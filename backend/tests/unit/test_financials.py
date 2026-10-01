import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core.financial import (
    CATEGORIES,
    FinancialStatement,
    normalize_account_name,
)
from backend.app.repositories.financials import TransactionData
from backend.app.schemas.accounts import AccountCreate, AccountRead
from backend.app.schemas.financials import FinancialResult, PeriodSelection
from backend.app.services.calculations import (
    RATIOS,
    average_balance,
    calculate_ratio,
    capital_employed,
    signed_amount,
)
from backend.app.services.classification import classify_transactions
from backend.app.services.financial_engine import FinancialEngine
from backend.app.services.normalization import validate_table
from backend.app.services.parsing import parse_file
from backend.app.services.periods import ReportingCalendar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EXPECTED_PNL = {
    "operating_revenue": "100000.00",
    "cogs": "40000.00",
    "gross_profit": "60000.00",
    "employee_cost": "20000.00",
    "other_operating_expense": "10000.00",
    "ebitda": "30000.00",
    "depreciation": "5000.00",
    "ebit": "25000.00",
    "other_income": "2000.00",
    "finance_cost": "1000.00",
    "pbt": "26000.00",
    "tax": "6500.00",
    "pat": "19500.00",
}
EXPECTED_MARGINS = {
    "gross_margin": "60.0000",
    "ebitda_margin": "30.0000",
    "ebit_margin": "25.0000",
    "pat_margin": "19.5000",
}


