import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from openpyxl.utils.datetime import from_excel

from backend.app.core.errors import IngestionError
from backend.app.schemas.ingestion import (
    ControlTotals,
    ValidationIssue,
    ValidationReport,
)
from backend.app.services.parsing import ParsedTable

MONEY = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999999999.99")

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "transaction_date": ("date", "transaction date", "posting date", "tran date"),
    "document_number": (
        "voucher no",
        "voucher number",
        "document no",
        "document number",
        "doc no",
    ),
    "account_code": ("account code", "gl code", "ledger code"),
    "account_name": (
        "account",
        "account name",
        "ledger",
        "ledger name",
        "gl account",
    ),
    "description": ("description", "particulars", "narration", "memo"),
    "debit": ("debit", "dr", "dr amount", "debit amount"),
    "credit": ("credit", "cr", "cr amount", "credit amount"),
    "currency": ("currency", "currency code", "ccy"),
    "cost_center": ("cost center", "cost centre", "costcenter"),
    "department": ("department", "dept"),
}
ALIAS_TO_FIELD = {
    "".join(
        char
        for char in unicodedata.normalize("NFKC", alias).casefold()
        if char.isalnum()
    ): field
    for field, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}


@dataclass(frozen=True)
class ColumnMapping:
    indexes: dict[str, int]
    names: dict[str, str]


@dataclass(frozen=True)
class NormalizedRow:
    source_row_number: int
    transaction_date: date
    document_number: str | None
    account_code: str | None
    account_name: str | None
    description: str | None
    debit: Decimal
    credit: Decimal
    currency: str
    cost_center: str | None
    department: str | None


@dataclass(frozen=True)
class ValidationResult:
    report: ValidationReport
    rows: list[NormalizedRow]


