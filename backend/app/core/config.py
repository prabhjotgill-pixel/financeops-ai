from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "FinanceOps AI"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str = ""
    financial_year_start_month: int = Field(default=4, ge=1, le=12)

    @model_validator(mode="after")
    def require_database_url(self) -> Self:
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
