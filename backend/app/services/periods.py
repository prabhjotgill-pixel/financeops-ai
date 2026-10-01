from calendar import monthrange
from datetime import date, timedelta

from backend.app.schemas.financials import PeriodSelection, PeriodType, ReportingPeriod


class ReportingCalendar:
    def __init__(self, start_month: int = 4) -> None:
        if not 1 <= start_month <= 12:
            raise ValueError("Financial year start month must be between 1 and 12")
        self.start_month = start_month

    def fiscal_year_for(self, value: date) -> int:
        return value.year if value.month >= self.start_month else value.year - 1

    def resolve(self, selection: PeriodSelection) -> ReportingPeriod:
        year = selection.fiscal_year
        start = date(year, self.start_month, 1)
        label = f"FY {year}-{(year + 1) % 100:02d}"
        if selection.period_type == "year":
            end = date(year + 1, self.start_month, 1) - timedelta(days=1)
        elif selection.period_type == "quarter":
            assert selection.quarter is not None
            offset = self.start_month - 1 + (selection.quarter - 1) * 3
            start = date(year + offset // 12, offset % 12 + 1, 1)
            end_offset = offset + 3
            end = date(year + end_offset // 12, end_offset % 12 + 1, 1) - timedelta(
                days=1
            )
            label += f" Q{selection.quarter}"
        else:
            assert selection.month is not None
            month = selection.month
            calendar_year = year + (month < self.start_month)
            start = date(calendar_year, month, 1)
            end = date(calendar_year, month, monthrange(calendar_year, month)[1])
            label = start.strftime("%B %Y")
        return ReportingPeriod(
            fiscal_year=year,
            period_type=selection.period_type,
            start_date=start,
            end_date=end,
            day_count=(end - start).days + 1,
            label=label,
            financial_year_start_month=self.start_month,
        )

    def selections(
        self, fiscal_year: int, period_type: PeriodType, currency: str | None
    ) -> list[PeriodSelection]:
        if period_type == "year":
            return [PeriodSelection(fiscal_year=fiscal_year, currency=currency)]
        if period_type == "quarter":
            return [
                PeriodSelection(
                    fiscal_year=fiscal_year,
                    period_type="quarter",
                    quarter=q,
                    currency=currency,
                )
                for q in range(1, 5)
            ]
        return [
            PeriodSelection(
                fiscal_year=fiscal_year,
                period_type="month",
                month=(self.start_month - 1 + i) % 12 + 1,
                currency=currency,
            )
            for i in range(12)
        ]
