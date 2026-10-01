import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.repositories.health import HealthRepository

logger = logging.getLogger(__name__)


class HealthService:
    def __init__(self, repository: HealthRepository | None = None) -> None:
        self.repository = repository or HealthRepository()

    def database_is_ready(self, session: Session) -> bool:
        try:
            self.repository.check_connection(session)
        except SQLAlchemyError as exc:
            logger.warning("Database readiness check failed (%s)", type(exc).__name__)
            return False
        return True
