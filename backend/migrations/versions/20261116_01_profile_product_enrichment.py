"""Add nullable user full name and product image URL.

Revision ID: 20261116_01
Revises: 20261113_01
Create Date: 2026-11-16

MySQL executes ALTER TABLE with implicit commits. Upgrade and downgrade are
therefore intentionally limited to the two independent nullable columns and
must be run only after backup/restore readiness has been confirmed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261116_01"
down_revision: str | None = "20261113_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("image_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "users", sa.Column("full_name", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "full_name")
    op.drop_column("products", "image_url")
