import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.v1.companies import router as companies_router
from backend.app.api.v1.files import router as files_router
from backend.app.api.v1.health import router as health_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import IngestionError
from backend.app.core.logging import configure_logging
from backend.app.db.session import make_engine, make_session_factory
from backend.app.schemas.health import ServiceInfo

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Application starting")
        try:
            yield
        finally:
            app.state.engine.dispose()
            logger.info("Application stopped")

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(companies_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")

    @app.get("/", response_model=ServiceInfo)
    def service_info() -> ServiceInfo:
        return ServiceInfo(name=settings.app_name, environment=settings.app_env)

    @app.exception_handler(IngestionError)
    async def ingestion_error(request: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unexpected API error on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    return app


app = create_app()
