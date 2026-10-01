# FinanceOps AI

FinanceOps AI is being built in milestones. Milestone 1 adds deterministic General Ledger ingestion to the Milestone 0 health and database foundation. It supports CSV and XLSX files, row-level quality reports, and importing valid rows into PostgreSQL. It does not use AI or perform finance analysis.

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
Copy-Item .env.example .env
uv sync --frozen
uv run alembic upgrade head
```

If uv was installed through pip and its executable is not on PATH, use `python -m uv` in place of `uv`. Never commit .env. OPENAI_API_KEY may remain blank and is unused.

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

## Checks

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
- OPENAI_API_KEY and AI_PROVIDER: reserved example values, unused.

See [docs/development-plan.md](docs/development-plan.md) and [docs/implementation-log.md](docs/implementation-log.md).
