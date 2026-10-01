import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import make_engine
from backend.app.main import create_app

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def financial_client() -> Iterator[tuple[TestClient, list[int], str]]:
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    if not url.startswith("postgresql+psycopg://"):
        pytest.fail("Financial integration tests require migrated PostgreSQL")
    company_ids: list[int] = []
    try:
        with TestClient(create_app(Settings(database_url=url))) as client:
            yield client, company_ids, url
    finally:
        database = make_engine(url)
        with database.begin() as connection:
            for company_id in company_ids:
                parameters = {"company_id": company_id}
                connection.execute(
                    text(
                        "UPDATE accounts SET parent_account_id = NULL "
                        "WHERE company_id = :company_id"
                    ),
                    parameters,
                )
                for table in ("accounts", "gl_transactions", "source_files"):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE company_id = :company_id"),
                        parameters,
                    )
                connection.execute(
                    text("DELETE FROM companies WHERE id = :company_id"), parameters
                )
        database.dispose()


def create_company(client: TestClient, ids: list[int]) -> int:
    response = client.post(
        "/api/v1/companies",
        json={"name": f"Synthetic M2 Test {uuid4().hex}", "currency": "INR"},
    )
    assert response.status_code == 201, response.text
    company_id = int(response.json()["id"])
    ids.append(company_id)
    return company_id


