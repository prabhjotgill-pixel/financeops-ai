# Development plan

- **Milestone 0 — Foundation (complete):** native Windows Python and PostgreSQL setup, health API, Streamlit status page, Alembic baseline, tests, and CI.
- **Milestone 1 — GL ingestion (complete):** companies, CSV/XLSX upload, deterministic mapping, row validation, quality report, valid-row import, source traceability, and basic Streamlit workflow.
- **Milestone 2 — Financial intelligence (implemented):** chart of accounts, exact classification, April–March periods, signed P&L, activity-derived Balance Sheet subtotals, reusable FinancialResult evidence, margins, explicit unavailable balance-dependent metrics, APIs, and basic Streamlit analysis. Verification results and the browser upload permission limitation are recorded in the implementation log.
- **Recommended next data foundation:** verified opening/closing balances and coverage, reliable credit-sales/purchases bases, and historical classification provenance. Specify and test these before enabling balance-dependent metrics or formal cash flow.
- **Later milestones — Separate work:** financial analysis, operational workflows, reporting, and AI assistance require their own specifications and tests. None are implemented as part of Milestone 1.

Docker may be evaluated later as an optional deployment method. It is not part of local development.
