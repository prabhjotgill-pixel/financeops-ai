"""Create synthetic data through the API, or verify an existing synthetic company."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
EXPECTED_PNL = {
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
EXPECTED_MARGINS = {
    "gross_margin": "60.0000",
    "ebitda_margin": "30.0000",
    "ebit_margin": "25.0000",
    "pat_margin": "19.5000",
}


def verify(client: httpx.Client, company_id: int) -> None:
    base = f"/api/v1/companies/{company_id}/financials"
    for report, expected in (("pnl", EXPECTED_PNL), ("ratios", EXPECTED_MARGINS)):
        response = client.get(
            f"{base}/{report}", params={"fiscal_year": 2026, "currency": "INR"}
        )
        response.raise_for_status()
        results = response.json()["results"]
        actual = {key: results[key]["value"] for key in expected}
        if actual != expected:
            raise RuntimeError(f"Synthetic {report} acceptance failed: {actual}")
        print(f"Verified {report}: {json.dumps(actual)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--accounts-only",
        action="store_true",
        help="Prepare a company for browser CSV upload",
    )
    mode.add_argument(
        "--verify-company-id",
        type=int,
        help="Verify existing data without modifying it",
    )
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        if args.verify_company_id is not None:
            verify(client, args.verify_company_id)
            return
        response = client.post(
            "/api/v1/companies",
            json={
                "name": f"Synthetic Financial Demo {uuid4().hex[:8]}",
                "industry": "Synthetic testing",
                "currency": "INR",
            },
        )
        response.raise_for_status()
        company_id = response.json()["id"]
        for payload in json.loads((FIXTURES / "financial_accounts.json").read_text()):
            response = client.post(
                f"/api/v1/companies/{company_id}/accounts", json=payload
            )
            response.raise_for_status()
        print(f"Synthetic company_id={company_id}")
        if args.accounts_only:
            print(f"Upload {FIXTURES / 'financial_gl.csv'} on the Ingestion page.")
            return
        with (FIXTURES / "financial_gl.csv").open("rb") as stream:
            response = client.post(
                "/api/v1/files/upload",
                data={"company_id": str(company_id)},
                files={"file": ("financial_gl.csv", stream, "text/csv")},
            )
        response.raise_for_status()
        file_id = response.json()["file"]["id"]
        response = client.post(f"/api/v1/files/{file_id}/import")
        response.raise_for_status()
        verify(client, company_id)


if __name__ == "__main__":
    main()
