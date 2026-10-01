from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db_session
from backend.app.schemas.ingestion import (
    ImportResponse,
    SheetList,
    SourceFileRead,
    UploadResponse,
    ValidationReport,
)
from backend.app.services.ingestion import IngestionService
from backend.app.services.parsing import MAX_FILE_BYTES

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/sheets", response_model=SheetList)
async def list_sheets(
    file: Annotated[UploadFile, File()],
) -> SheetList:
    content = await file.read(MAX_FILE_BYTES + 1)
    return SheetList(sheets=IngestionService().worksheets(file.filename or "", content))


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    company_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_db_session)],
    sheet_name: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    content = await file.read(MAX_FILE_BYTES + 1)
    source_file, report = IngestionService().upload(
        session, company_id, file.filename or "", content, sheet_name
    )
    return UploadResponse(
        file=SourceFileRead.model_validate(source_file), report=report
    )


@router.get("/{file_id}", response_model=SourceFileRead)
def get_file(
    file_id: int,
    session: Annotated[Session, Depends(get_db_session)],
) -> SourceFileRead:
    return SourceFileRead.model_validate(IngestionService().get_file(session, file_id))


@router.get("/{file_id}/validation-report", response_model=ValidationReport)
def validation_report(
    file_id: int,
    session: Annotated[Session, Depends(get_db_session)],
) -> ValidationReport:
    return IngestionService().report(session, file_id)


@router.post("/{file_id}/import", response_model=ImportResponse)
def import_file(
    file_id: int,
    session: Annotated[Session, Depends(get_db_session)],
) -> ImportResponse:
    return IngestionService().import_valid(session, file_id)
