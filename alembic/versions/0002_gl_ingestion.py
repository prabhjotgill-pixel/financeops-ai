"""Add company and general ledger ingestion tables.

Revision ID: 0002_gl_ingestion
Revises: 0001_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_gl_ingestion"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=200)),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_companies_name"),
    )
    op.create_table(
        "source_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=8), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_row_count", sa.Integer(), nullable=False),
        sa.Column("warning_row_count", sa.Integer(), nullable=False),
        sa.Column("error_row_count", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("file_content", sa.LargeBinary(), nullable=False),
        sa.Column("validation_report", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "sha256",
            "sheet_name",
            name="uq_source_file_company_hash_sheet",
        ),
        sa.CheckConstraint("file_size > 0", name="ck_source_file_size_positive"),
        sa.CheckConstraint(
            "row_count >= 0 AND valid_row_count >= 0 AND "
            "warning_row_count >= 0 AND error_row_count >= 0",
            name="ck_source_file_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "status IN ('validated', 'imported')", name="ck_source_file_status"
        ),
    )
    op.create_index("ix_source_files_company_id", "source_files", ["company_id"])
    op.create_table(
        "gl_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_file_id",
            sa.Integer(),
            sa.ForeignKey("source_files.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("document_number", sa.String(length=100)),
        sa.Column("account_code", sa.String(length=100)),
        sa.Column("account_name", sa.String(length=255)),
        sa.Column("description", sa.Text()),
        sa.Column("debit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("credit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("cost_center", sa.String(length=100)),
        sa.Column("department", sa.String(length=100)),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "source_file_id",
            "source_row_number",
            name="uq_gl_transaction_source_row",
        ),
        sa.CheckConstraint(
            "account_code IS NOT NULL OR account_name IS NOT NULL",
            name="ck_gl_transaction_account",
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0 AND "
            "((debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0))",
            name="ck_gl_transaction_amount_side",
        ),
    )
    op.create_index("ix_gl_transactions_company_id", "gl_transactions", ["company_id"])
    op.create_index(
        "ix_gl_transactions_source_file_id", "gl_transactions", ["source_file_id"]
    )
    op.create_index(
        "ix_gl_transactions_transaction_date", "gl_transactions", ["transaction_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_gl_transactions_transaction_date", table_name="gl_transactions")
    op.drop_index("ix_gl_transactions_source_file_id", table_name="gl_transactions")
    op.drop_index("ix_gl_transactions_company_id", table_name="gl_transactions")
    op.drop_table("gl_transactions")
    op.drop_index("ix_source_files_company_id", table_name="source_files")
    op.drop_table("source_files")
    op.drop_table("companies")
