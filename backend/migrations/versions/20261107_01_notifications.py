"""Create Admin notifications table.

Revision ID: 20261107_01
Revises: 20261106_01
Create Date: 2026-11-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261107_01"
down_revision: str | None = "20261106_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the admin_notifications table and composite inbox index."""
    op.create_table(
        "admin_notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.BigInteger(), nullable=False),
        sa.Column("approval_request_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("read_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_admin_notifications"),
        sa.UniqueConstraint(
            "approval_request_id",
            name="uq_admin_notifications_approval_request_id",
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            name="fk_admin_notifications_admin_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["staff_approval_requests.id"],
            name="fk_admin_notifications_approval_request_id",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "ix_admin_notifications_admin_user_id_read_at_created_at_id",
        "admin_notifications",
        ["admin_user_id", "read_at", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the admin_notifications table in reverse order."""
    op.drop_index(
        "ix_admin_notifications_admin_user_id_read_at_created_at_id",
        table_name="admin_notifications",
    )
    op.drop_table("admin_notifications")
