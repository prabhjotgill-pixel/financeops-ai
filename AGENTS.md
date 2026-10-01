# FinanceOps AI — Agent Instructions

## Project

FinanceOps AI is a finance automation platform combining finance/accounting workflows, Python, SQL, data analytics, automation, and AI.

The application will eventually support:

* Financial data ingestion
* Financial statement analysis
* FP&A
* Budget vs actual analysis
* Variance analysis
* Reconciliation
* Working-capital analysis
* Transaction anomaly detection
* Internal controls / IFC testing
* Credit analysis
* AI-assisted financial analysis
* Management reporting

## Engineering Principles

1. Keep business logic out of API route handlers.
2. Keep database access behind repository/data-access boundaries.
3. Keep business logic in services.
4. Use Pydantic schemas at API boundaries.
5. Use SQLAlchemy for database access.
6. Use Alembic for schema migrations.
7. Financial calculations must be deterministic and testable.
8. LLMs must never be the source of truth for numerical financial calculations.
9. AI features must retrieve structured data through explicit tools/services.
10. Never use real client or confidential CA-firm data.
11. Never commit secrets, API keys, credentials, or .env files.
12. Prefer simple architecture over unnecessary infrastructure.
13. Do not introduce microservices unless there is a documented reason.
14. New functionality requires tests.
15. Keep changes scoped to the current task.

## Python Standards

* Use type hints.
* Prefer clear, readable code over clever abstractions.
* Follow Ruff formatting and linting rules.
* Use meaningful names.
* Avoid unnecessary global state.
* Use dependency injection where appropriate.
* Handle errors explicitly.
* Do not silently swallow exceptions.

## Database Standards

* Use SQLAlchemy ORM/models consistently.
* Schema changes must use Alembic migrations.
* Do not modify the database schema manually.
* Add appropriate foreign keys and indexes.
* Do not place raw SQL in API route handlers.

## API Standards

* APIs are versioned under `/api/v1`.
* Route handlers should remain thin.
* Validate inputs using Pydantic.
* Return consistent response structures.
* Use appropriate HTTP status codes.
* Do not expose internal exceptions or secrets.

## AI Standards

When AI functionality is eventually introduced:

* Separate provider-specific code from business logic.
* Use an AI provider abstraction.
* Keep deterministic calculations outside the LLM.
* Give agents explicit tools rather than unrestricted database access.
* Preserve traceability from generated conclusions to source data.
* Use structured outputs where appropriate.
* Add evaluation tests for important financial reasoning.
* Introduce human review for consequential finance/control decisions.

## Documentation

Update relevant documentation when architecture, database structure, setup, or development workflow changes.

Do not force-read every documentation file for every task. Read the documents relevant to the requested change.

## Verification

Before declaring a task complete, run the relevant checks.

For Python changes, prefer:

* `ruff check .`
* `ruff format --check .`
* `mypy backend`
* `pytest`

If a validation command fails because of an environment issue, report it explicitly rather than hiding the failure.

## Scope Control

Do not implement future milestones unless explicitly requested.

Do not add AI, finance calculations, authentication, cloud infrastructure, or advanced UI during Milestone 0 unless required to satisfy the milestone's acceptance criteria.
