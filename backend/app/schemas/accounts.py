from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.core.financial import (
    AccountType,
    FinancialStatement,
    validate_classification,
)


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_code: str = Field(min_length=1, max_length=100)
    account_name: str = Field(min_length=1, max_length=255)
    account_type: AccountType | None = None
    financial_statement: FinancialStatement | None = None
    financial_category: str | None = Field(default=None, max_length=100)
    parent_account_id: int | None = Field(default=None, gt=0)
    is_active: bool = True

    @field_validator("account_code", "account_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Account code and name cannot be blank")
        return value

    @model_validator(mode="after")
    def check_classification(self) -> Self:
        validate_classification(
            self.account_type, self.financial_statement, self.financial_category
        )
        return self


class AccountPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType | None = None
    financial_statement: FinancialStatement | None = None
    financial_category: str | None = Field(default=None, max_length=100)
    parent_account_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class AccountRead(AccountCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    created_at: datetime


class CategoryRead(BaseModel):
    name: str
    account_type: AccountType
    default_statement: FinancialStatement


class ClassificationCatalog(BaseModel):
    account_types: list[AccountType]
    financial_statements: list[FinancialStatement]
    categories: list[CategoryRead]