def account(
    category: str,
    *,
    identifier: int = 1,
    code: str = "001",
    name: str = "Cash",
    company_id: int = 1,
) -> AccountRead:
    definition = CATEGORIES[category]
    return AccountRead(
        id=identifier,
        company_id=company_id,
        account_code=code,
        account_name=name,
        account_type=definition.account_type,
        financial_statement=definition.statement,
        financial_category=category,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def row(
    identifier: int = 1,
    *,
    code: str | None = "001",
    name: str | None = "Cash",
    debit: str = "10",
    credit: str = "0",
    day: date = date(2026, 4, 15),
) -> TransactionData:
    return TransactionData(
        id=identifier,
        company_id=1,
        transaction_date=day,
        account_code=code,
        account_name=name,
        debit=Decimal(debit),
        credit=Decimal(credit),
        currency="INR",
        source_file_id=1,
        source_row_number=identifier + 1,
        filename="synthetic.csv",
        sha256="a" * 64,
        error_row_count=0,
        warning_row_count=0,
    )


def engine(
    rows: list[TransactionData],
    accounts: list[AccountRead],
    selection: PeriodSelection | None = None,
) -> FinancialEngine:
    return FinancialEngine(
        1,
        "INR",
        ReportingCalendar().resolve(selection or PeriodSelection(fiscal_year=2026)),
        accounts,
        rows,
    )


def synthetic_engine(selection: PeriodSelection | None = None) -> FinancialEngine:
    payloads = json.loads((FIXTURES / "financial_accounts.json").read_text())
    accounts = [
        AccountRead(
            **payload,
            id=index,
            company_id=1,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for index, payload in enumerate(payloads, start=1)
    ]
    content = (FIXTURES / "financial_gl.csv").read_bytes()
    validated = validate_table(parse_file("financial_gl.csv", content, None), "INR")
    assert validated.report.error_row_count == 0
    assert validated.report.warning_row_count == 0
    assert validated.report.controls[0].balanced
    rows = [
        row(
            index,
            code=entry.account_code,
            name=entry.account_name,
            debit=str(entry.debit),
            credit=str(entry.credit),
            day=entry.transaction_date,
        )
        for index, entry in enumerate(validated.rows, start=1)
    ]
    if selection is not None:
        end = ReportingCalendar().resolve(selection).end_date
        rows = [entry for entry in rows if entry.transaction_date <= end]
    return engine(rows, accounts, selection)


def test_exact_annual_acceptance_and_margins() -> None:
    report_engine = synthetic_engine()
    pnl = report_engine.pnl()
    assert {key: pnl[key].value for key in EXPECTED_PNL} == {
        key: Decimal(value) for key, value in EXPECTED_PNL.items()
    }
    assert all(pnl[key].status == "calculated" for key in EXPECTED_PNL)
    ratios = report_engine.ratios(pnl)
    assert {key: ratios[key].value for key in EXPECTED_MARGINS} == {
        key: Decimal(value) for key, value in EXPECTED_MARGINS.items()
    }
    assert pnl["pat"].transaction_count == 32
    assert sum(source.transaction_count for source in pnl["pat"].source_files) == 32
    assert ratios["gross_margin"].transaction_count == 8


@pytest.mark.parametrize(
    ("selection", "start", "end"),
    [
        (PeriodSelection(fiscal_year=2026), date(2026, 4, 1), date(2027, 3, 31)),
        (
            PeriodSelection(fiscal_year=2026, period_type="quarter", quarter=4),
            date(2027, 1, 1),
            date(2027, 3, 31),
        ),
        (
            PeriodSelection(fiscal_year=2026, period_type="month", month=1),
            date(2027, 1, 1),
            date(2027, 1, 31),
        ),
        (
            PeriodSelection(fiscal_year=2023, period_type="month", month=2),
            date(2024, 2, 1),
            date(2024, 2, 29),
        ),
    ],
)
def test_fiscal_periods(selection: PeriodSelection, start: date, end: date) -> None:
    period = ReportingCalendar().resolve(selection)
    assert (period.start_date, period.end_date) == (start, end)
    assert period.day_count == (end - start).days + 1


def test_configurable_calendar_and_period_validation() -> None:
    assert ReportingCalendar(1).resolve(
        PeriodSelection(fiscal_year=2026)
    ).end_date == date(2026, 12, 31)
    assert ReportingCalendar().fiscal_year_for(date(2027, 3, 31)) == 2026
    assert ReportingCalendar().fiscal_year_for(date(2027, 4, 1)) == 2027
    for payload in (
        {"period_type": "quarter"},
        {"month": 1},
        {"period_type": "month", "month": 1, "quarter": 1},
    ):
        with pytest.raises(ValidationError):
            PeriodSelection(fiscal_year=2026, **payload)


def test_period_activity_and_cumulative_are_different() -> None:
    quarter = synthetic_engine(
        PeriodSelection(fiscal_year=2026, period_type="quarter", quarter=4)
    )
    assert quarter.pnl()["operating_revenue"].value == Decimal("25000")
    assert quarter.pnl()["pat"].value == Decimal("4875")
    assert quarter.balance_sheet()["trade_receivables"].value == Decimal("110000")
    assert (
        quarter.balance_sheet()[
            "trade_receivables"
        ].calculation_basis.population_scope.start_date
        is None
    )


def test_name_matching_code_priority_and_company_boundary() -> None:
    cash = account("cash")
    assert normalize_account_name("  CASH   Ledger ") == "cash ledger"
    matches = classify_transactions(
        [row(code=None, name=" cash "), row(2, code="missing", name="Cash")], [cash]
    )
    assert matches[0].match_method == "name"
    assert matches[1].exclusion_reason == "UNMATCHED_ACCOUNT_CODE"
    ambiguous = classify_transactions(
        [row(code=None)],
        [cash, account("cash", identifier=2, code="002", name=" CASH ")],
    )
    assert ambiguous[0].exclusion_reason == "AMBIGUOUS_ACCOUNT_NAME"
    foreign = account("cash", company_id=2)
    assert classify_transactions([row()], [foreign])[0].account is None
    assert classify_transactions([row(code="1")], [cash])[0].account is None


def test_classifications_and_cash_flow_exclusion() -> None:
    with pytest.raises(ValidationError):
        AccountCreate.model_validate(
            {
                "account_code": "1",
                "account_name": "Cash",
                "account_type": "REVENUE",
                "financial_statement": "PROFIT_AND_LOSS",
                "financial_category": "cash",
            }
        )
    with pytest.raises(ValidationError):
        AccountCreate(account_code="1", account_name="Cash", financial_category="cash")
    cash = account("cash").model_copy(
        update={"financial_statement": FinancialStatement.CASH_FLOW}
    )
    result = engine([row()], [cash]).balance_sheet()["cash"]
    assert result.value is None
    assert any(w.code == "CASH_FLOW_CLASSIFICATION_EXCLUDED" for w in result.warnings)


@pytest.mark.parametrize(
    ("kind", "debit", "credit", "expected"),
    [
        ("REVENUE", "120", "100", "-20"),
        ("EXPENSE", "100", "140", "-40"),
        ("ASSET", "50", "80", "-30"),
        ("LIABILITY", "80", "50", "-30"),
        ("EQUITY", "80", "50", "-30"),
    ],
)
def test_contra_postings_preserve_negative_signs(
    kind: str, debit: str, credit: str, expected: str
) -> None:
    assert signed_amount(kind, Decimal(debit), Decimal(credit)) == Decimal(expected)


def test_loss_and_negative_margin() -> None:
    report = engine(
        [row(1, code="REV", debit="0", credit="100"), row(2, code="COGS", debit="120")],
        [
            account("operating_revenue", code="REV"),
            account("cogs", identifier=2, code="COGS"),
        ],
    )
    assert report.pnl()["gross_profit"].value == Decimal("-20")
    assert report.ratios(report.pnl())["gross_margin"].value == Decimal("-20.0000")
    reversed_cost = engine([row(debit="0", credit="40")], [account("cogs")])
    assert reversed_cost.pnl()["cogs"].value == Decimal("-40")
    assert engine([row(debit="0", credit="30")], [account("cash")]).balance_sheet()[
        "cash"
    ].value == Decimal("-30")


def test_absence_zero_optional_categories_and_unknown_net_zero() -> None:
    report = engine([row(1), row(2, debit="0", credit="10")], [account("cash")])
    bs = report.balance_sheet()
    assert bs["cash"].value == Decimal("0.00")
    assert bs["current_assets"].value == Decimal("0.00")
    assert bs["current_assets"].status == "incomplete"
    assert bs["inventory"].value is None
    assert "inventory" in bs["current_assets"].warnings[-1].categories
    assert report.pnl()["operating_revenue"].value is None
    assert report.pnl()["ebitda"].value is None
    unknown = engine(
        [
            row(1, code="UNKNOWN"),
            row(2, code="UNKNOWN", debit="0", credit="10"),
            row(3),
        ],
        [account("cash")],
    )
    subtotal = unknown.balance_sheet()["total_assets"]
    assert subtotal.value == Decimal("10")
    warning = next(w for w in subtotal.warnings if w.code == "UNMATCHED_ACCOUNT_CODE")
    assert warning.transaction_count == 2
    assert (warning.debit, warning.credit) == (Decimal("10"), Decimal("10"))
    assert (
        unknown.report("balance-sheet")
        .populations["activity_derived"]
        .excluded_transaction_count
        == 2
    )


def test_source_quality_warnings_and_inactive_accounts() -> None:
    cash = account("cash").model_copy(update={"is_active": False})
    result = engine(
        [replace(row(), error_row_count=1, warning_row_count=1)], [cash]
    ).balance_sheet()["cash"]
    assert result.value == Decimal("10")
    assert {warning.code for warning in result.warnings} >= {
        "SOURCE_ROWS_REJECTED",
        "SOURCE_ROW_WARNINGS",
        "INACTIVE_ACCOUNT_ACTIVITY",
    }
    assert result.source_files[0].error_row_count == 1


def test_balance_dependent_metrics_and_strict_credit_bases() -> None:
    report = synthetic_engine()
    ratios = report.ratios(report.pnl())
    for name, definition in RATIOS.items():
        if definition.verified_balances:
            assert ratios[name].value is None
            assert ratios[name].status == "unavailable"
            assert ratios[name].reason is not None
    assert (
        ratios["dso"].reason is not None
        and ratios["dso"].reason.code == "CREDIT_SALES_BASE_UNAVAILABLE"
    )
    assert (
        ratios["dpo"].reason is not None
        and ratios["dpo"].reason.code == "CREDIT_PURCHASES_BASE_UNAVAILABLE"
    )
    assert (
        calculate_ratio(
            "dso",
            {
                "operating_revenue": Decimal(100),
                "average_trade_receivables": Decimal(10),
            },
            365,
            balances_verified=True,
        ).value
        is None
    )
    assert (
        calculate_ratio(
            "dpo",
            {"cogs": Decimal(100), "average_trade_payables": Decimal(10)},
            365,
            balances_verified=True,
        ).value
        is None
    )
    metrics = report.metrics(report.pnl(), report.balance_sheet())
    assert metrics["net_working_capital"].value is None
    assert metrics["activity_derived_current_assets"].value is not None


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("gross_margin", "60"),
        ("ebitda_margin", "30"),
        ("ebit_margin", "25"),
        ("pat_margin", "19.5"),
        ("current_ratio", "2"),
        ("quick_ratio", "1.6"),
        ("debt_equity", "0.5"),
        ("roa", "19.5"),
        ("roe", "39"),
        ("roce", "31.25"),
        ("dso", "36.5"),
        ("dpo", "45.625"),
        ("inventory_days", "36.5"),
        ("cash_conversion_cycle", "27.375"),
    ],
)
def test_every_ratio_with_explicit_verified_inputs(metric: str, expected: str) -> None:
    inputs = {
        key: Decimal(value)
        for key, value in {
            "operating_revenue": "100000",
            "gross_profit": "60000",
            "ebitda": "30000",
            "ebit": "25000",
            "pat": "19500",
            "current_assets": "100000",
            "quick_assets": "80000",
            "current_liabilities": "50000",
            "inventory": "20000",
            "debt": "25000",
            "equity": "50000",
            "average_assets": "100000",
            "average_equity": "50000",
            "average_capital_employed": "80000",
            "average_trade_receivables": "10000",
            "credit_sales": "100000",
            "average_trade_payables": "5000",
            "credit_purchases": "40000",
            "average_inventory": "4000",
            "cogs": "40000",
            "dso": "36.5",
            "dpo": "45.625",
            "inventory_days": "36.5",
        }.items()
    }
    assert calculate_ratio(
        metric,
        inputs,
        365,
        balances_verified=True,
        credit_sales_reliable=True,
        credit_purchases_reliable=True,
    ).value == Decimal(expected)


