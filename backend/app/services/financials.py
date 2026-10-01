from typing import Literal

from sqlalchemy.orm import Session

from backend.app.core.errors import DomainError
from backend.app.repositories.accounts import AccountRepository
from backend.app.repositories.financials import FinancialRepository
from backend.app.schemas.accounts import AccountRead
from backend.app.schemas.financials import (
    AvailablePeriods,
    DataWarning,
    DrillDown,
    FinancialReport,
    PeriodSelection,
    PeriodSummaries,
    PeriodType,
    TransactionTrace,
)
from backend.app.services.accounts import AccountService
from backend.app.services.financial_engine import FinancialEngine
from backend.app.services.periods import ReportingCalendar

ReportType = Literal["pnl", "balance-sheet", "metrics", "ratios"]


class FinancialService:
    def __init__(
        self,
        calendar: ReportingCalendar | None = None,
        repository: FinancialRepository | None = None,
    ) -> None:
        self.calendar = calendar or ReportingCalendar()
        self.repository = repository or FinancialRepository()
        self.accounts = AccountService()

    def engine(
        self, session: Session, company_id: int, selection: PeriodSelection
    ) -> FinancialEngine:
        company = self.accounts.company(session, company_id)
        currency = selection.currency or company.currency
        period = self.calendar.resolve(selection)
        accounts = [
            AccountRead.model_validate(account)
            for account in AccountRepository().list(session, company_id)
        ]
        rows = self.repository.population(
            session, company_id, currency, period.end_date
        )
        return FinancialEngine(company_id, currency, period, accounts, rows)

    def report(
        self,
        session: Session,
        company_id: int,
        selection: PeriodSelection,
        report_type: ReportType,
    ) -> FinancialReport:
        engine = self.engine(session, company_id, selection)
        report = engine.report(report_type)
        others = sorted(
            {
                currency
                for day, currency in self.repository.dates_and_currencies(
                    session, company_id
                )
                if currency != engine.currency and day <= engine.period.end_date
            }
        )
        if others:
            warning = DataWarning(
                code="OTHER_CURRENCIES_EXCLUDED",
                message=(
                    f"Results use {engine.currency} only; no FX conversion. "
                    f"Other loaded currencies: {', '.join(others)}."
                ),
                scope="currency",
            )
            report.warnings.append(warning)
            for result in report.results.values():
                result.warnings.append(warning)
        return report

    def available_periods(
        self, session: Session, company_id: int, currency: str | None
    ) -> AvailablePeriods:
        company = self.accounts.company(session, company_id)
        dates = self.repository.dates_and_currencies(session, company_id)
        selected_currency = (currency or company.currency).upper()
        selected = [(day, code) for day, code in dates if code == selected_currency]
        months = sorted(
            {(self.calendar.fiscal_year_for(day), day.month) for day, _code in selected}
        )
        periods = [
            self.calendar.resolve(
                PeriodSelection(fiscal_year=year, period_type="month", month=month)
            )
            for year, month in months
        ]
        periods.sort(key=lambda period: period.start_date)
        return AvailablePeriods(
            company_id=company_id,
            financial_year_start_month=self.calendar.start_month,
            fiscal_years=sorted({year for year, _month in months}),
            currencies=sorted({code for _day, code in dates} | {company.currency}),
            periods=periods,
        )

    def summaries(
        self,
        session: Session,
        company_id: int,
        fiscal_year: int,
        period_type: PeriodType,
        currency: str | None,
    ) -> PeriodSummaries:
        selections = self.calendar.selections(fiscal_year, period_type, currency)
        return PeriodSummaries(
            company_id=company_id,
            fiscal_year=fiscal_year,
            period_type=period_type,
            reports=[
                self.report(session, company_id, selection, "pnl")
                for selection in selections
            ],
        )

    def drill_down(
        self,
        session: Session,
        company_id: int,
        selection: PeriodSelection,
        *,
        report_type: ReportType,
        metric: str | None,
        population: Literal["contributing", "excluded"],
        scope: Literal["period_activity", "activity_derived"],
        offset: int,
        limit: int,
        expected_fingerprint: str | None,
    ) -> DrillDown:
        engine = self.engine(session, company_id, selection)
        if expected_fingerprint and expected_fingerprint != engine.fingerprint:
            raise DomainError(
                409,
                "POPULATION_CHANGED",
                (
                    "The population or current classifications changed; refresh "
                    "the report."
                ),
            )
        if population == "contributing":
            if metric is None:
                raise DomainError(
                    422,
                    "METRIC_REQUIRED",
                    "Select a metric for contributing transaction drill-down",
                )
            report = engine.report(report_type)
            result = report.results.get(metric)
            if result is None:
                raise DomainError(
                    422, "UNKNOWN_METRIC", "Metric is not available in this report"
                )
            basis = result.calculation_basis
            rows = engine.selected(basis.kind, basis.categories)
        else:
            if metric is not None:
                raise DomainError(
                    422,
                    "INVALID_DRILLDOWN",
                    "Excluded populations use scope rather than a metric",
                )
            basis = engine.basis(scope, "excluded transaction population", [])
            source = (
                engine.activity if scope == "period_activity" else engine.cumulative
            )
            rows = [row for row in source if row.exclusion_reason is not None]
        traces = [
            TransactionTrace(
                transaction_id=row.transaction.id,
                transaction_date=row.transaction.transaction_date,
                company_id=company_id,
                source_file_id=row.transaction.source_file_id,
                source_row_number=row.transaction.source_row_number,
                account_code=row.transaction.account_code,
                account_name=row.transaction.account_name,
                debit=row.transaction.debit,
                credit=row.transaction.credit,
                currency=row.transaction.currency,
                matched_account=row.account,
                match_method=row.match_method,
                exclusion_reason=row.exclusion_reason,
            )
            for row in rows[offset : offset + limit]
        ]
        return DrillDown(
            company_id=company_id,
            currency=engine.currency,
            resolved_period=engine.period,
            metric=metric,
            calculation_basis=basis,
            population_fingerprint=engine.fingerprint,
            total=len(rows),
            offset=offset,
            limit=limit,
            transactions=traces,
        )
