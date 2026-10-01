from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext

from backend.app.core.financial import AccountType
from backend.app.schemas.financials import ResultReason


def signed_amount(account_type: str, debit: Decimal, credit: Decimal) -> Decimal:
    if account_type in {AccountType.REVENUE, AccountType.LIABILITY, AccountType.EQUITY}:
        return credit - debit
    if account_type in {AccountType.EXPENSE, AccountType.ASSET}:
        return debit - credit
    raise ValueError("Cannot calculate a normal balance for an unknown account type")


PNL_FORMULAS: dict[str, tuple[tuple[str, int], ...]] = {
    "gross_profit": (("operating_revenue", 1), ("cogs", -1)),
    "operating_expenses": (("employee_cost", 1), ("other_operating_expense", 1)),
    "ebitda": (("gross_profit", 1), ("operating_expenses", -1)),
    "ebit": (("ebitda", 1), ("depreciation", -1)),
    "pbt": (("ebit", 1), ("other_income", 1), ("finance_cost", -1)),
    "pat": (("pbt", 1), ("tax", -1)),
}
CURRENT_ASSETS = ("cash", "trade_receivables", "inventory", "other_current_assets")
ASSETS = (*CURRENT_ASSETS, "fixed_assets", "other_non_current_assets")
CURRENT_LIABILITIES = ("trade_payables", "short_term_debt", "other_current_liabilities")
LIABILITIES = (*CURRENT_LIABILITIES, "long_term_debt", "other_non_current_liabilities")
EQUITY = ("share_capital", "reserves", "retained_earnings")
BS_GROUPS = {
    "current_assets": CURRENT_ASSETS,
    "total_assets": ASSETS,
    "current_liabilities": CURRENT_LIABILITIES,
    "debt": ("short_term_debt", "long_term_debt"),
    "other_liabilities": ("other_current_liabilities", "other_non_current_liabilities"),
    "equity": EQUITY,
    "total_liabilities_and_equity": (*LIABILITIES, *EQUITY),
}


@dataclass(frozen=True)
class RatioDefinition:
    numerator: str
    denominator: str | None
    inputs: tuple[str, ...]
    formula: str
    unit: str
    verified_balances: bool = False
    credit_sales: bool = False
    credit_purchases: bool = False


RATIOS = {
    name: RatioDefinition(
        numerator,
        "operating_revenue",
        (numerator, "operating_revenue"),
        f"{numerator} / operating_revenue * 100",
        "percent",
    )
    for name, numerator in (
        ("gross_margin", "gross_profit"),
        ("ebitda_margin", "ebitda"),
        ("ebit_margin", "ebit"),
        ("pat_margin", "pat"),
    )
} | {
    "current_ratio": RatioDefinition(
        "current_assets",
        "current_liabilities",
        ("current_assets", "current_liabilities"),
        "verified_current_assets / verified_current_liabilities",
        "times",
        True,
    ),
    "quick_ratio": RatioDefinition(
        "quick_assets",
        "current_liabilities",
        ("quick_assets", "current_liabilities"),
        "verified_quick_assets / verified_current_liabilities",
        "times",
        True,
    ),
    "debt_equity": RatioDefinition(
        "debt",
        "equity",
        ("debt", "equity"),
        "verified_debt / verified_equity",
        "times",
        True,
    ),
    "roa": RatioDefinition(
        "pat",
        "average_assets",
        ("pat", "average_assets"),
        "PAT / verified_average_assets * 100",
        "percent",
        True,
    ),
    "roe": RatioDefinition(
        "pat",
        "average_equity",
        ("pat", "average_equity"),
        "PAT / verified_average_equity * 100",
        "percent",
        True,
    ),
    "roce": RatioDefinition(
        "ebit",
        "average_capital_employed",
        ("ebit", "average_capital_employed"),
        "EBIT / verified_average_capital_employed * 100",
        "percent",
        True,
    ),
    "dso": RatioDefinition(
        "average_trade_receivables",
        "credit_sales",
        ("average_trade_receivables", "credit_sales"),
        "verified_average_trade_receivables / reliable_credit_sales * period_days",
        "days",
        True,
        True,
    ),
    "dpo": RatioDefinition(
        "average_trade_payables",
        "credit_purchases",
        ("average_trade_payables", "credit_purchases"),
        "verified_average_trade_payables / reliable_credit_purchases * period_days",
        "days",
        True,
        False,
        True,
    ),
    "inventory_days": RatioDefinition(
        "average_inventory",
        "cogs",
        ("average_inventory", "cogs"),
        "verified_average_inventory / COGS * period_days",
        "days",
        True,
    ),
    "cash_conversion_cycle": RatioDefinition(
        "dso",
        None,
        ("dso", "inventory_days", "dpo"),
        "DSO + inventory_days - DPO",
        "days",
        True,
        True,
        True,
    ),
}