@pytest.mark.parametrize("denominator", [Decimal("0"), Decimal("-1")])
def test_denominator_and_evidence_guards(denominator: Decimal) -> None:
    ratio = calculate_ratio(
        "gross_margin",
        {"gross_profit": Decimal(10), "operating_revenue": denominator},
        365,
    )
    assert ratio.value is None and ratio.reason is not None
    assert average_balance(Decimal(10), Decimal(20), verified=False) is None
    assert average_balance(Decimal(10), Decimal(20), verified=True) == Decimal(15)
    assert capital_employed(Decimal(100), Decimal(20), verified=True) == Decimal(80)


def test_contract_invariants_snapshot_and_reclassification() -> None:
    report = synthetic_engine().report("pnl")
    result = report.results["operating_revenue"]
    required = {
        "metric",
        "value",
        "status",
        "reason",
        "calculation_basis",
        "formula_version",
        "currency",
        "resolved_period",
        "contributing_accounts",
        "transaction_count",
        "source_files",
        "warnings",
    }
    assert required <= result.model_dump().keys()
    payload = result.model_dump()
    payload["status"] = "unavailable"
    with pytest.raises(ValidationError):
        FinancialResult.model_validate(payload)
    original = account("cash")
    before = engine([row()], [original])
    after = engine(
        [row()], [original.model_copy(update={"financial_category": "inventory"})]
    )
    assert before.balance_sheet()["cash"].value == Decimal(10)
    assert after.balance_sheet()["cash"].value is None
    assert after.balance_sheet()["inventory"].value == Decimal(10)
    assert before.fingerprint != after.fingerprint


def test_large_ratio_quantization_preserves_decimal_precision() -> None:
    result = calculate_ratio(
        "gross_margin",
        {"gross_profit": Decimal("1e25"), "operating_revenue": Decimal("0.01")},
        365,
    )
    assert result.value == Decimal("1e29")


def test_quick_ratio_requires_explicit_verified_quick_assets() -> None:
    result = calculate_ratio(
        "quick_ratio",
        {
            "current_assets": Decimal("100000"),
            "inventory": Decimal("20000"),
            "current_liabilities": Decimal("50000"),
        },
        365,
        balances_verified=True,
    )
    assert result.value is None
    assert result.reason is not None
    assert result.reason.code == "MISSING_REQUIRED_INPUTS"


@pytest.mark.parametrize(
    "outside_scope",
    [
        replace(row(), currency="USD"),
        replace(row(), company_id=2),
        replace(row(), transaction_date=date(2027, 4, 1)),
    ],
)
def test_engine_rejects_mixed_or_out_of_scope_population(
    outside_scope: TransactionData,
) -> None:
    with pytest.raises(ValueError, match="company, currency, and end date"):
        engine([row(), outside_scope], [account("cash")])
