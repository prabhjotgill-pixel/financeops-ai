from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Company, GLTransaction, SourceFile


class CompanyRepository:
    def create(self, session: Session, company: Company) -> Company:
        session.add(company)
        session.flush()
        return company

    def get(self, session: Session, company_id: int) -> Company | None:
        return session.get(Company, company_id)

    def list(self, session: Session) -> list[Company]:
        return list(session.scalars(select(Company).order_by(Company.id)))

    def by_name(self, session: Session, name: str) -> Company | None:
        return session.scalar(select(Company).where(Company.name == name))


class SourceFileRepository:
    def by_hash(
        self, session: Session, company_id: int, sha256: str, sheet_name: str
    ) -> SourceFile | None:
        return session.scalar(
            select(SourceFile).where(
                SourceFile.company_id == company_id,
                SourceFile.sha256 == sha256,
                SourceFile.sheet_name == sheet_name,
            )
        )

    def get(
        self, session: Session, file_id: int, *, lock: bool = False
    ) -> SourceFile | None:
        statement = select(SourceFile).where(SourceFile.id == file_id)
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def create(self, session: Session, source_file: SourceFile) -> SourceFile:
        session.add(source_file)
        session.flush()
        return source_file


class GLRepository:
    def add_all(self, session: Session, transactions: list[GLTransaction]) -> None:
        session.add_all(transactions)

    def summary(
        self, session: Session, company_id: int
    ) -> list[tuple[str, int, Decimal, Decimal]]:
        statement = (
            select(
                GLTransaction.currency,
                func.count(GLTransaction.id),
                func.sum(GLTransaction.debit),
                func.sum(GLTransaction.credit),
            )
            .where(GLTransaction.company_id == company_id)
            .group_by(GLTransaction.currency)
            .order_by(GLTransaction.currency)
        )
        return [
            (currency, count, debit, credit)
            for currency, count, debit, credit in session.execute(statement).all()
        ]
