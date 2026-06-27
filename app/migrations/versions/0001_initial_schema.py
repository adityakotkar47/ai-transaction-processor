"""Initial schema: jobs, transactions, job_summaries

Revision ID: 0001
Revises:
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("cleaned_rows", sa.Integer(), nullable=True),
        sa.Column("duplicate_rows", sa.Integer(), nullable=True),
        sa.Column("anomaly_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("txn_id", sa.String(50), nullable=True),
        sa.Column("txn_date", sa.Date(), nullable=True),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("account_id", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("anomaly_reason", sa.Text(), nullable=True),
        sa.Column("llm_category", sa.String(100), nullable=True),
        sa.Column("llm_failed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_job_id", "transactions", ["job_id"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])

    op.create_table(
        "job_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_spend", sa.Numeric(15, 2), nullable=True),
        sa.Column("top_merchants", postgresql.JSONB(), nullable=True),
        sa.Column("anomaly_count", sa.Integer(), nullable=True),
        sa.Column("category_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("llm_failed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_job_summaries_job_id"),
    )


def downgrade() -> None:
    op.drop_table("job_summaries")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_index("ix_transactions_job_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("jobs")
