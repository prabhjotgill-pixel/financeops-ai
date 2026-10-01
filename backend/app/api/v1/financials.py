from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.errors import DomainError
from backend.app.dependencies import get_db_session
from backend.app.schemas.financials import (
    AvailablePeriods,
    DrillDown,
    FinancialReport,
    PeriodSelection,
    PeriodSummaries,
    PeriodType,
)
from backend.app.services.financials import FinancialService, ReportType
from backend.app.services.periods import ReportingCalendar

router = APIRouter(prefix="/companies/{company_id}/financials", tags=["financials"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


def period_selection(
    fiscal_year: Annotated[int, Query(ge=1900, le=9998)],
    period_type: PeriodType = "year",
    quarter: Annotated[int | None, Query(ge=1, le=4)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    currency: str | None = None,
) -> PeriodSelection:
    try:
        return PeriodSelection(
            fiscal_year=fiscal_year,
            period_type=period_type,
            quarter=quarter,
            month=month,
            currency=currency,
        )
    except ValidationError as exc:
        raise DomainError(
            422,
            "INVALID_PERIOD",
            "Invalid period or currency parameters",
            {"errors": [error["msg"] for error in exc.errors()]},
        ) from exc


def financial_service(request: Request) -> FinancialService:
    return FinancialService(
        calendar=ReportingCalendar(request.app.state.financial_year_start_month)
    )


SelectionDependency = Annotated[PeriodSelection, Depends(period_selection)]
ServiceDependency = Annotated[FinancialService, Depends(financial_service)]


@router.get("/periods", response_model=AvailablePeriods)
def available_periods(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    currency: Annotated[str | None, Query(pattern="^[A-Za-z]{3}$")] = None,
) -> AvailablePeriods:
    return service.available_periods(session, company_id, currency)


@router.get("/period-summaries", response_model=PeriodSummaries)
def period_summaries(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    fiscal_year: Annotated[int, Query(ge=1900, le=9998)],
    period_type: PeriodType = "month",
    currency: Annotated[str | None, Query(pattern="^[A-Za-z]{3}$")] = None,
) -> PeriodSummaries:
    return service.summaries(
        session,
        company_id,
        fiscal_year,
        period_type,
        currency.upper() if currency else None,
    )


@router.get("/transactions", response_model=DrillDown)
def transactions(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    selection: SelectionDependency,
    report_type: ReportType = "pnl",
    metric: str | None = None,
    population: Literal["contributing", "excluded"] = "contributing",
    scope: Literal["period_activity", "activity_derived"] = "period_activity",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    population_fingerprint: str | None = None,
) -> DrillDown:
    return service.drill_down(
        session,
        company_id,
        selection,
        report_type=report_type,
        metric=metric,
        population=population,
        scope=scope,
        offset=offset,
        limit=limit,
        expected_fingerprint=population_fingerprint,
    )


@router.get("/pnl", response_model=FinancialReport)
def pnl(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    selection: SelectionDependency,
) -> FinancialReport:
    return service.report(session, company_id, selection, "pnl")


@router.get("/balance-sheet", response_model=FinancialReport)
def balance_sheet(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    selection: SelectionDependency,
) -> FinancialReport:
    return service.report(session, company_id, selection, "balance-sheet")


@router.get("/metrics", response_model=FinancialReport)
def metrics(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    selection: SelectionDependency,
) -> FinancialReport:
    return service.report(session, company_id, selection, "metrics")


@router.get("/ratios", response_model=FinancialReport)
def ratios(
    company_id: int,
    session: SessionDependency,
    service: ServiceDependency,
    selection: SelectionDependency,
) -> FinancialReport:
    return service.report(session, company_id, selection, "ratios")
