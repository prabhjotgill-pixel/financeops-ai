from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import GLTransaction, SourceFile


@dataclass(frozen=True)
class TransactionData:
    id: int
    company_id: int
    transaction_date: date
    account_code: str | None
    account_name: str | None
    debit: Decimal
    credit: Decimal
    currency: str
    source_file_id: int
    source_row_number: int
    filename: str
    sha256: str
    error_row_count: int
    warning_row_count: int


class FinancialRepository:
    def population(
        self, session: Session, company_id: int, currency: str, end_date: date
    ) -> list[TransactionData]:
        query = (
            select(
                GLTransaction,
                SourceFile.filename,
                SourceFile.sha256,
                SourceFile.error_row_count,
                SourceFile.warning_row_count,
            )
            .join(SourceFile, GLTransaction.source_file_id == SourceFile.id)
            .where(
                GLTransaction.company_id == company_id,
                GLTransaction.currency == currency,
                GLTransaction.transaction_date <= end_date,
                SourceFile.status == "imported",
            )
            .order_by(GLTransaction.id)
        )
        return [
            TransactionData(
                id=row.id,
                company_id=row.company_id,
                transaction_date=row.transaction_date,
                account_code=row.account_code,
                account_name=row.account_name,
                debit=row.debit,
                credit=row.credit,
                currency=row.currency,
                source_file_id=row.source_file_id,
                source_row_number=row.source_row_number,
                filename=filename,
                sha256=digest,
                error_row_count=errors,
                warning_row_count=warnings,
            )
            for row, filename, digest, errors, warnings in session.execute(query)
        ]

    def dates_and_currencies(
        self, session: Session, company_id: int
    ) -> list[tuple[date, str]]:
        query = (
            select(GLTransaction.transaction_date, GLTransaction.currency)
            .join(
                SourceFile,
                SourceFile.id == GLTransaction.source_file_id,
            )
            .where(
                GLTransaction.company_id == company_id, SourceFile.status == "imported"
            )
            .distinct()
            .order_by(GLTransaction.transaction_date)
        )
        return [(day, currency) for day, currency in session.execute(query)]
