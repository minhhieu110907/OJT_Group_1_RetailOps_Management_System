"""Allow Staff account locking and persist immutable administration events.

Revision ID: 20261119_01
Revises: 20261118_01

MySQL 8 CHECK constraint changes use implicit-commit DDL. Run only after
verifying backup/restore readiness. Downgrade refuses to remove LOCKED support
when any locked account remains.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20261119_01"
down_revision: str | None = "20261118_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_STATUS_CHECK = (
    "(role = 'ADMIN' AND admin_slot IS NOT NULL AND admin_slot = 1 "
    "AND status = 'ACTIVE') OR "
    "(role = 'STAFF' AND admin_slot IS NULL AND status IN "
    "('PENDING_APPROVAL', 'ACTIVE', 'REJECTED', 'LOCKED'))"
)

OLD_USER_STATUS_CHECK = (
    "(role = 'ADMIN' AND admin_slot IS NOT NULL AND admin_slot = 1 "
    "AND status = 'ACTIVE') OR "
    "(role = 'STAFF' AND admin_slot IS NULL AND status IN "
    "('PENDING_APPROVAL', 'ACTIVE', 'REJECTED'))"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_users_role_status_admin_slot", "users", type_="check"
    )
    op.create_check_constraint(
        "ck_users_role_status_admin_slot", "users", USER_STATUS_CHECK
    )
    op.create_table(
        "staff_account_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_staff_account_events_actor"
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name="fk_staff_account_events_target",
        ),
        sa.CheckConstraint(
            "action IN ('LOCK', 'UNLOCK')", name="ck_staff_account_events_action"
        ),
    )
    op.create_index(
        "ix_staff_account_events_target_time",
        "staff_account_events",
        ["target_user_id", "created_at", "id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.scalar(
        sa.text("SELECT COUNT(*) FROM users WHERE status = 'LOCKED'")
    )
    if count:
        raise RuntimeError(
            "Cannot downgrade: unlock all LOCKED accounts through the "
            "approved operational procedure first."
        )
    op.drop_index(
        "ix_staff_account_events_target_time", table_name="staff_account_events"
    )
    op.drop_table("staff_account_events")
    op.drop_constraint(
        "ck_users_role_status_admin_slot", "users", type_="check"
    )
    op.create_check_constraint(
        "ck_users_role_status_admin_slot", "users", OLD_USER_STATUS_CHECK
    )
