import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal

from backend.app.core.financial import CATEGORIES, FinancialStatement
from backend.app.repositories.financials import TransactionData
from backend.app.schemas.accounts import AccountRead
from backend.app.schemas.financials import (
    AccountContribution,
    CalculationBasis,
    DataWarning,
    FinancialReport,
    FinancialResult,
    PopulationScope,
    PopulationSummary,
    ReportingPeriod,
    ResultReason,
    SourceFileReference,
    Status,
)
from backend.app.services.calculations import (
    BS_GROUPS,
    PNL_FORMULAS,
    RATIOS,
    calculate_ratio,
    signed_amount,
)
from backend.app.services.classification import (
    ClassifiedTransaction,
    classify_transactions,
)

ZERO = Decimal("0.00")


class FinancialEngine:
    """Pure reporting over an explicit stored population and classification snapshot."""

    def __init__(
        self,
        company_id: int,
        currency: str,
        period: ReportingPeriod,
        accounts: Sequence[AccountRead],
        rows: Sequence[TransactionData],
    ) -> None:
        if any(
            row.company_id != company_id
            or row.currency != currency
            or row.transaction_date > period.end_date
            for row in rows
        ):
            raise ValueError(
                "Financial population must match company, currency, and end date"
            )
        if any(account.company_id != company_id for account in accounts):
            raise ValueError("Classification snapshot must belong to the company")
        self.company_id, self.currency, self.period = company_id, currency, period
        self.accounts = list(accounts)
        self.cumulative = classify_transactions(rows, accounts)
        self.activity = [
            row
            for row in self.cumulative
            if row.transaction.transaction_date >= period.start_date
        ]
        snapshot = {
            "accounts": [account.model_dump(mode="json") for account in accounts],
            "transactions": [asdict(row) for row in rows],
        }
        self.fingerprint = hashlib.sha256(
            json.dumps(snapshot, default=str, sort_keys=True).encode()
        ).hexdigest()

    def _population(self, kind: str) -> list[ClassifiedTransaction]:
        return self.activity if kind == "period_activity" else self.cumulative

    def basis(
        self,
        kind: str,
        formula: str,
        categories: list[str],
        inputs: list[str] | None = None,
    ) -> CalculationBasis:
        return CalculationBasis(
            kind=kind,
            formula=formula,
            categories=categories,
            input_metrics=inputs or [],
            population_scope=PopulationScope(
                company_id=self.company_id,
                currency=self.currency,
                start_date=self.period.start_date
                if kind == "period_activity"
                else None,
                end_date=self.period.end_date,
                population_fingerprint=self.fingerprint,
            ),
        )

    def _warnings(self, kind: str) -> list[DataWarning]:
        population = self._population(kind)
        warnings = [
            DataWarning(
                code="PERIOD_COVERAGE_UNVERIFIED"
                if kind == "period_activity"
                else "OPENING_BALANCES_UNVERIFIED",
                message="Full reporting-period coverage is not verified."
                if kind == "period_activity"
                else (
                    "Loaded cumulative activity does not establish verified "
                    "opening or closing balances."
                ),
                scope=kind,
            )
        ]
        exclusions = sorted(
            {row.exclusion_reason for row in population if row.exclusion_reason}
        )
        for code in exclusions:
            excluded = [
                row.transaction for row in population if row.exclusion_reason == code
            ]
            warnings.append(
                DataWarning(
                    code=code,
                    message=(
                        "Transactions are excluded from classified financial "
                        "amounts; materiality has not been assessed."
                    ),
                    scope=kind,
                    transaction_count=len(excluded),
                    source_file_ids=sorted({row.source_file_id for row in excluded}),
                    debit=sum((row.debit for row in excluded), ZERO),
                    credit=sum((row.credit for row in excluded), ZERO),
                )
            )
        for code, attribute, message in (
            (
                "SOURCE_ROWS_REJECTED",
                "error_row_count",
                (
                    "Source files contain rejected rows; their applicability to "
                    "this period cannot be established."
                ),
            ),
            (
                "SOURCE_ROW_WARNINGS",
                "warning_row_count",
                (
                    "Source files contain row warnings, including possible "
                    "duplicate transactions."
                ),
            ),
        ):
            affected = [
                row.transaction
                for row in population
                if getattr(row.transaction, attribute) > 0
            ]
            if affected:
                warnings.append(
                    DataWarning(
                        code=code,
                        message=message,
                        scope=kind,
                        transaction_count=len(affected),
                        source_file_ids=sorted(
                            {row.source_file_id for row in affected}
                        ),
                    )
                )
        inactive = [
            row.transaction
            for row in population
            if row.account is not None and not row.account.is_active
        ]
        if inactive:
            warnings.append(
                DataWarning(
                    code="INACTIVE_ACCOUNT_ACTIVITY",
                    message=(
                        "Historical activity retains the current classification of "
                        "inactive accounts."
                    ),
                    scope=kind,
                    transaction_count=len(inactive),
                    source_file_ids=sorted({row.source_file_id for row in inactive}),
                )
            )
        return warnings

    def selected(
        self, kind: str, categories: Sequence[str]
    ) -> list[ClassifiedTransaction]:
        return [
            row
            for row in self._population(kind)
            if row.exclusion_reason is None
            and row.account is not None
            and row.account.financial_category in categories
        ]

    def _evidence(
        self, rows: list[ClassifiedTransaction]
    ) -> tuple[list[AccountContribution], list[SourceFileReference]]:
        accounts: dict[int, list[ClassifiedTransaction]] = {}
        files: dict[int, list[TransactionData]] = {}
        for row in rows:
            assert row.account is not None
            accounts.setdefault(row.account.id, []).append(row)
            files.setdefault(row.transaction.source_file_id, []).append(row.transaction)
        contributions = []
        for _account_id, group in sorted(accounts.items()):
            account = group[0].account
            assert (
                account is not None
                and account.account_type is not None
                and account.financial_statement is not None
                and account.financial_category is not None
            )
            debit = sum((row.transaction.debit for row in group), ZERO)
            credit = sum((row.transaction.credit for row in group), ZERO)
            contributions.append(
                AccountContribution(
                    account_id=account.id,
                    account_code=account.account_code,
                    account_name=account.account_name,
                    account_type=account.account_type,
                    financial_statement=account.financial_statement,
                    financial_category=account.financial_category,
                    is_active=account.is_active,
                    match_methods=sorted(
                        {row.match_method for row in group if row.match_method}
                    ),
                    debit=debit,
                    credit=credit,
                    signed_amount=signed_amount(account.account_type, debit, credit),
                    transaction_count=len(group),
                    source_file_ids=sorted(
                        {row.transaction.source_file_id for row in group}
                    ),
                )
            )
        sources = [
            SourceFileReference(
                source_file_id=file_id,
                filename=group[0].filename,
                sha256=group[0].sha256,
                transaction_count=len(group),
                warning_row_count=group[0].warning_row_count,
                error_row_count=group[0].error_row_count,
            )
            for file_id, group in sorted(files.items())
        ]
        return contributions, sources

    def _result(
        self,
        metric: str,
        value: Decimal | None,
        kind: str,
        formula: str,
        categories: list[str],
        *,
        reason: ResultReason | None = None,
        inputs: list[str] | None = None,
        unit: str = "amount",
        extra_warnings: list[DataWarning] | None = None,
    ) -> FinancialResult:
        warnings = self._warnings(kind) + (extra_warnings or [])
        rows = self.selected(kind, categories)
        contributions, sources = self._evidence(rows)
        status: Status = "calculated"
        if value is None:
            status = "unavailable"
            reason = reason or ResultReason(
                code="NO_OBSERVED_ACTIVITY",
                message=(
                    "No qualifying transaction population was observed; zero is "
                    "not inferred."
                ),
            )
        elif kind != "period_activity":
            status = "incomplete"
            reason = reason or ResultReason(
                code="ACTIVITY_DERIVED_SUBTOTAL",
                message=(
                    "Observed classified activity; verified opening and closing "
                    "balances are unavailable."
                ),
            )
        elif any(
            warning.code
            not in {"PERIOD_COVERAGE_UNVERIFIED", "INACTIVE_ACCOUNT_ACTIVITY"}
            for warning in warnings
        ):
            status = "incomplete"
            reason = reason or ResultReason(
                code="PARTIAL_CLASSIFIED_POPULATION",
                message=(
                    "Excluded transactions or source-file quality issues can "
                    "affect this result."
                ),
            )
        return FinancialResult(
            company_id=self.company_id,
            metric=metric,
            value=value,
            unit=unit,
            status=status,
            reason=reason,
            calculation_basis=self.basis(kind, formula, categories, inputs),
            currency=self.currency,
            resolved_period=self.period,
            contributing_accounts=contributions,
            transaction_count=len(rows),
            source_files=sources,
            warnings=warnings,
        )

    def pnl(self) -> dict[str, FinancialResult]:
        results: dict[str, FinancialResult] = {}
        for name, definition in CATEGORIES.items():
            if definition.statement != FinancialStatement.PROFIT_AND_LOSS:
                continue
            rows = self.selected("period_activity", [name])
            value = (
                sum(
                    (
                        signed_amount(
                            row.account.account_type or "",
                            row.transaction.debit,
                            row.transaction.credit,
                        )
                        for row in rows
                        if row.account is not None
                    ),
                    ZERO,
                )
                if rows
                else None
            )
            formula = (
                "sum(credit - debit)"
                if definition.account_type == "REVENUE"
                else "sum(debit - credit)"
            )
            results[name] = self._result(
                name, value, "period_activity", formula, [name]
            )
        for metric, components in PNL_FORMULAS.items():
            missing = [
                name for name, _sign in components if results[name].value is None
            ]
            value = (
                None
                if missing
                else sum(
                    (
                        value * sign
                        for name, sign in components
                        if (value := results[name].value) is not None
                    ),
                    ZERO,
                )
            )
            categories = sorted(
                {
                    category
                    for name, _sign in components
                    for category in results[name].calculation_basis.categories
                }
            )
            reason = (
                ResultReason(
                    code="MISSING_REQUIRED_INPUTS",
                    message=(
                        "Required P&L inputs are unavailable: " + ", ".join(missing)
                    ),
                )
                if missing
                else None
            )
            formula = " ".join(
                f"{'+' if sign > 0 else '-'} {name}" for name, sign in components
            ).removeprefix("+ ")
            results[metric] = self._result(
                metric,
                value,
                "period_activity",
                formula,
                categories,
                reason=reason,
                inputs=[name for name, _sign in components],
            )
        return results

    def balance_sheet(self) -> dict[str, FinancialResult]:
        results: dict[str, FinancialResult] = {}
        for name, definition in CATEGORIES.items():
            if definition.statement != FinancialStatement.BALANCE_SHEET:
                continue
            rows = self.selected("activity_derived", [name])
            value = (
                sum(
                    (
                        signed_amount(
                            row.account.account_type or "",
                            row.transaction.debit,
                            row.transaction.credit,
                        )
                        for row in rows
                        if row.account is not None
                    ),
                    ZERO,
                )
                if rows
                else None
            )
            formula = (
                "sum(debit - credit)"
                if definition.account_type == "ASSET"
                else "sum(credit - debit)"
            )
            results[name] = self._result(
                name, value, "activity_derived", formula, [name]
            )
        for metric, categories in BS_GROUPS.items():
            observed = [name for name in categories if results[name].value is not None]
            absent = [name for name in categories if results[name].value is None]
            value = (
                sum(
                    (
                        value
                        for name in observed
                        if (value := results[name].value) is not None
                    ),
                    ZERO,
                )
                if observed
                else None
            )
            warnings = (
                [
                    DataWarning(
                        code="OPTIONAL_CATEGORIES_NOT_OBSERVED",
                        message=(
                            "These categories have no observed classified activity and "
                            "were not assumed to be zero."
                        ),
                        scope="activity_derived",
                        categories=absent,
                    )
                ]
                if absent
                else []
            )
            results[metric] = self._result(
                metric,
                value,
                "activity_derived",
                "sum(observed classified category amounts)",
                list(categories),
                inputs=observed,
                extra_warnings=warnings,
            )
        return results

    def ratios(self, pnl: dict[str, FinancialResult]) -> dict[str, FinancialResult]:
        results: dict[str, FinancialResult] = {}
        inputs = {name: result.value for name, result in pnl.items()}
        for name, definition in RATIOS.items():
            calculation = calculate_ratio(name, inputs, self.period.day_count)
            categories = (
                sorted(
                    {
                        category
                        for key in definition.inputs
                        if key in pnl
                        for category in pnl[key].calculation_basis.categories
                    }
                )
                if not definition.verified_balances
                else []
            )
            warnings = []
            if definition.verified_balances:
                warnings.append(
                    DataWarning(
                        code="VERIFIED_BALANCES_UNAVAILABLE",
                        message=(
                            "Activity-derived amounts cannot substitute for verified "
                            "balance inputs."
                        ),
                        scope="verified_balance",
                    )
                )
            if definition.credit_sales:
                warnings.append(
                    DataWarning(
                        code="CREDIT_SALES_NOT_IDENTIFIED",
                        message=(
                            "Operating revenue is not used as a "
                            "credit-sales substitute."
                        ),
                        scope="verified_balance",
                    )
                )
            if definition.credit_purchases:
                warnings.append(
                    DataWarning(
                        code="CREDIT_PURCHASES_NOT_IDENTIFIED",
                        message="COGS is not used as a credit-purchases substitute.",
                        scope="verified_balance",
                    )
                )
            results[name] = self._result(
                name,
                calculation.value,
                "verified_balance"
                if definition.verified_balances
                else "period_activity",
                definition.formula,
                categories,
                reason=calculation.reason,
                inputs=list(definition.inputs),
                unit=definition.unit,
                extra_warnings=warnings,
            )
        return results

    def metrics(
        self, pnl: dict[str, FinancialResult], balance_sheet: dict[str, FinancialResult]
    ) -> dict[str, FinancialResult]:
        results = {
            name: pnl[name]
            for name in (
                "operating_revenue",
                "gross_profit",
                "ebitda",
                "ebit",
                "pbt",
                "pat",
            )
        }
        for name in (
            "current_assets",
            "current_liabilities",
            "cash",
            "trade_receivables",
            "inventory",
            "trade_payables",
        ):
            result = balance_sheet[name].model_copy(deep=True)
            result.metric = f"activity_derived_{name}"
            results[result.metric] = result
        for name, formula in {
            "current_assets": "verified closing current assets",
            "current_liabilities": "verified closing current liabilities",
            "net_working_capital": (
                "verified_current_assets - verified_current_liabilities"
            ),
            "operating_working_capital": (
                "verified_receivables + verified_inventory - verified_payables"
            ),
        }.items():
            results[name] = self._result(
                name,
                None,
                "verified_balance",
                formula,
                [],
                reason=ResultReason(
                    code="VERIFIED_BALANCES_UNAVAILABLE",
                    message=(
                        "Verified closing balances and supporting coverage "
                        "are unavailable."
                    ),
                ),
            )
        return results

    def report(self, report_type: str) -> FinancialReport:
        pnl = self.pnl()
        if report_type == "pnl":
            results = pnl
        elif report_type == "balance-sheet":
            results = self.balance_sheet()
        elif report_type == "ratios":
            results = self.ratios(pnl)
        elif report_type == "metrics":
            results = self.metrics(pnl, self.balance_sheet())
        else:
            raise ValueError("Unknown financial report")
        populations = {}
        for name, rows in (
            ("period_activity", self.activity),
            ("activity_derived", self.cumulative),
        ):
            excluded = [
                row.transaction for row in rows if row.exclusion_reason is not None
            ]
            populations[name] = PopulationSummary(
                transaction_count=len(rows),
                excluded_transaction_count=len(excluded),
                first_transaction_date=min(
                    (row.transaction.transaction_date for row in rows), default=None
                ),
                last_transaction_date=max(
                    (row.transaction.transaction_date for row in rows), default=None
                ),
                excluded_debit=sum((row.debit for row in excluded), ZERO),
                excluded_credit=sum((row.credit for row in excluded), ZERO),
            )
        warnings_by_key = {
            warning.model_dump_json(): warning
            for result in results.values()
            for warning in result.warnings
        }
        return FinancialReport(
            company_id=self.company_id,
            currency=self.currency,
            resolved_period=self.period,
            report_type=report_type,
            population_fingerprint=self.fingerprint,
            classifications=self.accounts,
            populations=populations,
            results=results,
            warnings=list(warnings_by_key.values()),
        )