def upload_and_import(
    client: TestClient, company_id: int, filename: str, content: bytes
) -> int:
    uploaded = client.post(
        "/api/v1/files/upload",
        data={"company_id": str(company_id)},
        files={"file": (filename, content)},
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = int(uploaded.json()["file"]["id"])
    imported = client.post(f"/api/v1/files/{file_id}/import")
    assert imported.status_code == 200, imported.text
    return file_id


def test_exact_financial_acceptance_persistence_periods_currency_and_traceability(
    financial_client: tuple[TestClient, list[int], str],
) -> None:
    client, ids, url = financial_client
    company_id = create_company(client, ids)
    payloads = json.loads((FIXTURES / "financial_accounts.json").read_text())
    accounts = {}
    for payload in payloads:
        response = client.post(f"/api/v1/companies/{company_id}/accounts", json=payload)
        assert response.status_code == 201, response.text
        accounts[payload["financial_category"]] = response.json()["id"]
    file_id = upload_and_import(
        client,
        company_id,
        "financial_gl.csv",
        (FIXTURES / "financial_gl.csv").read_bytes(),
    )
    base = f"/api/v1/companies/{company_id}/financials"
    parameters = {"fiscal_year": 2026}
    pnl_response = client.get(f"{base}/pnl", params=parameters)
    assert pnl_response.status_code == 200, pnl_response.text
    report = pnl_response.json()
    expected = {
        "operating_revenue": "100000.00",
        "cogs": "40000.00",
        "gross_profit": "60000.00",
        "employee_cost": "20000.00",
        "other_operating_expense": "10000.00",
        "ebitda": "30000.00",
        "depreciation": "5000.00",
        "ebit": "25000.00",
        "other_income": "2000.00",
        "finance_cost": "1000.00",
        "pbt": "26000.00",
        "tax": "6500.00",
        "pat": "19500.00",
    }
    assert {key: report["results"][key]["value"] for key in expected} == expected
    assert report["results"]["pat"]["transaction_count"] == 32
    assert report["results"]["pat"]["source_files"][0]["source_file_id"] == file_id
    required = {
        "metric",
        "value",
        "status",
        "reason",
        "calculation_basis",
        "formula_version",
        "currency",
        "resolved_period",
        "contributing_accounts",
        "transaction_count",
        "source_files",
        "warnings",
    }
    assert all(required <= result.keys() for result in report["results"].values())
    ratio_response = client.get(f"{base}/ratios", params=parameters)
    assert ratio_response.status_code == 200, ratio_response.text
    ratios = ratio_response.json()["results"]
    margins = {
        "gross_margin": "60.0000",
        "ebitda_margin": "30.0000",
        "ebit_margin": "25.0000",
        "pat_margin": "19.5000",
    }
    assert {key: ratios[key]["value"] for key in margins} == margins
    assert ratios["dso"]["value"] is None and ratios["dpo"]["value"] is None
    assert ratios["current_ratio"]["status"] == "unavailable"
    bs = client.get(f"{base}/balance-sheet", params=parameters).json()
    assert bs["results"]["trade_receivables"]["value"] == "110000.00"
    assert bs["results"]["total_assets"]["status"] == "incomplete"
    metrics = client.get(f"{base}/metrics", params=parameters).json()
    assert metrics["results"]["net_working_capital"]["value"] is None
    quarter = client.get(
        f"{base}/pnl", params=parameters | {"period_type": "quarter", "quarter": 4}
    ).json()
    assert quarter["results"]["pat"]["value"] == "4875.00"
    january = client.get(
        f"{base}/pnl", params=parameters | {"period_type": "month", "month": 1}
    ).json()
    assert january["resolved_period"]["start_date"] == "2027-01-01"
    march = client.get(
        f"{base}/pnl", params=parameters | {"period_type": "month", "month": 3}
    ).json()
    assert march["results"]["operating_revenue"]["value"] is None
    assert (
        client.get(f"{base}/pnl", params=parameters | {"quarter": 1}).status_code == 422
    )
    assert (
        client.get(
            f"{base}/pnl", params=parameters | {"period_type": "quarter"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{base}/pnl", params=parameters | {"currency": "INVALID"}
        ).status_code
        == 422
    )
    assert client.get(f"{base}/periods").json()["fiscal_years"] == [2026]
    summary = client.get(
        f"{base}/period-summaries", params=parameters | {"period_type": "quarter"}
    )
    assert summary.status_code == 200
    assert len(summary.json()["reports"]) == 4
    assert all(
        entry["results"]["pat"]["value"] == "4875.00"
        for entry in summary.json()["reports"]
    )
    trace_parameters = parameters | {
        "report_type": "pnl",
        "metric": "pat",
        "population_fingerprint": report["population_fingerprint"],
        "limit": 5,
    }
    trace = client.get(f"{base}/transactions", params=trace_parameters)
    assert trace.status_code == 200
    assert trace.json()["total"] == 32 and len(trace.json()["transactions"]) == 5
    assert all(
        entry["source_file_id"] == file_id
        and entry["source_row_number"] >= 2
        and entry["matched_account"]["financial_category"]
        for entry in trace.json()["transactions"]
    )
    usd = (
        b"Date,Account Code,Account,Debit,Credit,Currency\n"
        b"2026-04-15,0001,Revenue,,500,USD\n"
        b"2026-04-15,0009,Cash,500,,USD\n"
        b"2025-04-15,0001,Revenue,,100,USD\n"
        b"2025-04-15,0009,Cash,100,,USD\n"
    )
    upload_and_import(client, company_id, "synthetic_usd.csv", usd)
    assert client.get(f"{base}/periods").json()["fiscal_years"] == [2026]
    assert client.get(f"{base}/periods", params={"currency": "USD"}).json()[
        "fiscal_years"
    ] == [2025, 2026]
    refreshed = client.get(f"{base}/pnl", params=parameters).json()
    assert refreshed["results"]["operating_revenue"]["value"] == "100000.00"
    assert any(
        warning["code"] == "OTHER_CURRENCIES_EXCLUDED"
        for warning in refreshed["results"]["operating_revenue"]["warnings"]
    )
    usd_report = client.get(
        f"{base}/pnl", params=parameters | {"currency": "USD"}
    ).json()
    assert usd_report["results"]["operating_revenue"]["value"] == "500.00"
    changed = client.patch(
        f"/api/v1/accounts/{accounts['other_income']}",
        json={"financial_category": "operating_revenue"},
    )
    assert changed.status_code == 200
    reclassified = client.get(f"{base}/pnl", params=parameters).json()
    assert reclassified["results"]["operating_revenue"]["value"] == "102000.00"
    assert reclassified["results"]["pat"]["value"] is None
    assert (
        client.get(f"{base}/transactions", params=trace_parameters).status_code == 409
    )
    database = make_engine(url)
    with database.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM gl_transactions "
                    "WHERE source_file_id = :file_id"
                ),
                {"file_id": file_id},
            )
            == 78
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM accounts WHERE company_id = :company_id"),
                {"company_id": company_id},
            )
            == 22
        )
    database.dispose()


