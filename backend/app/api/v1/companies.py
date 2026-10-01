from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db_session
from backend.app.schemas.ingestion import CompanyCreate, CompanyRead, GLSummary
from backend.app.services.companies import CompanyService
from backend.app.services.ingestion import IngestionService

router = APIRouter(tags=["companies"])


@router.post("/companies", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    session: Annotated[Session, Depends(get_db_session)],
) -> CompanyRead:
    return CompanyRead.model_validate(CompanyService().create(session, payload))


@router.get("/companies", response_model=list[CompanyRead])
def list_companies(
    session: Annotated[Session, Depends(get_db_session)],
) -> list[CompanyRead]:
    return [
        CompanyRead.model_validate(company)
        for company in CompanyService().list(session)
    ]


@router.get("/companies/{company_id}/gl/summary", response_model=GLSummary)
def gl_summary(
    company_id: int,
    session: Annotated[Session, Depends(get_db_session)],
) -> GLSummary:
    return IngestionService().summary(session, company_id)
