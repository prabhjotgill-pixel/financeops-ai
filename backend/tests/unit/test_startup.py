from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def test_application_starts_and_serves_metadata() -> None:
    app = create_app(
        Settings(
            app_name="FinanceOps AI Test",
            app_env="test",
            database_url="sqlite+pysqlite:///:memory:",
        )
    )
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {
            "name": "FinanceOps AI Test",
            "environment": "test",
        }
