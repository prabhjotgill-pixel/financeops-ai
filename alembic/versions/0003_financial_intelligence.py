"""Add company chart of accounts.

Revision ID: 0003_financial_intelligence
Revises: 0002_gl_ingestion
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_financial_intelligence"
down_revision: str | None = "0002_gl_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("account_code", sa.String(100), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(16)),
        sa.Column("financial_statement", sa.String(32)),
        sa.Column("financial_category", sa.String(100)),
        sa.Column("parent_account_id", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "company_id", "account_code", name="uq_accounts_company_code"
        ),
        sa.UniqueConstraint("company_id", "id", name="uq_accounts_company_id"),
        sa.ForeignKeyConstraint(
            ["company_id", "parent_account_id"],
            ["accounts.company_id", "accounts.id"],
            ondelete="RESTRICT",
            name="fk_accounts_company_parent",
        ),
        sa.CheckConstraint(
            "parent_account_id IS NULL OR parent_account_id <> id",
            name="ck_accounts_not_self_parent",
        ),
        sa.CheckConstraint(
            (
                "account_type IS NULL OR account_type IN ('ASSET', "
                "'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE')"
            ),
            name="ck_accounts_type",
        ),
        sa.CheckConstraint(
            (
                "financial_statement IS NULL OR financial_statement IN "
                "('PROFIT_AND_LOSS', 'BALANCE_SHEET', 'CASH_FLOW')"
            ),
            name="ck_accounts_statement",
        ),
        sa.CheckConstraint(
            (
                "(account_type IS NULL AND financial_statement IS NULL AND "
                "financial_category IS NULL) OR "
                "(account_type IS NOT NULL AND financial_statement IS NOT "
                "NULL AND financial_category IS NOT NULL)"
            ),
            name="ck_accounts_classification_complete",
        ),
    )
    op.create_index("ix_accounts_company_id", "accounts", ["company_id"])
    op.create_index("ix_accounts_parent_account_id", "accounts", ["parent_account_id"])


def downgrade() -> None:
    op.drop_index("ix_accounts_parent_account_id", table_name="accounts")
    op.drop_index("ix_accounts_company_id", table_name="accounts")
    op.drop_table("accounts")
