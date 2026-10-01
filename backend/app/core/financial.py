from dataclasses import dataclass
from enum import StrEnum


class AccountType(StrEnum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class FinancialStatement(StrEnum):
    PROFIT_AND_LOSS = "PROFIT_AND_LOSS"
    BALANCE_SHEET = "BALANCE_SHEET"
    CASH_FLOW = "CASH_FLOW"


@dataclass(frozen=True)
class CategoryDefinition:
    name: str
    account_type: AccountType
    statement: FinancialStatement


_CATEGORY_GROUPS = {
    AccountType.REVENUE: ("operating_revenue", "other_income"),
    AccountType.EXPENSE: (
        "cogs",
        "employee_cost",
        "other_operating_expense",
        "depreciation",
        "finance_cost",
        "tax",
    ),
    AccountType.ASSET: (
        "cash",
        "trade_receivables",
        "inventory",
        "other_current_assets",
        "fixed_assets",
        "other_non_current_assets",
    ),
    AccountType.LIABILITY: (
        "trade_payables",
        "short_term_debt",
        "long_term_debt",
        "other_current_liabilities",
        "other_non_current_liabilities",
    ),
    AccountType.EQUITY: ("share_capital", "reserves", "retained_earnings"),
}

# Extend this registry deliberately with compatible categories and methodology tests.
CATEGORIES = {
    name: CategoryDefinition(
        name,
        account_type,
        FinancialStatement.PROFIT_AND_LOSS
        if account_type in {AccountType.REVENUE, AccountType.EXPENSE}
        else FinancialStatement.BALANCE_SHEET,
    )
    for account_type, names in _CATEGORY_GROUPS.items()
    for name in names
}


def validate_classification(
    account_type: AccountType | None,
    statement: FinancialStatement | None,
    category: str | None,
) -> None:
    if account_type is None and statement is None and category is None:
        return
    if account_type is None or statement is None or category is None:
        raise ValueError(
            "Assign all three classification fields or leave all unassigned"
        )
    definition = CATEGORIES.get(category)
    if definition is None:
        raise ValueError("Unknown financial category; select one from the catalog")
    if definition.account_type != account_type:
        raise ValueError("Financial category is incompatible with the account type")
    if statement != FinancialStatement.CASH_FLOW and statement != definition.statement:
        raise ValueError("Financial statement is incompatible with the account type")


def normalize_account_name(name: str) -> str:
    return " ".join(name.split()).casefold()
