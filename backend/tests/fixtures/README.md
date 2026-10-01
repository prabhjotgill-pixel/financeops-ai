# Synthetic fixtures

All files in this directory contain synthetic test data.

Milestone 1 fixtures cover clean and alias GL columns, invalid rows, duplicates, and multiple Excel worksheets.

Milestone 2 uses `financial_accounts.json` (22 classified accounts) and `financial_gl.csv` (78 balanced INR journal lines). Four quarters of FY 2026-27 produce operating revenue 100,000, COGS 40,000, employee cost 20,000, other operating expense 10,000, depreciation 5,000, other income 2,000, finance cost 1,000, and tax 6,500. Expected PAT is 19,500; margins are 60%, 30%, 25%, and 19.5%.

The recorded starting entries exercise cumulative Balance Sheet activity. They do not establish verified opening/closing coverage in the application. Balance-dependent ratios, DSO, and DPO remain unavailable.