@dataclass(frozen=True)
class RatioCalculation:
    value: Decimal | None
    reason: ResultReason | None


def average_balance(
    opening: Decimal | None, closing: Decimal | None, *, verified: bool
) -> Decimal | None:
    if not verified or opening is None or closing is None:
        return None
    return (opening + closing) / Decimal(2)


def capital_employed(
    assets: Decimal | None, current_liabilities: Decimal | None, *, verified: bool
) -> Decimal | None:
    if not verified or assets is None or current_liabilities is None:
        return None
    return assets - current_liabilities


def calculate_ratio(
    metric: str,
    inputs: Mapping[str, Decimal | None],
    period_days: int,
    *,
    balances_verified: bool = False,
    credit_sales_reliable: bool = False,
    credit_purchases_reliable: bool = False,
) -> RatioCalculation:
    definition = RATIOS[metric]

    def unavailable(code: str, message: str) -> RatioCalculation:
        return RatioCalculation(None, ResultReason(code=code, message=message))

    if definition.credit_sales and not credit_sales_reliable:
        return unavailable(
            "CREDIT_SALES_BASE_UNAVAILABLE",
            "Reliable credit sales are unavailable; revenue is not a substitute.",
        )
    if definition.credit_purchases and not credit_purchases_reliable:
        return unavailable(
            "CREDIT_PURCHASES_BASE_UNAVAILABLE",
            "Reliable credit purchases are unavailable; COGS is not a substitute.",
        )
    if definition.verified_balances and not balances_verified:
        return unavailable(
            "VERIFIED_BALANCES_UNAVAILABLE",
            (
                "Verified opening/closing balances and supporting coverage "
                "are unavailable."
            ),
        )
    missing = [name for name in definition.inputs if inputs.get(name) is None]
    if missing:
        return unavailable(
            "MISSING_REQUIRED_INPUTS",
            f"Required inputs are unavailable: {', '.join(missing)}",
        )
    values = {name: value for name, value in inputs.items() if value is not None}
    if any(not value.is_finite() for value in values.values()):
        return unavailable("INVALID_INPUT", "Ratio inputs must be finite.")
    if metric == "cash_conversion_cycle":
        value = values["dso"] + values["inventory_days"] - values["dpo"]
    else:
        assert definition.denominator is not None
        denominator = values[definition.denominator]
        if denominator <= 0:
            return unavailable(
                "NON_POSITIVE_DENOMINATOR",
                "The required denominator is zero or negative.",
            )
        numerator = values[definition.numerator]
        with localcontext() as context:
            context.prec = 38
            value = numerator / denominator
            if definition.unit == "percent":
                value *= Decimal(100)
            elif definition.unit == "days":
                if period_days <= 0:
                    return unavailable(
                        "INVALID_PERIOD", "Period must contain at least one day."
                    )
                value *= Decimal(period_days)
    with localcontext() as context:
        context.prec = max(38, value.adjusted() + 6)
        return RatioCalculation(value.quantize(Decimal("0.0001")), None)
