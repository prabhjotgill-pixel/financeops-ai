import os

import pytest
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.db.session import make_engine

pytestmark = pytest.mark.integration


def test_postgres_connection_and_migration_head() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    if not database_url.startswith("postgresql+psycopg://"):
        pytest.fail("DATABASE_URL or TEST_DATABASE_URL must use PostgreSQL psycopg")

    engine = make_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0002_gl_ingestion"
            )
    finally:
        engine.dispose()
