# FinanceOps architecture

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

## Milestone 2 financial intelligence

Stored GL -> company chart of accounts -> exact classification -> financial engine -> shared results -> API -> Streamlit.

Repositories own chart-of-accounts reads and company/currency/date-bounded imported GL queries. They do not load original upload bytes for financial reports. Classification matches exact company/code, or a unique normalized name only when the GL code is absent. Unmatched, ambiguous, unclassified, and CASH_FLOW-only populations remain visible. Inactive accounts retain their classifications for historical activity. Parent hierarchy does not double-count posted transactions.

Services own fiscal periods, matching, signed arithmetic, availability, and evidence. Streamlit uses HTTP only and displays backend results. No GL schema rewrite, classification history, FX conversion, or user-declared opening-balance assertion is added.

### Calculation methodology

All financial arithmetic uses Decimal. Revenue, liabilities, and equity use credit minus debit; expenses and assets use debit minus credit. Contra postings, negative amounts, and losses retain their signs. No absolute-value normalization is used.

Gross Profit = Operating Revenue − COGS. Operating Expenses = Employee Cost + Other Operating Expense. EBITDA = Gross Profit − Operating Expenses. EBIT = EBITDA − Depreciation. PBT = EBIT + Other Income − Finance Cost. PAT = PBT − Tax. Other income is excluded from operating revenue and EBITDA. Margins divide the corresponding profit by operating revenue and multiply by 100.

Balance Sheet categories represent cumulative classified activity through period end. Optional absent categories remain null; section subtotals sum observed populations rather than inserting zeroes. A section with no qualifying population is unavailable. Subtotals remain incomplete because opening/closing coverage is unverified, even if arithmetic is balanced. No retained-earnings or balancing plug is manufactured.

Ratio functions support explicit verified inputs: current assets/current liabilities; explicitly verified quick assets/current liabilities; debt/equity; PAT/average assets; PAT/average equity; EBIT/average capital employed, with capital employed defined as assets less current liabilities. Return ratios are percentages, without subannual annualization. Days measures use average relevant balances and actual resolved-period days. Inventory days requires COGS. DSO requires reliable credit sales, DPO reliable credit purchases, and cash conversion cycle requires DSO + inventory days − DPO. Generic revenue/COGS never substitute for credit bases. Missing inputs and non-positive denominators yield null; negative profit numerators remain valid.

The reporting service does not provide verified balances or reliable credit bases in this milestone. Balance-dependent ratios and verified working-capital totals therefore remain unavailable. Observed current-asset, current-liability, receivable, payable, inventory, and cash activity remain visible separately.

The distinction between position at period end and performance over a period is described by the [IFRS presentation framework](https://www.ifrs.org/issued-standards/list-of-standards/ias-1-presentation-of-financial-statements/). Ratio conventions are documented with [ACCA interpretation guidance](https://www.accaglobal.com/an/en/student/exam-support-resources/fundamentals-exams-study-resources/f7/technical-articles/performance-appraisal.html). These activity reports do not certify complete statutory statements.

### Shared FinancialResult contract

Every result includes `company_id`, `metric`, `value`, `unit`, `status`, `reason`, `calculation_basis`, `formula_version`, `currency`, `resolved_period`, `contributing_accounts`, `transaction_count`, `source_files`, and `warnings`. Values serialize as signed decimal strings. Unavailable results require null and a structured reason; incomplete results require a numeric value and reason; calculated results require a numeric value. No observed P&L category means unavailable, which propagates to dependent totals. Observed net-zero populations remain zero.

Calculation basis contains the formula, kind, input metrics, category population, company/currency/date scope, coverage flag, and population fingerprint. Account contributions include classification snapshots, matching methods, debit/credit and signed amounts, counts, and source IDs. Source references include file identity/hash, contribution counts, and quality counts. Derived results use distinct contributing GL transactions; shared numerator/denominator inputs are not counted again.

Warnings propagate to affected results for unknown accounts, ambiguous names, unclassified accounts, cash-flow exclusions, rejected source rows, and source row warnings. Excluded populations disclose both debit and credit totals even when their net activity is zero; materiality is not inferred. Informational warnings expose unverified period coverage, inactive-account activity, and excluded currencies. Optional absent categories are disclosed without suppressing Balance Sheet subtotals. Source-level rejection/warning applicability to a selected period cannot always be established, so results disclose that uncertainty.

Paginated drill-down returns transaction IDs and source file/row numbers. An optional fingerprint detects changed data or classifications. Classification edits immediately affect past reports; response snapshots expose the classification used, but historical versions are not persisted.

The contract is independent of Streamlit and financial routes. Future FP&A, reconciliation, anomaly, credit, or agent modules can reuse evidence and availability fields without implementing those modules now. See [full JSON examples](financial-result-examples.json).

### Current limitations

Classification and arithmetic operate on an in-memory company/currency/date-bounded population. Very large histories may require repository aggregation and database pagination in a later performance milestone. Results do not certify period completeness, and no materiality threshold is applied automatically.
