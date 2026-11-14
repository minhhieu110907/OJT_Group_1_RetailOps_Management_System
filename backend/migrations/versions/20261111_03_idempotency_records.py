"""Create shared idempotency records.

Revision ID: 20261111_03
Revises: 20261111_02
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261111_03"
down_revision: str | None = "20261111_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("key_digest", mysql.BINARY(32), nullable=False),
        sa.Column("request_digest", mysql.BINARY(32), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", mysql.JSON(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "operation IN ('CHECKOUT','CONFIRM_RECEIPT','CANCEL_ORDER',"
            "'INVENTORY_ADJUSTMENT')",
            name="ck_idempotency_records_operation",
        ),
        sa.CheckConstraint(
            "(response_status IS NULL AND response_body IS NULL "
            "AND completed_at IS NULL AND expires_at IS NULL) OR "
            "(response_status BETWEEN 200 AND 499 AND response_body IS NOT NULL "
            "AND completed_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at = DATE_ADD(completed_at, INTERVAL 24 HOUR))",
            name="ck_idempotency_records_completion",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "operation", "key_digest"),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")
