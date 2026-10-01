from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "account_code", name="uq_accounts_company_code"),
        UniqueConstraint("company_id", "id", name="uq_accounts_company_id"),
        ForeignKeyConstraint(
            ["company_id", "parent_account_id"],
            ["accounts.company_id", "accounts.id"],
            ondelete="RESTRICT",
            name="fk_accounts_company_parent",
        ),
        CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id",
            name="ck_accounts_not_self_parent",
        ),
        CheckConstraint(
            (
                "account_type IS NULL OR account_type IN ('ASSET', "
                "'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE')"
            ),
            name="ck_accounts_type",
        ),
        CheckConstraint(
            (
                "financial_statement IS NULL OR financial_statement IN "
                "('PROFIT_AND_LOSS', 'BALANCE_SHEET', 'CASH_FLOW')"
            ),
            name="ck_accounts_statement",
        ),
        CheckConstraint(
            (
                "(account_type IS NULL AND financial_statement IS NULL AND "
                "financial_category IS NULL) OR "
                "(account_type IS NOT NULL AND financial_statement IS NOT "
                "NULL AND financial_category IS NOT NULL)"
            ),
            name="ck_accounts_classification_complete",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    account_code: Mapped[str] = mapped_column(String(100))
    account_name: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str | None] = mapped_column(String(16))
    financial_statement: Mapped[str | None] = mapped_column(String(32))
    financial_category: Mapped[str | None] = mapped_column(String(100))
    parent_account_id: Mapped[int | None] = mapped_column(Integer, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=true(), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
