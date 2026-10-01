from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db_session
from backend.app.schemas.accounts import (
    AccountCreate,
    AccountPatch,
    AccountRead,
    ClassificationCatalog,
)
from backend.app.services.accounts import AccountService

router = APIRouter(tags=["accounts"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/accounts/classification-catalog", response_model=ClassificationCatalog)
def classification_catalog() -> ClassificationCatalog:
    return AccountService.catalog()


@router.get(
    "/companies/{company_id}/accounts/by-code/{account_code}",
    response_model=AccountRead,
)
def account_by_code(
    company_id: int, account_code: str, session: SessionDependency
) -> AccountRead:
    return AccountService().by_code(session, company_id, account_code)


@router.get("/companies/{company_id}/accounts", response_model=list[AccountRead])
def list_accounts(company_id: int, session: SessionDependency) -> list[AccountRead]:
    return AccountService().list(session, company_id)


@router.post(
    "/companies/{company_id}/accounts", response_model=AccountRead, status_code=201
)
def create_account(
    company_id: int, payload: AccountCreate, session: SessionDependency
) -> AccountRead:
    return AccountService().create(session, company_id, payload)


@router.patch("/accounts/{account_id}", response_model=AccountRead)
def update_classification(
    account_id: int, payload: AccountPatch, session: SessionDependency
) -> AccountRead:
    return AccountService().update(session, account_id, payload)
