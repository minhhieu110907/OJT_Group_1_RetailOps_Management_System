"""SQLAlchemy ORM models for purchase receipts and receipt line items."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PurchaseReceipt(Base):
    """Purchase receipt header (DRAFT, CONFIRMED, or CANCELLED)."""

    __tablename__ = "purchase_receipts"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    supplier_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "suppliers.id",
            name="fk_purchase_receipts_supplier_id_suppliers",
        ),
        nullable=False,
    )
    supplier_name_snapshot: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(9),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
    )
    draft_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    total_vnd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_purchase_receipts_created_by_users",
        ),
        nullable=False,
    )
    closed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_purchase_receipts_closed_by_users",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_purchase_receipts"),
        CheckConstraint(
            "draft_version >= 1 AND total_vnd >= 0",
            name="ck_purchase_receipts_version_and_total",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND closed_by IS NULL AND closed_at IS NULL) "
            "OR (status IN ('CONFIRMED','CANCELLED') "
            "AND closed_by IS NOT NULL "
            "AND closed_at IS NOT NULL "
            "AND supplier_name_snapshot IS NOT NULL)",
            name="ck_purchase_receipts_status_lifecycle",
        ),
        Index(
            "ix_purchase_receipts_created_at_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_purchase_receipts_status_created_at_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_purchase_receipts_supplier_id_created_at_id",
            "supplier_id",
            "created_at",
            "id",
        ),
    )


class PurchaseReceiptItem(Base):
    """Line item belonging to a purchase receipt with composite PK."""

    __tablename__ = "purchase_receipt_items"

    receipt_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "purchase_receipts.id",
            name="fk_purchase_receipt_items_receipt_id_purchase_receipts",
        ),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "products.id",
            name="fk_purchase_receipt_items_product_id_products",
        ),
        nullable=False,
    )
    sku_snapshot: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    product_name_snapshot: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    unit_cost_vnd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    line_total_vnd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "receipt_id",
            "product_id",
            name="pk_purchase_receipt_items",
        ),
        CheckConstraint(
            "quantity > 0 AND unit_cost_vnd >= 0 "
            "AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_cost_vnd",
            name="ck_purchase_receipt_items_qty_cost_line_total",
        ),
    )

