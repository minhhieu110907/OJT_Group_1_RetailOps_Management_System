"""Create the authentication database foundation.

Revision ID: 20261106_01
Revises: 20261105_01
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261106_01"
down_revision: str | None = "20261105_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only the four ERD-approved Auth tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "email_normalized",
            sa.String(length=254, collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("admin_slot", mysql.TINYINT(), nullable=True),
        sa.Column("last_reapplied_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "(role = 'ADMIN' AND admin_slot IS NOT NULL AND admin_slot = 1 "
            "AND status = 'ACTIVE') OR "
            "(role = 'STAFF' AND admin_slot IS NULL AND status IN "
            "('PENDING_APPROVAL', 'ACTIVE', 'REJECTED'))",
            name="ck_users_role_status_admin_slot",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("admin_slot", name="uq_users_admin_slot"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
    )
    op.create_table(
        "staff_approval_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("requested_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint("attempt_no > 0", name="ck_staff_approval_attempt_positive"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_by IS NULL AND decided_at IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') "
            "AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND decided_at >= requested_at)",
            name="ck_staff_approval_decision_state",
        ),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "attempt_no", name="uq_staff_approval_user_attempt"
        ),
    )
    op.create_index(
        "ix_staff_approval_status_requested_id",
        "staff_approval_requests",
        ["status", "requested_at", "id"],
        unique=False,
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", mysql.BINARY(length=16), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at "
            "AND expires_at <= DATE_ADD(created_at, INTERVAL 8 HOUR)",
            name="ck_auth_sessions_expiry",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_user_revoked",
        "auth_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("token_digest", mysql.BINARY(length=32), nullable=False),
        sa.Column("session_id", mysql.BINARY(length=16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("issued_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "generation >= 0 AND (consumed_at IS NULL OR consumed_at >= issued_at)",
            name="ck_refresh_tokens_generation_consumption",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"]),
        sa.PrimaryKeyConstraint("token_digest"),
        sa.UniqueConstraint(
            "session_id", "generation", name="uq_refresh_tokens_session_generation"
        ),
    )


def downgrade() -> None:
    """Remove the Auth foundation in reverse dependency order."""
    op.drop_table("refresh_tokens")
    op.drop_index("ix_auth_sessions_user_revoked", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(
        "ix_staff_approval_status_requested_id",
        table_name="staff_approval_requests",
    )
    op.drop_table("staff_approval_requests")
    op.drop_table("users")
