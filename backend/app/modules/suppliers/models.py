"""SQLAlchemy ORM model for suppliers."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Imported so the supplier_categories -> categories FK resolves whenever the
# suppliers models are used on their own (e.g. isolated unit-test metadata).
from app.modules.categories.models import Category  # noqa: F401


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


class SupplierCategory(Base):
    """Optional many-to-many link: categories a supplier is able to provide.

    Used only as a UX filter hint when drafting purchase receipts; it never
    restricts which products a receipt may contain (PUR-01..PUR-05 unchanged).
    Deleting a supplier removes its links; a category referenced by any link
    cannot be hard-deleted (categories are only ever deactivated).
    """

    __tablename__ = "supplier_categories"

    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "suppliers.id",
            name="fk_supplier_categories_supplier_id_suppliers",
            ondelete="CASCADE",
        ),
        nullable=False,
        autoincrement=False,
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "categories.id",
            name="fk_supplier_categories_category_id_categories",
            ondelete="RESTRICT",
        ),
        nullable=False,
        autoincrement=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "supplier_id", "category_id", name="pk_supplier_categories"
        ),
        Index("ix_supplier_categories_category_id", "category_id"),
    )
