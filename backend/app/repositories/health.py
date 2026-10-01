from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    def check_connection(self, session: Session) -> None:
        session.execute(text("SELECT 1"))