class AmountValueError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def normalize_header(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def detect_columns(headers: list[str]) -> ColumnMapping:
    indexes: dict[str, int] = {}
    names: dict[str, str] = {}
    for index, header in enumerate(headers):
        field = ALIAS_TO_FIELD.get(normalize_header(header))
        if field is None:
            continue
        if field in indexes:
            raise IngestionError(
                422,
                "AMBIGUOUS_COLUMN_MAPPING",
                f"More than one column maps to {field}",
            )
        indexes[field] = index
        names[field] = header
    missing = []
    if "transaction_date" not in indexes:
        missing.append("transaction_date")
    if "account_code" not in indexes and "account_name" not in indexes:
        missing.append("account_code or account_name")
    if "debit" not in indexes and "credit" not in indexes:
        missing.append("debit or credit")
    if missing:
        raise IngestionError(
            422,
            "MISSING_REQUIRED_COLUMNS",
            "Required GL columns are missing",
            {"missing": missing},
        )
    return ColumnMapping(indexes, names)


def normalize_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            result = from_excel(value)
            if isinstance(result, datetime):
                return result.date()
        except (ValueError, OverflowError):
            pass
        raise ValueError("Invalid Excel date")
    text = str(value).strip() if value is not None else ""
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError("Invalid date")


def normalize_amount(value: Any) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal("0.00")
    if isinstance(value, bool):
        raise AmountValueError("INVALID_NUMERIC", "Amount is not numeric")
    text = str(value).strip()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise AmountValueError("INVALID_NUMERIC", "Amount is not numeric")
    try:
        amount = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise AmountValueError("INVALID_NUMERIC", "Amount is not numeric") from exc
    if not amount.is_finite() or abs(amount) > MAX_AMOUNT:
        raise AmountValueError(
            "INVALID_NUMERIC", "Amount is outside the supported range"
        )
    if amount != amount.quantize(MONEY):
        raise AmountValueError(
            "EXCESS_PRECISION", "Amount has more than two decimal places"
        )
    return amount.quantize(MONEY)


def _cell(values: list[Any], mapping: ColumnMapping, field: str) -> Any:
    index = mapping.indexes.get(field)
    return values[index] if index is not None else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def validate_table(table: ParsedTable, company_currency: str) -> ValidationResult:
    mapping = detect_columns(table.headers)
    issues: list[ValidationIssue] = []
    accepted: list[NormalizedRow] = []
    warning_rows: set[int] = set()
    error_rows: set[int] = set()
    seen_identifiers: set[tuple[date, str, str, Decimal, Decimal, str]] = set()

    def issue(
        number: int, severity: Literal["ERROR", "WARNING"], code: str, message: str
    ) -> None:
        issues.append(
            ValidationIssue(
                row_number=number,
                severity=severity,
                code=code,
                message=message,
            )
        )
        (error_rows if severity == "ERROR" else warning_rows).add(number)

    for source in table.rows:
        number, values = source.number, source.values
        if len(values) != len(table.headers):
            issue(number, "ERROR", "MALFORMED_ROW", "Row has the wrong number of cells")
            continue
        raw_date = _cell(values, mapping, "transaction_date")
        if raw_date is None or str(raw_date).strip() == "":
            issue(number, "ERROR", "MISSING_DATE", "Transaction date is required")
            transaction_date = None
        else:
            try:
                transaction_date = normalize_date(raw_date)
            except ValueError:
                transaction_date = None
                issue(number, "ERROR", "INVALID_DATE", "Transaction date is invalid")

        account_code = _text(_cell(values, mapping, "account_code"))
        account_name = _text(_cell(values, mapping, "account_name"))
        if not account_code and not account_name:
            issue(
                number, "ERROR", "MISSING_ACCOUNT", "Account code or name is required"
            )

        amounts: dict[str, Decimal] = {}
        for side in ("debit", "credit"):
            try:
                amounts[side] = normalize_amount(_cell(values, mapping, side))
            except AmountValueError as exc:
                amounts[side] = Decimal("0.00")
                issue(number, "ERROR", exc.code, f"{side.capitalize()}: {exc}")
        debit, credit = amounts["debit"], amounts["credit"]
        if debit < 0:
            issue(number, "ERROR", "NEGATIVE_DEBIT", "Debit cannot be negative")
        if credit < 0:
            issue(number, "ERROR", "NEGATIVE_CREDIT", "Credit cannot be negative")
        if debit > 0 and credit > 0:
            issue(number, "ERROR", "BOTH_SIDES", "Debit and credit are both populated")
        elif (
            debit == 0
            and credit == 0
            and not any(
                entry.row_number == number
                and entry.code in {"INVALID_NUMERIC", "EXCESS_PRECISION"}
                for entry in issues
            )
        ):
            issue(number, "ERROR", "NO_AMOUNT", "Neither debit nor credit is populated")

        currency = _text(_cell(values, mapping, "currency")) or company_currency
        currency = currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            issue(
                number,
                "ERROR",
                "INVALID_CURRENCY",
                "Currency must be a three-letter code",
            )

        text_fields = {
            "document_number": (_text(_cell(values, mapping, "document_number")), 100),
            "account_code": (account_code, 100),
            "account_name": (account_name, 255),
            "cost_center": (_text(_cell(values, mapping, "cost_center")), 100),
            "department": (_text(_cell(values, mapping, "department")), 100),
        }
        for field, (value, limit) in text_fields.items():
            if value is not None and len(value) > limit:
                issue(
                    number,
                    "ERROR",
                    "VALUE_TOO_LONG",
                    f"{field} exceeds {limit} characters",
                )

        if number in error_rows or transaction_date is None:
            continue
        document_number = text_fields["document_number"][0]
        account_key = account_code or account_name or ""
        if document_number:
            identifier = (
                transaction_date,
                document_number,
                account_key,
                debit,
                credit,
                currency,
            )
            if identifier in seen_identifiers:
                issue(
                    number,
                    "WARNING",
                    "DUPLICATE_TRANSACTION",
                    "Identical document, account, date, and amount appears earlier",
                )
            seen_identifiers.add(identifier)
        accepted.append(
            NormalizedRow(
                source_row_number=number,
                transaction_date=transaction_date,
                document_number=document_number,
                account_code=account_code,
                account_name=account_name,
                description=_text(_cell(values, mapping, "description")),
                debit=debit,
                credit=credit,
                currency=currency,
                cost_center=text_fields["cost_center"][0],
                department=text_fields["department"][0],
            )
        )

    grouped: dict[str, tuple[Decimal, Decimal]] = {}
    for row in accepted:
        debit, credit = grouped.get(row.currency, (Decimal("0.00"), Decimal("0.00")))
        grouped[row.currency] = (debit + row.debit, credit + row.credit)
    controls = [
        ControlTotals(
            currency=currency,
            total_debit=debit,
            total_credit=credit,
            difference=debit - credit,
            balanced=debit == credit,
        )
        for currency, (debit, credit) in sorted(grouped.items())
    ]
    report = ValidationReport(
        worksheet=table.worksheet,
        column_mapping=mapping.names,
        row_count=len(table.rows),
        valid_row_count=len(accepted),
        warning_row_count=len(warning_rows),
        error_row_count=len(error_rows),
        controls=controls,
        issues=issues,
    )
    return ValidationResult(report, accepted)
