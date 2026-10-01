# Milestone 1 architecture

```text
Browser -> Streamlit -> FastAPI /api/v1 -> services -> repositories
                                               -> SQLAlchemy -> PostgreSQL
```

The local stack runs natively on Windows. Streamlit makes HTTP calls only. The API handles multipart uploads and response schemas. Ingestion services own file checks, deterministic header mapping, normalization, validation, and the decision to import. Repositories own SQLAlchemy reads and writes. Milestone 0 health routes and error handling remain available.

## Two-stage ingestion

1. The client creates/selects a company. For XLSX, it can ask the API for sheet names before choosing one.
2. Upload checks extension, size, content, and same-company file/worksheet SHA-256 duplicates. CSV is decoded as UTF-8; XLSX is read as workbook data without executing macros or formulas.
3. Header aliases are normalized with Unicode normalization, case folding, and removal of punctuation/spacing. A required date, account identifier/name, and at least one amount column must be identifiable. Ambiguous or missing required mapping is a file-level 422 response.
4. Every data row is validated. The report records source row, severity, code, and message. Errors make a row ineligible; warnings allow import. Debit, credit, and difference controls include importable rows and are grouped by currency. Balance is informational.
5. The original bounded upload and JSON quality report are saved in `source_files`. A separate import request locks the file record, reparses the stored bytes, inserts only eligible rows, and marks the source imported in one transaction. Unique source-row constraints and an imported status prevent repeat imports.
6. The company summary reads imported transactions from PostgreSQL and groups amounts by currency.

Exact duplicate document/date/account/amount/currency rows within one file receive a warning. A voucher number alone may legitimately cover several GL lines, so it is not treated as a duplicate. Date input accepts ISO dates and day-first slash/dash dates. Monetary input accepts grouped decimals with at most two significant decimal places. Blank amount cells become zero; a row must have exactly one positive side.

File-level failures do not create a source record. Rows from readable files remain traceable through `source_file_id`, `source_row_number`, the stored original upload, and the report. See [database.md](database.md).
