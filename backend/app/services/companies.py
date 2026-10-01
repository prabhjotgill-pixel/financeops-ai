from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.errors import IngestionError
from backend.app.models import Company
from backend.app.repositories.ingestion import CompanyRepository
from backend.app.schemas.ingestion import CompanyCreate


class CompanyService:
    def __init__(self, repository: CompanyRepository | None = None) -> None:
        self.repository = repository or CompanyRepository()

    def create(self, session: Session, payload: CompanyCreate) -> Company:
        if self.repository.by_name(session, payload.name):
            raise IngestionError(409, "COMPANY_EXISTS", "Company name already exists")
        company = Company(
            name=payload.name,
            industry=payload.industry,
            currency=payload.currency,
        )
        try:
            self.repository.create(session, company)
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise IngestionError(
                409, "COMPANY_EXISTS", "Company name already exists"
            ) from exc
        session.refresh(company)
        return company

    def list(self, session: Session) -> list[Company]:
        return self.repository.list(session)
