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
