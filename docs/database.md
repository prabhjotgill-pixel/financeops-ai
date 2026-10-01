# Database schema

Alembic revision `0002_gl_ingestion` adds three tables after the Milestone 0 baseline.

## companies

- `id` integer primary key
- `name` required, unique, up to 200 characters
- `industry` optional
- `currency` required three-letter default currency for uploads
- `created_at` UTC-capable timestamp with database default

## source_files

- Required metadata: `id`, `company_id`, `filename`, `file_type`, `file_size`, `sha256`, `uploaded_at`, `status`, `row_count`, `valid_row_count`, `warning_row_count`, `error_row_count`
- Additional ingestion state: `sheet_name` (empty for CSV), `file_content` (bounded original bytes), and `validation_report` (JSONB)
- Foreign key to companies, company index, unique company/hash/worksheet combination, nonnegative count and positive size checks
- Status is `validated` or `imported`. Valid count includes rows with warnings; error count covers rejected rows. The counts are row counts, not issue counts.

## gl_transactions

- Required: `id`, `company_id`, `source_file_id`, `transaction_date`, `debit`, `credit`, `currency`, `source_row_number`, `created_at`
- Optional: `document_number`, `account_code`, `account_name`, `description`, `cost_center`, `department`
- Foreign keys to company and source file; indexes on company, source file, and transaction date
- Unique source file/row pair; at least one account identifier/name; nonnegative amounts with exactly one positive side
- Amounts use `NUMERIC(18,2)`; validation rejects excess precision rather than silently rounding.

## accounts

Revision `0003_financial_intelligence` adds only `accounts` and preserves Milestone 1 tables.

- Required: `id`, `company_id`, `account_code` (100 characters), `account_name` (255 characters), `is_active` (default true), and timezone-capable `created_at`.
- Optional: `account_type`, `financial_statement`, `financial_category`, and `parent_account_id`. Classification fields must be collectively assigned or collectively null.
- Unique company/code identity; leading zeroes are preserved. Names can repeat, causing visible ambiguity for name-only GL matching.
- Type/statement check constraints restrict supported identifiers. The application registry validates category compatibility. CASH_FLOW classifications are represented but excluded from initial financial calculations.
- Company foreign key and composite company/parent foreign key prevent cross-company parents. Self-parenting is rejected by a database check; the service rejects longer cycles while serializing hierarchy edits per company.
- Indexes on company and parent, with restricted referenced deletion. No account foreign key or backfill is added to GL rows: their original identifiers remain and match against current classifications.

Financial results and historical classifications are not stored in new tables. Reports expose current classification and source-population snapshots. There are no FP&A, forecasting, reconciliation, or AI tables.
