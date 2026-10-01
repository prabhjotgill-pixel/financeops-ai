from pathlib import Path

import pytest

from backend.app.core.config import Settings


def test_configuration_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("APP_ENV", "test")
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.app_env == "test"
    assert settings.app_name == "FinanceOps AI"


def test_example_environment_has_required_keys() -> None:
    example = Path(".env.example").read_text(encoding="utf-8")
    for key in ("APP_ENV=", "APP_NAME=", "LOG_LEVEL=", "DATABASE_URL="):
        assert key in example
