"""Database persistence and query primitives for inventory."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.products.models import Inventory, Product


class InventoryQueryRepository:
    """Read repository for querying inventory records joined with products."""

    def list_inventory(
        self,
        session: Session,
        page: int,
        page_size: int,
        category_id: int | None = None,
        status: str | None = None,
        in_stock: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query paginated inventory records joined with products.

        Applies filters and tie-breaker sorting by Product.id ASC.
        """
        stmt = select(
            Product.id.label("product_id"),
            Product.sku.label("sku"),
            Product.name.label("name"),
            Product.category_id.label("category_id"),
            Product.status.label("status"),
            Inventory.quantity.label("quantity"),
            Inventory.stock_version.label("stock_version"),
            Inventory.first_stocked_at.label("first_stocked_at"),
        ).join(Inventory, Product.id == Inventory.product_id)

        count_stmt = select(func.count(Product.id)).join(
            Inventory, Product.id == Inventory.product_id
        )

        if category_id is not None:
            stmt = stmt.where(Product.category_id == category_id)
            count_stmt = count_stmt.where(Product.category_id == category_id)

        if status is not None:
            status_val = status.value if hasattr(status, "value") else str(status)
            stmt = stmt.where(Product.status == status_val)
            count_stmt = count_stmt.where(Product.status == status_val)

        if in_stock is True:
            stmt = stmt.where(Inventory.quantity > 0)
            count_stmt = count_stmt.where(Inventory.quantity > 0)
        elif in_stock is False:
            stmt = stmt.where(Inventory.quantity == 0)
            count_stmt = count_stmt.where(Inventory.quantity == 0)

        total = session.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Product.id.asc()).offset(offset).limit(page_size)

        rows = session.execute(stmt).mappings().all()
        items = [dict(row) for row in rows]
        return items, total

    def get_by_product_id(
        self, session: Session, product_id: int
    ) -> dict[str, Any] | None:
        """Query a single inventory record joined with product by product_id."""
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku.label("sku"),
                Product.name.label("name"),
                Product.category_id.label("category_id"),
                Product.status.label("status"),
                Inventory.quantity.label("quantity"),
                Inventory.stock_version.label("stock_version"),
                Inventory.first_stocked_at.label("first_stocked_at"),
            )
            .join(Inventory, Product.id == Inventory.product_id)
            .where(Product.id == product_id)
        )
        row = session.execute(stmt).mappings().first()
        return dict(row) if row is not None else None