def test_account_catalog_identity_and_hierarchy(
    financial_client: tuple[TestClient, list[int], str],
) -> None:
    client, ids, url = financial_client
    company_id = create_company(client, ids)
    other_company = create_company(client, ids)
    base = f"/api/v1/companies/{company_id}/accounts"
    payload = {
        "account_code": "0001",
        "account_name": "Cash",
        "account_type": "ASSET",
        "financial_statement": "BALANCE_SHEET",
        "financial_category": "cash",
    }
    root = client.post(base, json=payload).json()
    assert client.post(base, json=payload).status_code == 409
    assert client.get(f"{base}/by-code/0001").json()["id"] == root["id"]
    assert (
        client.get(
            f"/api/v1/companies/{other_company}/accounts/by-code/0001"
        ).status_code
        == 404
    )
    foreign = client.post(
        f"/api/v1/companies/{other_company}/accounts", json=payload
    ).json()
    child = client.post(
        base, json=payload | {"account_code": "0002", "parent_account_id": root["id"]}
    ).json()
    assert (
        client.patch(
            f"/api/v1/accounts/{root['id']}", json={"parent_account_id": child["id"]}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/accounts/{root['id']}", json={"parent_account_id": root["id"]}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/accounts/{child['id']}", json={"parent_account_id": foreign["id"]}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/accounts/{root['id']}", json={"account_type": "REVENUE"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/accounts/{root['id']}", json={"is_active": None}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/accounts/{root['id']}", json={"financial_statement": "CASH_FLOW"}
        ).status_code
        == 200
    )
    unclassified = client.post(
        base, json={"account_code": "0003", "account_name": "Pending"}
    )
    assert unclassified.status_code == 201
    catalog = client.get("/api/v1/accounts/classification-catalog").json()
    assert len(catalog["categories"]) == 22
    assert "CASH_FLOW" in catalog["financial_statements"]
    database = make_engine(url)
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            text("UPDATE accounts SET parent_account_id = :parent WHERE id = :child"),
            {"parent": foreign["id"], "child": child["id"]},
        )
    database.dispose()


def test_existing_name_only_gl_exclusions_and_source_quality(
    financial_client: tuple[TestClient, list[int], str],
) -> None:
    client, ids, _url = financial_client
    company_id = create_company(client, ids)
    accounts_url = f"/api/v1/companies/{company_id}/accounts"
    cash = {
        "account_code": "CASH",
        "account_name": "Cash",
        "account_type": "ASSET",
        "financial_statement": "BALANCE_SHEET",
        "financial_category": "cash",
    }
    assert client.post(accounts_url, json=cash).status_code == 201
    upload_and_import(
        client, company_id, "mixed_gl.csv", (FIXTURES / "mixed_gl.csv").read_bytes()
    )
    base = f"/api/v1/companies/{company_id}/financials"
    parameters = {"fiscal_year": 2024}
    bs = client.get(f"{base}/balance-sheet", params=parameters).json()
    assert bs["results"]["cash"]["value"] == "200.00"
    assert bs["results"]["current_assets"]["value"] == "200.00"
    assert {warning["code"] for warning in bs["results"]["cash"]["warnings"]} >= {
        "SOURCE_ROWS_REJECTED",
        "SOURCE_ROW_WARNINGS",
        "UNMATCHED_ACCOUNT_NAME",
    }
    trace = client.get(
        f"{base}/transactions",
        params=parameters | {"population": "excluded", "scope": "activity_derived"},
    ).json()
    assert trace["total"] == 1
    assert trace["transactions"][0]["exclusion_reason"] == "UNMATCHED_ACCOUNT_NAME"
    revenue = client.post(
        accounts_url,
        json={
            "account_code": "REV",
            "account_name": " Revenue ",
            "account_type": "REVENUE",
            "financial_statement": "PROFIT_AND_LOSS",
            "financial_category": "operating_revenue",
        },
    ).json()
    pnl = client.get(f"{base}/pnl", params=parameters).json()
    assert pnl["results"]["operating_revenue"]["value"] == "100.00"
    assert pnl["results"]["operating_revenue"]["status"] == "incomplete"
    assert pnl["results"]["operating_revenue"]["contributing_accounts"][0][
        "match_methods"
    ] == ["name"]
    assert (
        client.patch(
            f"/api/v1/accounts/{revenue['id']}", json={"is_active": False}
        ).status_code
        == 200
    )
    assert (
        client.get(f"{base}/pnl", params=parameters).json()["results"][
            "operating_revenue"
        ]["value"]
        == "100.00"
    )
    assert (
        client.post(
            accounts_url,
            json=cash | {"account_code": "CASH2", "account_name": " CASH "},
        ).status_code
        == 201
    )
    ambiguous = client.get(f"{base}/balance-sheet", params=parameters).json()
    assert ambiguous["results"]["cash"]["value"] is None
    assert any(
        warning["code"] == "AMBIGUOUS_ACCOUNT_NAME" for warning in ambiguous["warnings"]
    )
