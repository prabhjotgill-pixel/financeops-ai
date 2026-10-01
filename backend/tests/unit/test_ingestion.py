from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from backend.app.core.errors import IngestionError
from backend.app.repositories.ingestion import CompanyRepository, SourceFileRepository
from backend.app.services.ingestion import IngestionService
from backend.app.services.normalization import (
    AmountValueError,
    detect_columns,
    normalize_amount,
    normalize_date,
    normalize_header,
    validate_table,
)
from backend.app.services.parsing import list_worksheets, parse_file, validate_upload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def report_for(name: str) -> tuple[list[str], int, int, int]:
    table = parse_file(name, load_fixture(name), None)
    result = validate_table(table, "USD")
    return (
        [issue.code for issue in result.report.issues],
        result.report.valid_row_count,
        result.report.warning_row_count,
        result.report.error_row_count,
    )


def test_header_normalization_and_alias_mapping() -> None:
    assert normalize_header("  Posting-Date  ") == "postingdate"
    mapping = detect_columns(
        [" Posting-Date ", "Voucher No.", "GL Account", "Dr Amount", "Cr Amount"]
    )
    assert mapping.names == {
        "transaction_date": " Posting-Date ",
        "document_number": "Voucher No.",
        "account_name": "GL Account",
        "debit": "Dr Amount",
        "credit": "Cr Amount",
    }


def test_missing_required_columns() -> None:
    with pytest.raises(IngestionError, match="Required GL columns"):
        detect_columns(["Date", "Memo", "Debit"])


def test_date_normalization() -> None:
    assert normalize_date("2025-01-02") == date(2025, 1, 2)
    assert normalize_date("02/01/2025") == date(2025, 1, 2)
    with pytest.raises(ValueError):
        normalize_date("not-a-date")


def test_amount_normalization() -> None:
    assert normalize_amount("1,250.00") == Decimal("1250.00")
    assert normalize_amount("") == Decimal("0.00")
    with pytest.raises(AmountValueError) as error:
        normalize_amount("not-money")
    assert error.value.code == "INVALID_NUMERIC"
    with pytest.raises(AmountValueError) as precision:
        normalize_amount("1.234")
    assert precision.value.code == "EXCESS_PRECISION"


@pytest.mark.parametrize(
    ("filename", "expected_code"),
    [
        ("invalid_date.csv", "INVALID_DATE"),
        ("invalid_numeric.csv", "INVALID_NUMERIC"),
        ("both_sides.csv", "BOTH_SIDES"),
        ("neither_side.csv", "NO_AMOUNT"),
        ("missing_account.csv", "MISSING_ACCOUNT"),
        ("malformed_row.csv", "MALFORMED_ROW"),
    ],
)
def test_row_errors_have_source_row_number(filename: str, expected_code: str) -> None:
    table = parse_file(filename, load_fixture(filename), None)
    result = validate_table(table, "USD")
    assert result.report.valid_row_count == 0
    assert result.report.error_row_count == 1
    assert any(
        issue.code == expected_code and issue.row_number == 2
        for issue in result.report.issues
    )


def test_duplicate_transaction_is_warning() -> None:
    codes, valid, warnings, errors = report_for("duplicate_transaction.csv")
    assert (valid, warnings, errors) == (2, 1, 0)
    assert "DUPLICATE_TRANSACTION" in codes


def test_controls_count_only_importable_rows() -> None:
    table = parse_file("mixed_gl.csv", load_fixture("mixed_gl.csv"), None)
    result = validate_table(table, "USD")
    assert (result.report.row_count, result.report.valid_row_count) == (8, 3)
    assert (result.report.warning_row_count, result.report.error_row_count) == (1, 5)
    control = result.report.controls[0]
    assert control.total_debit == Decimal("200.00")
    assert control.total_credit == Decimal("100.00")
    assert control.difference == Decimal("100.00")
    assert not control.balanced


def test_alias_file_balances() -> None:
    table = parse_file("alias_gl.csv", load_fixture("alias_gl.csv"), None)
    result = validate_table(table, "USD")
    assert result.report.valid_row_count == 2
    assert result.report.controls[0].balanced


def test_file_validation() -> None:
    with pytest.raises(IngestionError) as extension:
        validate_upload("ledger.pdf", b"data")
    assert extension.value.code == "UNSUPPORTED_FILE_TYPE"
    with pytest.raises(IngestionError) as empty:
        validate_upload("ledger.csv", b"")
    assert empty.value.code == "EMPTY_FILE"


def test_excel_sheet_selection() -> None:
    content = load_fixture("multi_sheet_gl.xlsx")
    assert list_worksheets("multi_sheet_gl.xlsx", content) == ["Notes", "GL"]
    with pytest.raises(IngestionError) as error:
        parse_file("multi_sheet_gl.xlsx", content, None)
    assert error.value.code == "SHEET_SELECTION_REQUIRED"
    table = parse_file("multi_sheet_gl.xlsx", content, "GL")
    assert validate_table(table, "USD").report.valid_row_count == 2


def test_duplicate_upload_detected_before_persistence() -> None:
    companies = Mock(spec=CompanyRepository)
    companies.get.return_value = SimpleNamespace(id=1, currency="USD")
    files = Mock(spec=SourceFileRepository)
    files.by_hash.return_value = SimpleNamespace(id=99)
    service = IngestionService(companies=companies, files=files)

    with pytest.raises(IngestionError) as error:
        service.upload(
            Mock(spec=Session),
            1,
            "clean_gl.csv",
            load_fixture("clean_gl.csv"),
            None,
        )
    assert error.value.code == "DUPLICATE_UPLOAD"
    assert error.value.details["file_id"] == 99
    files.create.assert_not_called()


def test_negative_amount_is_rejected() -> None:
    table = parse_file(
        "negative.csv",
        b"Date,Account,Debit,Credit\n2025-01-02,Cash,-10,\n",
        None,
    )
    result = validate_table(table, "USD")
    assert result.report.error_row_count == 1
    assert any(issue.code == "NEGATIVE_DEBIT" for issue in result.report.issues)


def test_missing_date_is_rejected() -> None:
    table = parse_file(
        "missing_date.csv",
        b"Date,Account,Debit,Credit\n,Cash,10,\n",
        None,
    )
    result = validate_table(table, "USD")
    assert any(issue.code == "MISSING_DATE" for issue in result.report.issues)


def test_corrupt_excel_is_rejected() -> None:
    with pytest.raises(IngestionError) as error:
        list_worksheets("broken.xlsx", b"not a workbook")
    assert error.value.code == "MALFORMED_FILE"
