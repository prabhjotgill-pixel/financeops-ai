from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.errors import DomainError
from backend.app.core.financial import CATEGORIES, AccountType, FinancialStatement
from backend.app.models import Account, Company
from backend.app.repositories.accounts import AccountRepository
from backend.app.schemas.accounts import (
    AccountCreate,
    AccountPatch,
    AccountRead,
    CategoryRead,
    ClassificationCatalog,
)


class AccountService:
    def __init__(self, repository: AccountRepository | None = None) -> None:
        self.repository = repository or AccountRepository()

    def company(
        self, session: Session, company_id: int, *, lock: bool = False
    ) -> Company:
        company = self.repository.company(session, company_id, lock=lock)
        if company is None:
            raise DomainError(404, "COMPANY_NOT_FOUND", "Company does not exist")
        return company

    def list(self, session: Session, company_id: int) -> list[AccountRead]:
        self.company(session, company_id)
        return [
            AccountRead.model_validate(account)
            for account in self.repository.list(session, company_id)
        ]

    def by_code(self, session: Session, company_id: int, code: str) -> AccountRead:
        self.company(session, company_id)
        account = self.repository.by_code(session, company_id, code.strip())
        if account is None:
            raise DomainError(
                404, "ACCOUNT_NOT_FOUND", "Account code does not exist for this company"
            )
        return AccountRead.model_validate(account)

    def _check_parent(
        self,
        session: Session,
        company_id: int,
        parent_id: int | None,
        account_id: int | None = None,
    ) -> None:
        visited = {account_id} if account_id is not None else set()
        while parent_id is not None:
            if parent_id in visited:
                raise DomainError(
                    422,
                    "ACCOUNT_HIERARCHY_CYCLE",
                    "Account hierarchy cannot contain cycles",
                )
            visited.add(parent_id)
            parent = self.repository.get(session, parent_id)
            if parent is None or parent.company_id != company_id:
                raise DomainError(
                    422,
                    "INVALID_PARENT_ACCOUNT",
                    "Parent account must belong to the same company",
                )
            parent_id = parent.parent_account_id

    def create(
        self, session: Session, company_id: int, payload: AccountCreate
    ) -> AccountRead:
        # Serialize hierarchy mutations per company, including concurrent cycle edits.
        self.company(session, company_id, lock=True)
        self._check_parent(session, company_id, payload.parent_account_id)
        if self.repository.by_code(session, company_id, payload.account_code):
            raise DomainError(
                409,
                "ACCOUNT_CODE_EXISTS",
                "Account code already exists for this company",
            )
        account = Account(company_id=company_id, **payload.model_dump())
        try:
            self.repository.add(session, account)
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise DomainError(
                409,
                "ACCOUNT_CONFLICT",
                "Account conflicts with an existing account or hierarchy",
            ) from exc
        session.refresh(account)
        return AccountRead.model_validate(account)

    def update(
        self, session: Session, account_id: int, patch: AccountPatch
    ) -> AccountRead:
        account = self.repository.get(session, account_id)
        if account is None:
            raise DomainError(404, "ACCOUNT_NOT_FOUND", "Account does not exist")
        self.company(session, account.company_id, lock=True)
        # The first read may precede the company lock; refresh after serialization.
        session.refresh(account)
        updates = patch.model_dump(exclude_unset=True)
        if "is_active" in updates and updates["is_active"] is None:
            raise DomainError(422, "INVALID_ACCOUNT", "is_active cannot be null")
        original = AccountRead.model_validate(account).model_dump(
            include=set(AccountCreate.model_fields)
        )
        try:
            merged = AccountCreate.model_validate(original | updates)
        except ValidationError as exc:
            raise DomainError(
                422,
                "INVALID_CLASSIFICATION",
                "Classification must be complete and compatible with the catalog",
            ) from exc
        self._check_parent(
            session, account.company_id, merged.parent_account_id, account.id
        )
        for field, value in merged.model_dump().items():
            setattr(account, field, value)
        session.commit()
        session.refresh(account)
        return AccountRead.model_validate(account)

    @staticmethod
    def catalog() -> ClassificationCatalog:
        return ClassificationCatalog(
            account_types=list(AccountType),
            financial_statements=list(FinancialStatement),
            categories=[
                CategoryRead(
                    name=definition.name,
                    account_type=definition.account_type,
                    default_statement=definition.statement,
                )
                for definition in CATEGORIES.values()
            ],
        )
