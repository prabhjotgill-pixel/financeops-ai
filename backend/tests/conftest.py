import os
from collections.abc import Iterator
from pathlib import Path

if "DATABASE_URL" not in os.environ and not Path(".env").exists():
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
