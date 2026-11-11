"""Create the transactional outbox table.

Revision ID: 20261111_01
Revises: 20261107_03
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261111_01"
down_revision: str | None = "20261107_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", mysql.BINARY(16), nullable=False),
        sa.Column("subject_user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=False),
        sa.Column("secret_expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("secret_ciphertext", mysql.VARBINARY(2048), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("available_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("published_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "delivery_attempts", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("outcome", sa.String(9), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('STAFF_REGISTERED','STAFF_APPROVED',"
            "'STAFF_REJECTED','PASSWORD_RESET','STAFF_REAPPLY_PROOF')",
            name="ck_outbox_events_event_type",
        ),
        sa.CheckConstraint(
            "(outcome IS NULL AND finished_at IS NULL) OR "
            "(outcome IN ('SENT','FAILED','SKIPPED') AND finished_at IS NOT NULL)",
            name="ck_outbox_events_outcome_state",
        ),
        sa.CheckConstraint(
            "publish_attempts >= 0 AND delivery_attempts >= 0",
            name="ck_outbox_events_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "secret_ciphertext IS NULL OR secret_expires_at IS NOT NULL",
            name="ck_outbox_events_secret_expiry",
        ),
        sa.CheckConstraint(
            "available_at >= created_at", name="ck_outbox_events_availability"
        ),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_events_published_available_id",
        "outbox_events",
        ["published_at", "available_at", "id"],
    )
    op.create_index(
        "ix_outbox_events_outcome_finished_id",
        "outbox_events",
        ["outcome", "finished_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_outcome_finished_id", table_name="outbox_events")
    op.drop_index(
        "ix_outbox_events_published_available_id", table_name="outbox_events"
    )
    op.drop_table("outbox_events")
