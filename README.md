# FinanceOps AI

FinanceOps AI is being built in milestones. Milestone 2 adds a chart of accounts and deterministic financial intelligence to the existing CSV/XLSX ingestion and health foundation. Financial results include classification snapshots, availability reasons, warnings, and source traceability. The application uses no AI services.

## Architecture

Browser -> Streamlit -> FastAPI -> services -> repositories -> SQLAlchemy -> PostgreSQL.

The frontend calls HTTP endpoints only. The backend parses and validates files, stores the original upload and its report, then imports eligible rows on a separate request. See [docs/architecture.md](docs/architecture.md) and [docs/database.md](docs/database.md).

## Prerequisites

- Windows with Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL 17 installed natively, with its Windows service and `psql.exe`

## Native PostgreSQL setup

Check the service and start it if needed. Starting it may require elevated PowerShell:

```powershell
Get-Service postgresql-x64-17
Start-Service postgresql-x64-17
```

On a fresh installation, create the example development role and database once. `psql` prompts for the PostgreSQL administrator password:

```powershell
$psql = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
& $psql -h 127.0.0.1 -U postgres -d postgres -W -c "CREATE ROLE financeops LOGIN PASSWORD 'financeops'"
& $psql -h 127.0.0.1 -U postgres -d postgres -W -c "CREATE DATABASE financeops OWNER financeops"
```

Skip these commands if the role and database already exist. If you change the role password, update DATABASE_URL to match.

## Local setup

