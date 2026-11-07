"""SQLAlchemy ORM model for categories."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CategoryStatus(StrEnum):
    """Supported category status values."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Category(Base):
    """Product category."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=CategoryStatus.ACTIVE,
        server_default=text("'ACTIVE'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_categories"),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_categories_status",
        ),
    )

