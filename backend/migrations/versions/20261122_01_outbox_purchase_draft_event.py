"""Allow PURCHASE_DRAFT_CREATED outbox events.

Revision ID: 20261122_01
Revises: 20261121_01
Create Date: 2026-11-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261122_01"
down_revision: str | None = "20261121_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = (
    "'STAFF_REGISTERED','STAFF_APPROVED','STAFF_REJECTED',"
    "'PASSWORD_RESET','STAFF_REAPPLY_PROOF'"
)


def upgrade() -> None:
    op.drop_constraint("ck_outbox_events_event_type", "outbox_events", type_="check")
    op.create_check_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        f"event_type IN ({_BASE},'PURCHASE_DRAFT_CREATED')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM outbox_events WHERE event_type = 'PURCHASE_DRAFT_CREATED'")
    op.drop_constraint("ck_outbox_events_event_type", "outbox_events", type_="check")
    op.create_check_constraint(
        "ck_outbox_events_event_type",
        "outbox_events",
        f"event_type IN ({_BASE})",
    )
