from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "sha256",
            "sheet_name",
            name="uq_source_file_company_hash_sheet",
        ),
        CheckConstraint("file_size > 0", name="ck_source_file_size_positive"),
        CheckConstraint(
            "row_count >= 0 AND valid_row_count >= 0 AND "
            "warning_row_count >= 0 AND error_row_count >= 0",
            name="ck_source_file_counts_nonnegative",
        ),
        CheckConstraint(
            "status IN ('validated', 'imported')", name="ck_source_file_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(8), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
