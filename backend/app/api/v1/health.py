import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db_session
from backend.app.schemas.health import HealthStatus
from backend.app.services.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/live", response_model=HealthStatus)
def live() -> HealthStatus:
    logger.debug("Liveness check requested")
    return HealthStatus(status="alive")


@router.get(
    "/ready",
    response_model=HealthStatus,
    responses={503: {"model": HealthStatus}},
)
def ready(
    session: Annotated[Session, Depends(get_db_session)],
) -> HealthStatus | JSONResponse:
    logger.debug("Readiness check requested")
    if not HealthService().database_is_ready(session):
        return JSONResponse(
            status_code=503,
            content=HealthStatus(status="unavailable").model_dump(),
        )
    return HealthStatus(status="ready")
