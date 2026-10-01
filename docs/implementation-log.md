# Implementation log

## Milestone 0

Established native Windows development with FastAPI, Streamlit, SQLAlchemy, PostgreSQL, Alembic, health checks, unit/integration tests, linting, typing, and CI.

## Milestone 1 — GL ingestion

- Added company, source file, and canonical GL transaction tables through revision `0002_gl_ingestion`.
- Added bounded CSV/XLSX parsing, sheet selection, SHA-256 duplicate checks, deterministic column aliases, normalization, row issues, currency-grouped controls, and a two-stage validate/import workflow.
- Stored original source bytes and JSON quality reports to preserve rejected-row traceability. Import commits only rows without errors and prevents repeat import.
- Added company, worksheet, upload, report, import, and GL summary API routes plus a basic Streamlit ingestion page.
- Added synthetic CSV and multi-sheet XLSX fixtures and unit/integration coverage. No real accounting data or AI services were used.

Validation on native Windows: `alembic upgrade head` and `alembic check` passed on the existing development database and a clean temporary PostgreSQL database. `pytest` passed 27 unit tests; `pytest -m integration` passed 2 PostgreSQL integration tests. Ruff lint, Ruff format, and mypy passed. A running FastAPI instance returned 200 for live and ready, and Streamlit served the ingestion page. A manual HTTP upload of synthetic `mixed_gl.csv` produced 8 rows, 3 importable rows, 5 rejected rows, and 1 warning row; import persisted source rows 2, 3, and 9. The browser UI created a synthetic company, but its automated file picker did not open, so a complete browser upload was not verified. Both manual-test companies and their records were removed after verification.

## Milestone 2 — Financial intelligence

Implemented on 1 October 2026 against the refined specification. The existing ingestion models, data, routes, and native Windows workflow remain compatible. No runtime/development dependencies or AI calls were added.

### Changes

- Added revision `0003_financial_intelligence`, creating only `accounts`: required company/code/name, optional collective classification, active flag, timestamp, unique company/code, scoped parent foreign key, indexes, and restrictive deletion. Services serialize hierarchy edits and reject cycles.
- Added the centralized 22-category registry, exact company/code matching, unique normalized name-only matching, inactive historical classification, and manual account APIs.
- Added April–March calendar resolution, signed Decimal calculations, strict P&L availability, observed Balance Sheet subtotals with optional-category disclosures, four margins, independently tested ratio formulas, and explicit unavailable verified-balance/credit-base metrics.
- Defined the reusable FinancialResult contract before financial routes: metric, value, status, reason, calculation basis, formula version, currency, resolved period, contributing account snapshots, transaction count, source references, and warnings. Also includes company/unit. Four complete examples are in `financial-result-examples.json`.
- Added company/currency isolation, period discovery/summaries, current classifications, excluded population debit/credit disclosures, source quality warnings, and paginated source drill-down with an optional population fingerprint.
- Added the HTTP-only Financial Analysis page, synthetic account/GL fixtures, and API-based demo preparation/acceptance verification.

### Files created

```text
alembic/versions/0003_financial_intelligence.py
backend/app/api/v1/accounts.py
backend/app/api/v1/financials.py
backend/app/core/financial.py
backend/app/models/account.py
backend/app/repositories/accounts.py
backend/app/repositories/financials.py
backend/app/schemas/accounts.py
backend/app/schemas/financials.py
backend/app/services/accounts.py
backend/app/services/calculations.py
backend/app/services/classification.py
backend/app/services/financial_engine.py
backend/app/services/financials.py
backend/app/services/periods.py
backend/tests/fixtures/README.md
backend/tests/fixtures/financial_accounts.json
backend/tests/fixtures/financial_gl.csv
backend/tests/integration/test_financials_api.py
backend/tests/unit/test_financials.py
docs/financial-result-examples.json
frontend/pages/2_Financial_Analysis.py
scripts/seed_financial_demo.py
```

### Files modified

```text
.env.example
README.md
alembic.ini
backend/app/core/config.py
backend/app/core/errors.py
backend/app/main.py
backend/app/models/__init__.py
backend/tests/integration/test_postgres.py
docs/architecture.md
docs/database.md
docs/development-plan.md
docs/implementation-log.md
pyproject.toml
```

The migration-head assertion now compares with Alembic's actual head. `alembic.ini` explicitly declares the OS path separator. Domain error handling retains the existing ingestion error interface.

### Verification actually executed

