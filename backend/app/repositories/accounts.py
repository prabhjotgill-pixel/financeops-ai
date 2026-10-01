from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Account, Company


class AccountRepository:
    def company(
        self, session: Session, company_id: int, *, lock: bool = False
    ) -> Company | None:
        query = select(Company).where(Company.id == company_id)
        return session.scalar(query.with_for_update() if lock else query)

    def list(self, session: Session, company_id: int) -> list[Account]:
        return list(
            session.scalars(
                select(Account)
                .where(Account.company_id == company_id)
                .order_by(Account.account_code)
            )
        )

    def get(self, session: Session, account_id: int) -> Account | None:
        return session.get(Account, account_id)

    def by_code(self, session: Session, company_id: int, code: str) -> Account | None:
        return session.scalar(
            select(Account).where(
                Account.company_id == company_id, Account.account_code == code
            )
        )

    def add(self, session: Session, account: Account) -> None:
        session.add(account)
        session.flush()
