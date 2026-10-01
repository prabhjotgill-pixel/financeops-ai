import csv
import io
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from backend.app.core.errors import IngestionError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DATA_ROWS = 100_000


@dataclass(frozen=True)
class RawRow:
    number: int
    values: list[Any]


@dataclass(frozen=True)
class ParsedTable:
    headers: list[str]
    rows: list[RawRow]
    worksheet: str | None


def validate_upload(filename: str, content: bytes) -> str:
    extension = PurePath(filename).suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise IngestionError(
            422, "UNSUPPORTED_FILE_TYPE", "Only .csv and .xlsx are supported"
        )
    if not content:
        raise IngestionError(422, "EMPTY_FILE", "The uploaded file is empty")
    if len(content) > MAX_FILE_BYTES:
        raise IngestionError(
            413, "FILE_TOO_LARGE", "The file exceeds the 10 MB upload limit"
        )
    return extension.removeprefix(".")


def list_worksheets(filename: str, content: bytes) -> list[str]:
    if validate_upload(filename, content) != "xlsx":
        raise IngestionError(
            422, "NOT_EXCEL", "Worksheet selection applies only to .xlsx"
        )
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (OSError, ValueError, InvalidFileException, BadZipFile) as exc:
        raise IngestionError(
            422, "MALFORMED_FILE", "Unable to read Excel workbook"
        ) from exc
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def parse_file(filename: str, content: bytes, sheet_name: str | None) -> ParsedTable:
    file_type = validate_upload(filename, content)
    if file_type == "csv":
        if sheet_name:
            raise IngestionError(422, "NOT_EXCEL", "CSV files have no worksheets")
        return _parse_csv(content)
    return _parse_excel(content, sheet_name)


def _parse_csv(content: bytes) -> ParsedTable:
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""))
        headers = next(reader, [])
        rows: list[RawRow] = []
        for values in reader:
            rows.append(RawRow(reader.line_num, values))
            if len(rows) > MAX_DATA_ROWS:
                raise IngestionError(
                    413, "TOO_MANY_ROWS", "The file exceeds 100,000 rows"
                )
    except (UnicodeError, csv.Error) as exc:
        raise IngestionError(422, "MALFORMED_FILE", "Unable to read UTF-8 CSV") from exc
    if not headers or not rows:
        raise IngestionError(422, "EMPTY_FILE", "The file has no header or data rows")
    return ParsedTable([str(value) for value in headers], rows, None)


def _parse_excel(content: bytes, sheet_name: str | None) -> ParsedTable:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (OSError, ValueError, InvalidFileException, BadZipFile) as exc:
        raise IngestionError(
            422, "MALFORMED_FILE", "Unable to read Excel workbook"
        ) from exc
    try:
        sheets = workbook.sheetnames
        if sheet_name is None:
            if len(sheets) != 1:
                raise IngestionError(
                    422,
                    "SHEET_SELECTION_REQUIRED",
                    "Select a worksheet",
                    {"sheets": sheets},
                )
            sheet_name = sheets[0]
        if sheet_name not in sheets:
            raise IngestionError(
                422, "UNKNOWN_SHEET", "Worksheet does not exist", {"sheets": sheets}
            )
        worksheet = workbook[sheet_name]
        iterator = worksheet.iter_rows(values_only=True)
        headers = next(iterator, None)
        if headers is None:
            raise IngestionError(422, "EMPTY_FILE", "The worksheet is empty")
        rows: list[RawRow] = []
        for number, values in enumerate(iterator, start=2):
            rows.append(RawRow(number, list(values)))
            if len(rows) > MAX_DATA_ROWS:
                raise IngestionError(
                    413, "TOO_MANY_ROWS", "The sheet exceeds 100,000 rows"
                )
        if not rows:
            raise IngestionError(422, "EMPTY_FILE", "The worksheet has no data rows")
        return ParsedTable(
            [str(value) if value is not None else "" for value in headers],
            rows,
            sheet_name,
        )
    finally:
        workbook.close()
