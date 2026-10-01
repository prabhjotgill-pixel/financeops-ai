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

There are no financial statement, FP&A, forecasting, reconciliation, or AI tables in this milestone.
