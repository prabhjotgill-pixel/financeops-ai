from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.schemas.accounts import AccountRead

PeriodType = Literal["month", "quarter", "year"]
Status = Literal["calculated", "incomplete", "unavailable"]


class PeriodSelection(BaseModel):
    fiscal_year: int = Field(ge=1900, le=9998)
    period_type: PeriodType = "year"
    quarter: int | None = Field(default=None, ge=1, le=4)
    month: int | None = Field(default=None, ge=1, le=12)
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise ValueError("Currency must be a three-letter ASCII code")
        return value

    @model_validator(mode="after")
    def check_parameters(self) -> Self:
        if self.period_type == "year" and (
            self.quarter is not None or self.month is not None
        ):
            raise ValueError("Year periods do not accept month or quarter")
        if self.period_type == "quarter" and (
            self.quarter is None or self.month is not None
        ):
            raise ValueError("Quarter periods require quarter and do not accept month")
        if self.period_type == "month" and (
            self.month is None or self.quarter is not None
        ):
            raise ValueError("Month periods require month and do not accept quarter")
        return self


class ReportingPeriod(BaseModel):
    fiscal_year: int
    period_type: PeriodType
    start_date: date
    end_date: date
    day_count: int
    label: str
    financial_year_start_month: int


class AccountContribution(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    account_type: str
    financial_statement: str
    financial_category: str
    is_active: bool
    match_methods: list[str]
    debit: Decimal
    credit: Decimal
    signed_amount: Decimal
    transaction_count: int
    source_file_ids: list[int]


class DataWarning(BaseModel):
    code: str
    message: str
    scope: str
    transaction_count: int = 0
    source_file_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    debit: Decimal | None = None
    credit: Decimal | None = None


class ResultReason(BaseModel):
    code: str
    message: str


class PopulationScope(BaseModel):
    company_id: int
    currency: str
    start_date: date | None
    end_date: date
    coverage_verified: bool = False
    population_fingerprint: str


class CalculationBasis(BaseModel):
    # Names are registered by the producing module; future modules can extend them.
    kind: str
    formula: str
    population_scope: PopulationScope
    input_metrics: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)


class SourceFileReference(BaseModel):
    source_file_id: int
    filename: str
    sha256: str
    transaction_count: int
    warning_row_count: int
    error_row_count: int


class FinancialResult(BaseModel):
    """Shared evidence contract, independent of the reporting API and frontend."""

    company_id: int
    metric: str
    value: Decimal | None
    unit: str
    status: Status
    reason: ResultReason | None
    calculation_basis: CalculationBasis
    formula_version: str = "financial-intelligence/v1"
    currency: str
    resolved_period: ReportingPeriod
    contributing_accounts: list[AccountContribution]
    transaction_count: int
    source_files: list[SourceFileReference]
    warnings: list[DataWarning]

    @model_validator(mode="after")
    def check_availability(self) -> Self:
        if (self.status == "unavailable") != (self.value is None):
            raise ValueError(
                "Unavailable results require null; other states require a value"
            )
        if self.status != "calculated" and self.reason is None:
            raise ValueError("Incomplete and unavailable results require a reason")
        if self.value is not None and not self.value.is_finite():
            raise ValueError("Financial values must be finite")
        return self


class PopulationSummary(BaseModel):
    transaction_count: int
    excluded_transaction_count: int
    first_transaction_date: date | None
    last_transaction_date: date | None
    coverage_verified: bool = False
    excluded_debit: Decimal
    excluded_credit: Decimal


class FinancialReport(BaseModel):
    company_id: int
    currency: str
    resolved_period: ReportingPeriod
    report_type: str
    formula_version: str = "financial-intelligence/v1"
    population_fingerprint: str
    classifications: list[AccountRead]
    populations: dict[str, PopulationSummary]
    results: dict[str, FinancialResult]
    warnings: list[DataWarning]


class TransactionTrace(BaseModel):
    transaction_id: int
    transaction_date: date
    company_id: int
    source_file_id: int
    source_row_number: int
    account_code: str | None
    account_name: str | None
    debit: Decimal
    credit: Decimal
    currency: str
    matched_account: AccountRead | None
    match_method: str | None
    exclusion_reason: str | None


class DrillDown(BaseModel):
    company_id: int
    currency: str
    resolved_period: ReportingPeriod
    metric: str | None
    calculation_basis: CalculationBasis
    population_fingerprint: str
    total: int
    offset: int
    limit: int
    transactions: list[TransactionTrace]


class AvailablePeriods(BaseModel):
    company_id: int
    financial_year_start_month: int
    fiscal_years: list[int]
    currencies: list[str]
    periods: list[ReportingPeriod]


class PeriodSummaries(BaseModel):
    company_id: int
    fiscal_year: int
    period_type: PeriodType
    reports: list[FinancialReport]