Commands used `python -m uv` because uv is installed through Python on this machine:

```powershell
python -m uv run alembic upgrade head
python -m uv run alembic check
python -m uv run pytest -q
python -m uv run pytest -m integration -q
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run mypy backend
python -m uv lock --check
git diff --check
python -m uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
$env:BACKEND_URL = 'http://127.0.0.1:8001'
python -m uv run streamlit run frontend/streamlit_app.py --server.address 127.0.0.1 --server.port 8503 --server.headless true
python -m uv run python scripts/seed_financial_demo.py --base-url http://127.0.0.1:8001 --accounts-only
python -m uv run python scripts/seed_financial_demo.py --base-url http://127.0.0.1:8001 --verify-company-id 12
```

- Development PostgreSQL: migration upgrade and schema drift check passed.
- Clean PostgreSQL: initialized a separate temporary native PostgreSQL 17 cluster on localhost:55432, confirmed zero public tables, upgraded all migrations, passed `alembic check`, and passed all five integration tests. Stopped the temporary server afterwards. Development credentials and PostgreSQL security settings were not changed.
- Final default tests: **67 passed**, integration tests explicitly deselected.
- Final PostgreSQL integration tests: **5 passed**, unit tests deselected. The Milestone 0/1 tests are retained.
- Ruff lint/format passed; mypy passed for 59 backend source files; dependency lock and Git whitespace checks passed. An intermediate format check caught mixed line endings in an edited file; formatting was corrected and the check rerun.
- Unit coverage includes all accounting signs/contra postings, losses, every ratio, absent inputs versus observed zeroes, optional categories, unknown net-zero populations, strict credit bases, fiscal boundaries, category compatibility, matching, source warnings, reclassification, mixed-currency guards, and large Decimal ratio precision.
- Integration coverage includes account APIs/hierarchy/database constraints, existing name-only ingestion, warnings/ambiguity, exact annual acceptance, currency-specific period discovery, PostgreSQL persistence, period queries, traceability, and changed-population detection.
- FastAPI started successfully; live/ready returned 200. Streamlit started successfully; its native health endpoint returned 200.

The installed Starlette TestClient emits an upstream httpx deprecation warning. Tests pass; the warning is retained and no additional dependency was introduced to suppress it.

### Manual HTTP and browser verification

Prepared synthetic INR company 12, `Synthetic Financial Demo be1bc22d`, with 22 accounts. Uploaded `financial_gl.csv` through HTTP: 78 valid rows, zero warning/error rows. Import persisted 78 transactions in source file 15, with debit and credit controls of 339,500 each and zero difference.

Annual API verification matched every required value exactly:

| P&L metric | INR |
| --- | ---: |
| Operating revenue | 100,000 |
| COGS | 40,000 |
| Gross Profit | 60,000 |
| Employee Cost | 20,000 |
| Other Operating Expense | 10,000 |
| EBITDA | 30,000 |
| Depreciation | 5,000 |
| EBIT | 25,000 |
| Other Income | 2,000 |
| Finance Cost | 1,000 |
| PBT | 26,000 |
| Tax | 6,500 |
| PAT | 19,500 |

Margins matched **60%, 30%, 25%, and 19.5%**. The acceptance verifier was run again against the final restarted API and passed.

Chrome verification selected the synthetic company, INR, FY 2026-27, and annual period. The page displayed all exact P&L amounts and margins, saved operating revenue classification via PATCH (200), labeled Balance Sheet results `activity_derived`/`incomplete`, displayed unavailable ratios with reasons, and loaded four operating-revenue source transactions with file/row references.

**Browser upload was blocked:** the ChatGPT Chrome extension lacks “Allow access to file URLs.” The visible upload control opened a chooser, but assigning the synthetic fixture was rejected by the extension. Therefore a complete browser ingestion-to-analysis workflow was **not** verified. HTTP ingestion and subsequent browser classification/analysis were verified. The demo remains available for manual review; existing user companies were not removed.

### Limits and next work

Classifications change historical reports. Verified balances/coverage, reliable credit bases, formal cash flow, and historical classification versions remain future work. Reports use a company/currency/date-bounded in-memory population; larger histories may require repository aggregation/database pagination. No FX conversion, invented opening balances, retained-earnings adjustments, inferred zeroes, or AI integration is included.

Recommended next specification: verified financial-position inputs and provenance before enabling balance-dependent ratios or cash flow. Native Windows remains the development environment; Docker is an optional future deployment consideration.
