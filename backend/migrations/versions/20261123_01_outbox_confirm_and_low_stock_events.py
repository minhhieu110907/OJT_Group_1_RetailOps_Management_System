"""Add PURCHASE_RECEIPT_CONFIRMED and LOW_STOCK_ALERT to outbox_events.

Revision ID: 20261123_01
Revises: 20261122_01
Create Date: 2026-11-23 16:05:00
"""

from alembic import op

revision = "20261123_01"
down_revision = "20261122_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        (
            "event_type IN ('STAFF_REGISTERED','STAFF_APPROVED',"
            "'STAFF_REJECTED','PASSWORD_RESET','STAFF_REAPPLY_PROOF',"
            "'PURCHASE_DRAFT_CREATED','PURCHASE_RECEIPT_CONFIRMED',"
            "'LOW_STOCK_ALERT')"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        (
            "event_type IN ('STAFF_REGISTERED','STAFF_APPROVED',"
            "'STAFF_REJECTED','PASSWORD_RESET','STAFF_REAPPLY_PROOF',"
            "'PURCHASE_DRAFT_CREATED')"
        ),
    )
