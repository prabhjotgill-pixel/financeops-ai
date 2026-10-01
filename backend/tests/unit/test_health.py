from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.dependencies import get_db_session
from backend.app.main import create_app


def test_live(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_on_database_error() -> None:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    session = Mock(spec=Session)
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("offline"))
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_unexpected_error_is_sanitized() -> None:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    session = Mock(spec=Session)
    session.execute.side_effect = RuntimeError("internal detail")
    app.dependency_overrides[get_db_session] = lambda: session

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "internal detail" not in response.text
