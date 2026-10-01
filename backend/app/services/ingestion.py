import hashlib

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.errors import IngestionError
from backend.app.models import GLTransaction, SourceFile
from backend.app.repositories.ingestion import (
    CompanyRepository,
    GLRepository,
    SourceFileRepository,
)
from backend.app.schemas.ingestion import (
    ControlTotals,
    GLSummary,
    ImportResponse,
    ValidationReport,
)
from backend.app.services.normalization import validate_table
from backend.app.services.parsing import list_worksheets, parse_file, validate_upload


class IngestionService:
    def __init__(
        self,
        companies: CompanyRepository | None = None,
        files: SourceFileRepository | None = None,
        transactions: GLRepository | None = None,
    ) -> None:
        self.companies = companies or CompanyRepository()
        self.files = files or SourceFileRepository()
        self.transactions = transactions or GLRepository()

    def worksheets(self, filename: str, content: bytes) -> list[str]:
        return list_worksheets(filename, content)

    def upload(
        self,
        session: Session,
        company_id: int,
        filename: str,
        content: bytes,
        sheet_name: str | None,
    ) -> tuple[SourceFile, ValidationReport]:
        company = self.companies.get(session, company_id)
        if company is None:
            raise IngestionError(404, "COMPANY_NOT_FOUND", "Company does not exist")
        file_type = validate_upload(filename, content)
        clean_name = filename.replace("\\", "/").split("/")[-1]
        if not clean_name or len(clean_name) > 255:
            raise IngestionError(422, "INVALID_FILENAME", "Filename is invalid")
        table = parse_file(clean_name, content, sheet_name)
        digest = hashlib.sha256(content).hexdigest()
        worksheet_key = table.worksheet or ""
        prior = self.files.by_hash(session, company_id, digest, worksheet_key)
        if prior is not None:
            raise IngestionError(
                409,
                "DUPLICATE_UPLOAD",
                "This file and worksheet were already uploaded for this company",
                {"file_id": prior.id},
            )
        result = validate_table(table, company.currency)
        report = result.report
        source_file = SourceFile(
            company_id=company_id,
            filename=clean_name,
            file_type=file_type,
            file_size=len(content),
            sha256=digest,
            status="validated",
            row_count=report.row_count,
            valid_row_count=report.valid_row_count,
            warning_row_count=report.warning_row_count,
            error_row_count=report.error_row_count,
            sheet_name=worksheet_key,
            file_content=content,
            validation_report=report.model_dump(mode="json"),
        )
        try:
            self.files.create(session, source_file)
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            prior = self.files.by_hash(session, company_id, digest, worksheet_key)
            raise IngestionError(
                409,
                "DUPLICATE_UPLOAD",
                "This file and worksheet were already uploaded for this company",
                {"file_id": prior.id if prior else None},
            ) from exc
        session.refresh(source_file)
        report.file_id = source_file.id
        return source_file, report

    def get_file(self, session: Session, file_id: int) -> SourceFile:
        source_file = self.files.get(session, file_id)
        if source_file is None:
            raise IngestionError(404, "FILE_NOT_FOUND", "Source file does not exist")
        return source_file

    def report(self, session: Session, file_id: int) -> ValidationReport:
        source_file = self.get_file(session, file_id)
        report = ValidationReport.model_validate(source_file.validation_report)
        report.file_id = source_file.id
        return report

    def import_valid(self, session: Session, file_id: int) -> ImportResponse:
        source_file = self.files.get(session, file_id, lock=True)
        if source_file is None:
            raise IngestionError(404, "FILE_NOT_FOUND", "Source file does not exist")
        if source_file.status == "imported":
            raise IngestionError(
                409, "ALREADY_IMPORTED", "Source file was already imported"
            )
        company = self.companies.get(session, source_file.company_id)
        if company is None:
            raise IngestionError(404, "COMPANY_NOT_FOUND", "Company does not exist")
        table = parse_file(
            source_file.filename,
            source_file.file_content,
            source_file.sheet_name or None,
        )
        result = validate_table(table, company.currency)
        if not result.rows:
            raise IngestionError(
                409, "NO_VALID_ROWS", "The file has no importable rows"
            )
        records = [
            GLTransaction(
                company_id=source_file.company_id,
                source_file_id=source_file.id,
                source_row_number=row.source_row_number,
                transaction_date=row.transaction_date,
                document_number=row.document_number,
                account_code=row.account_code,
                account_name=row.account_name,
                description=row.description,
                debit=row.debit,
                credit=row.credit,
                currency=row.currency,
                cost_center=row.cost_center,
                department=row.department,
            )
            for row in result.rows
        ]
        self.transactions.add_all(session, records)
        source_file.status = "imported"
        session.commit()
        return ImportResponse(
            file_id=source_file.id,
            status=source_file.status,
            imported_row_count=len(records),
            skipped_row_count=result.report.error_row_count,
            controls=result.report.controls,
        )

    def summary(self, session: Session, company_id: int) -> GLSummary:
        if self.companies.get(session, company_id) is None:
            raise IngestionError(404, "COMPANY_NOT_FOUND", "Company does not exist")
        groups = self.transactions.summary(session, company_id)
        controls = [
            ControlTotals(
                currency=currency,
                total_debit=debit,
                total_credit=credit,
                difference=debit - credit,
                balanced=debit == credit,
            )
            for currency, _count, debit, credit in groups
        ]
        return GLSummary(
            company_id=company_id,
            transaction_count=sum(
                count for _currency, count, _debit, _credit in groups
            ),
            controls=controls,
        )