From the repository root:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
uv sync --frozen
uv run alembic upgrade head
```

Retain an existing configured .env; set DATABASE_URL to your native PostgreSQL database. If uv was installed through pip and its executable is not on PATH, use `python -m uv` in place of `uv`. Never commit .env. OPENAI_API_KEY may remain blank and is unused.

Start FastAPI and Streamlit in separate terminals from the repository root:

```powershell
uv run uvicorn backend.app.main:app --reload
```

```powershell
uv run streamlit run frontend/streamlit_app.py
```

Open http://localhost:8501 and choose the **Ingestion** page in the sidebar.

## Ingestion workflow

1. Create or select a company and its default three-letter currency.
2. Choose a .csv or .xlsx file. For a workbook with multiple sheets, select the GL worksheet.
3. Click **Parse and validate**. Review detected columns, row counts, row issues, and debit/credit controls per currency.
4. Click **Import valid rows**. Rows with warnings are importable; rows with errors remain in the saved report and source file.
5. Review the import count and company GL summary.

Uploads are limited to 10 MB and 100,000 data rows. CSV must be UTF-8. The same file and worksheet cannot be uploaded twice for the same company. Balancing is informational; an unbalanced file is not rejected. Totals include importable rows only.

## API

- `POST /api/v1/companies` and `GET /api/v1/companies`
- `POST /api/v1/files/sheets`: list XLSX worksheets without saving the file
- `POST /api/v1/files/upload`: multipart `company_id`, `file`, optional `sheet_name`; saves the source and validation report
- `GET /api/v1/files/{file_id}`: source metadata and counts
- `GET /api/v1/files/{file_id}/validation-report`: mapping, issues, counts, and controls
- `POST /api/v1/files/{file_id}/import`: import valid and warning rows once
- `GET /api/v1/companies/{company_id}/gl/summary`: stored transaction count and controls per currency
- `GET /api/v1/health/live` and `GET /api/v1/health/ready`

File-level failures return an error code and do not create a source record. A readable file with bad individual rows produces a saved report. See [docs/architecture.md](docs/architecture.md) for validation details.

## Financial analysis

Open **Financial Analysis** after importing GL data. Create/classify accounts, then select company, currency, fiscal year, and month/quarter/year. Exact company/code matching takes priority; name-only GL rows can match a unique name normalized for case/whitespace. Classification changes recalculate every period; historical versions are not stored.

FY 2026-27 runs from 1 April 2026 through 31 March 2027. Q1 is April–June, Q2 July–September, Q3 October–December, Q4 January–March. Calculated values describe observed activity; incomplete values retain evidence limitations; unavailable values contain null and a reason. Missing P&L inputs are never inferred as zero. Balance Sheet subtotals include observed categories even when optional categories have no activity, but are incomplete because opening/closing coverage is unverified. Observed zeroes remain distinct from absent categories.

Balance-dependent ratios and verified working-capital totals remain unavailable. DSO requires reliable credit sales; DPO requires reliable credit purchases. Revenue and COGS never substitute. There is no FX conversion or formal cash-flow statement. Use **Source transactions** to inspect original file/row references and excluded populations.

Additional APIs:

- `GET /api/v1/accounts/classification-catalog`
- `GET/POST /api/v1/companies/{company_id}/accounts`
- `GET /api/v1/companies/{company_id}/accounts/by-code/{account_code}`
- `PATCH /api/v1/accounts/{account_id}`: classification, parent, and active status; identity is immutable
- `GET /api/v1/companies/{company_id}/financials/pnl`
- `GET /api/v1/companies/{company_id}/financials/balance-sheet`
- `GET /api/v1/companies/{company_id}/financials/metrics`
- `GET /api/v1/companies/{company_id}/financials/ratios`
- `GET /api/v1/companies/{company_id}/financials/periods`
- `GET /api/v1/companies/{company_id}/financials/period-summaries`
- `GET /api/v1/companies/{company_id}/financials/transactions`

Reports require `fiscal_year` (starting year), `period_type=year|quarter|month`, optional `currency`, and `quarter=1..4` or calendar `month=1..12` where appropriate. January–March resolve to the following calendar year. Incompatible parameters return 422. Example: `/api/v1/companies/1/financials/pnl?fiscal_year=2026&period_type=quarter&quarter=4&currency=INR`.

Period summaries use fiscal year, currency, and grouping period type. Discovery lists available fiscal years, months, and currencies. Drill-down uses report period parameters plus `population=contributing`, `report_type`, `metric`, `offset`, and `limit` (maximum 200). Exclusions use `population=excluded` and `scope=period_activity|activity_derived`, without a metric. Supply the report's `population_fingerprint` to detect changed data/classifications with a 409 response.

See the reusable FinancialResult contract and formulas in [architecture](docs/architecture.md), and [full JSON examples](docs/financial-result-examples.json).

## Synthetic financial demo

With FastAPI running:

```powershell
uv run python scripts/seed_financial_demo.py
```

This creates a synthetic INR company, 22 accounts, and 78 balanced journal lines through the existing API, then verifies the exact annual P&L and margins. Select the printed company on Financial Analysis and FY 2026-27.

For a browser upload exercise, run `uv run python scripts/seed_financial_demo.py --accounts-only`, select its company on Ingestion, upload `backend/tests/fixtures/financial_gl.csv`, validate, and import. Then run `uv run python scripts/seed_financial_demo.py --verify-company-id <printed-id>`. Any unexpected P&L/margin value fails verification. Each seed creates a separate synthetic company.

## Quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy backend
uv run pytest
uv run pytest -m integration
uv run alembic check
```

The default pytest run contains unit tests. The marked integration tests require native PostgreSQL migrated to head; they read DATABASE_URL from .env unless TEST_DATABASE_URL is set. All fixtures under `backend/tests/fixtures` are synthetic.

## Environment

- APP_ENV, APP_NAME, LOG_LEVEL: application metadata and logging.
- DATABASE_URL: PostgreSQL URL used by FastAPI, Alembic, and integration tests.
- BACKEND_URL: Streamlit's backend address.
- FINANCIAL_YEAR_START_MONTH: centralized reporting calendar, defaults to 4; valid values 1–12.
- OPENAI_API_KEY and AI_PROVIDER: reserved example values, unused.

See [docs/development-plan.md](docs/development-plan.md) and [docs/implementation-log.md](docs/implementation-log.md).
