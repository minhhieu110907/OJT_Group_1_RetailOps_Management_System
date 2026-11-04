"""Establish an empty migration baseline.

Revision ID: 20261105_01
Revises: None
Create Date: 2026-11-05
"""

from collections.abc import Sequence

revision: str = "20261105_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the baseline without creating business tables."""


def downgrade() -> None:
    """Remove the empty baseline revision."""
