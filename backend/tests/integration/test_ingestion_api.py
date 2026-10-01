import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import make_engine
from backend.app.main import create_app
from backend.app.models import GLTransaction

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_gl_ingestion_end_to_end() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    if not database_url.startswith("postgresql+psycopg://"):
        pytest.fail("Integration test requires PostgreSQL")
    engine = make_engine(database_url)
    company_id: int | None = None
    app = create_app(Settings(database_url=database_url))
    try:
        with TestClient(app) as client:
            name = f"Synthetic GL Test {uuid4().hex}"
            created = client.post(
                "/api/v1/companies",
                json={"name": name, "industry": "Synthetic", "currency": "USD"},
            )
            assert created.status_code == 201
            company_id = created.json()["id"]
            listed = client.get("/api/v1/companies")
            assert any(row["id"] == company_id for row in listed.json())

            mixed = (FIXTURES / "mixed_gl.csv").read_bytes()
            uploaded = client.post(
                "/api/v1/files/upload",
                data={"company_id": str(company_id)},
                files={"file": ("mixed_gl.csv", mixed, "text/csv")},
            )
            assert uploaded.status_code == 201, uploaded.text
            file_id = uploaded.json()["file"]["id"]
            assert uploaded.json()["report"]["valid_row_count"] == 3
            assert uploaded.json()["report"]["error_row_count"] == 5
            assert uploaded.json()["report"]["warning_row_count"] == 1
            duplicate = client.post(
                "/api/v1/files/upload",
                data={"company_id": str(company_id)},
                files={"file": ("mixed_gl.csv", mixed, "text/csv")},
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["code"] == "DUPLICATE_UPLOAD"
            assert duplicate.json()["detail"]["details"]["file_id"] == file_id

            metadata = client.get(f"/api/v1/files/{file_id}")
            assert metadata.status_code == 200
            assert metadata.json()["status"] == "validated"
            report = client.get(f"/api/v1/files/{file_id}/validation-report")
            assert report.status_code == 200
            assert report.json()["file_id"] == file_id
            rejected = [
                issue
                for issue in report.json()["issues"]
                if issue["severity"] == "ERROR"
            ]
            assert rejected and all(issue["row_number"] >= 2 for issue in rejected)
            assert report.json()["controls"][0]["difference"] == "100.00"

            imported = client.post(f"/api/v1/files/{file_id}/import")
            assert imported.status_code == 200, imported.text
            assert imported.json()["imported_row_count"] == 3
            assert imported.json()["skipped_row_count"] == 5
            assert client.post(f"/api/v1/files/{file_id}/import").status_code == 409

            workbook = (FIXTURES / "multi_sheet_gl.xlsx").read_bytes()
            sheets = client.post(
                "/api/v1/files/sheets",
                files={"file": ("multi_sheet_gl.xlsx", workbook)},
            )
            assert sheets.status_code == 200
            assert sheets.json()["sheets"] == ["Notes", "GL"]
            no_sheet = client.post(
                "/api/v1/files/upload",
                data={"company_id": str(company_id)},
                files={"file": ("multi_sheet_gl.xlsx", workbook)},
            )
            assert no_sheet.status_code == 422
            excel = client.post(
                "/api/v1/files/upload",
                data={"company_id": str(company_id), "sheet_name": "GL"},
                files={"file": ("multi_sheet_gl.xlsx", workbook)},
            )
            assert excel.status_code == 201, excel.text
            assert excel.json()["report"]["valid_row_count"] == 2
            excel_id = excel.json()["file"]["id"]
            assert client.post(f"/api/v1/files/{excel_id}/import").status_code == 200

            summary = client.get(f"/api/v1/companies/{company_id}/gl/summary")
            assert summary.status_code == 200
            assert summary.json()["transaction_count"] == 5
            assert summary.json()["controls"][0]["total_debit"] == "225.00"

        with engine.connect() as connection:
            rows = connection.scalars(
                select(GLTransaction.source_row_number)
                .where(GLTransaction.source_file_id == file_id)
                .order_by(GLTransaction.source_row_number)
            ).all()
            assert list(rows) == [2, 3, 9]
    finally:
        if company_id is not None:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM gl_transactions WHERE company_id = :company_id"),
                    {"company_id": company_id},
                )
                connection.execute(
                    text("DELETE FROM source_files WHERE company_id = :company_id"),
                    {"company_id": company_id},
                )
                connection.execute(
                    text("DELETE FROM companies WHERE id = :company_id"),
                    {"company_id": company_id},
                )
        engine.dispose()
