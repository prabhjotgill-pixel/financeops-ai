# FinanceOps AI — Claude Code Instructions

## Repository Context

This repository contains FinanceOps AI, a finance automation platform that will combine:

* Finance/accounting workflows
* Python
* SQL
* Data analytics
* Automation
* AI/LLM capabilities

The project is being built incrementally through milestones.

## Rules

Follow the repository's `AGENTS.md` as the primary engineering contract.

For each task:

1. Inspect the existing implementation before changing it.
2. Identify the smallest appropriate change.
3. Preserve existing architecture unless the task explicitly requires a change.
4. Do not implement future milestones.
5. Add or update tests for behavior you change.
6. Run relevant validation commands before finishing.
7. Report any unresolved issue honestly.

## Architecture

Use:

API → Service → Repository/DB

Keep:

* HTTP concerns in API modules
* Business logic in services
* Database access in repositories/SQLAlchemy
* Request/response validation in Pydantic schemas
* Infrastructure configuration in core modules

## Finance/AI Rule

Future financial calculations must be deterministic and implemented in Python/SQL.

LLMs may explain, summarize, reason over retrieved data, and orchestrate tools, but must not be treated as the authoritative source for numerical financial calculations.

## Security

Never commit:

* API keys
* database credentials
* `.env`
* client information
* confidential accounting data

Use synthetic/demo data only.

## Milestone Discipline

Only implement the milestone specified by the user.

Do not add unrelated features because they appear useful.

## Completion Standard

A task is complete only when:

* implementation is coherent
* tests pass
* lint/type checks pass where applicable
* documentation is updated where necessary
* no known error is silently ignored
