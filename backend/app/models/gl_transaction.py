from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class GLTransaction(Base):
    __tablename__ = "gl_transactions"
    __table_args__ = (
        UniqueConstraint(
            "source_file_id",
            "source_row_number",
            name="uq_gl_transaction_source_row",
        ),
        CheckConstraint(
            "account_code IS NOT NULL OR account_name IS NOT NULL",
            name="ck_gl_transaction_account",
        ),
        CheckConstraint(
            "debit >= 0 AND credit >= 0 AND "
            "((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))",
            name="ck_gl_transaction_amount_side",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_files.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100))
    account_code: Mapped[str | None] = mapped_column(String(100))
    account_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cost_center: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
