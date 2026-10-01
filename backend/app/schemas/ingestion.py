from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=200)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("company name is required")
        return name

    @field_validator("industry")
    @classmethod
    def strip_industry(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a three-letter code")
        return code


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    industry: str | None
    currency: str
    created_at: datetime


class SourceFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    filename: str
    file_type: str
    file_size: int
    sha256: str
    uploaded_at: datetime
    status: str
    row_count: int
    valid_row_count: int
    warning_row_count: int
    error_row_count: int
    sheet_name: str


class ValidationIssue(BaseModel):
    row_number: int | None
    severity: Literal["ERROR", "WARNING"]
    code: str
    message: str


class ControlTotals(BaseModel):
    currency: str
    total_debit: Decimal
    total_credit: Decimal
    difference: Decimal
    balanced: bool


class ValidationReport(BaseModel):
    file_id: int | None = None
    worksheet: str | None
    column_mapping: dict[str, str]
    row_count: int
    valid_row_count: int
    warning_row_count: int
    error_row_count: int
    controls: list[ControlTotals]
    issues: list[ValidationIssue]


class UploadResponse(BaseModel):
    file: SourceFileRead
    report: ValidationReport


class SheetList(BaseModel):
    sheets: list[str]


class ImportResponse(BaseModel):
    file_id: int
    status: str
    imported_row_count: int
    skipped_row_count: int
    controls: list[ControlTotals]


class GLSummary(BaseModel):
    company_id: int
    transaction_count: int
    controls: list[ControlTotals]
