"""SQLAlchemy ORM model for suppliers."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupplierStatus(StrEnum):
    """Supported supplier status values."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Supplier(Base):
    """Product supplier."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    contact_email: Mapped[str | None] = mapped_column(
        String(254),
        nullable=True,
    )
    contact_phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=SupplierStatus.ACTIVE,
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
        PrimaryKeyConstraint("id", name="pk_suppliers"),
        CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')",
            name="ck_suppliers_status",
        ),
    )
