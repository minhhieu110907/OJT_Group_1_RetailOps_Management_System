"""Database persistence and query primitives for inventory."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, inspect, literal, select, text
from sqlalchemy.orm import Session

from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD
from app.modules.products.models import CatalogStatus, Inventory, Product

MovementProvider = Callable[
    [Session, int, int, int | None, str | None],
    tuple[list[dict[str, Any]], int],
]


class InventoryQueryRepository:
    """Read repository for inventory, low-stock alerts, and movement queries."""

    def __init__(
        self,
        movement_provider: MovementProvider | None = None,
    ) -> None:
        self._movement_provider = movement_provider

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

    def list_low_stock(
        self,
        session: Session,
        page: int,
        page_size: int,
        threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query products with active status and inventory quantity <= threshold.

        Sorted by quantity ASC and Product.id ASC.
        """
        active_status = CatalogStatus.ACTIVE.value
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.sku.label("sku"),
                Product.name.label("name"),
                Inventory.quantity.label("quantity"),
                literal(threshold).label("threshold"),
            )
            .join(Inventory, Product.id == Inventory.product_id)
            .where(
                Product.status == active_status,
                Inventory.quantity <= threshold,
            )
        )
        count_stmt = (
            select(func.count(Product.id))
            .join(Inventory, Product.id == Inventory.product_id)
            .where(
                Product.status == active_status,
                Inventory.quantity <= threshold,
            )
        )

        total = session.scalar(count_stmt) or 0
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(Inventory.quantity.asc(), Product.id.asc())
            .offset(offset)
            .limit(page_size)
        )

        rows = session.execute(stmt).mappings().all()
        items = [dict(row) for row in rows]
        return items, total

    def list_stock_movements(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query append-only stock movement history with safe runtime fallback."""
        if self._movement_provider is not None:
            return self._movement_provider(session, page, page_size, product_id, kind)

        try:
            has_table = inspect(session.connection()).has_table("stock_movements")
        except Exception:
            has_table = False

        if not has_table:
            return [], 0

        where_clauses: list[str] = []
        params: dict[str, Any] = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }

        if product_id is not None:
            where_clauses.append("sm.product_id = :product_id")
            params["product_id"] = product_id

        if kind is not None:
            where_clauses.append("sm.kind = :kind")
            params["kind"] = kind

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        has_adj_table = False
        try:
            has_adj_table = inspect(session.connection()).has_table(
                "inventory_adjustments"
            )
        except Exception:
            has_adj_table = False

        if has_adj_table:
            query_sql = f"""
                SELECT
                    sm.id,
                    sm.product_id,
                    sm.sku_snapshot AS sku,
                    sm.kind,
                    sm.quantity_before,
                    sm.quantity_after,
                    sm.stock_version_after,
                    COALESCE(
                        sm.receipt_id, sm.order_id, sm.adjustment_id
                    ) AS reference_id,
                    sm.occurred_at,
                    sm.actor_id,
                    adj.reason AS adjustment_reason
                FROM stock_movements sm
                LEFT JOIN inventory_adjustments adj ON sm.adjustment_id = adj.id
                {where_sql}
                ORDER BY sm.occurred_at DESC, sm.id DESC
                LIMIT :limit OFFSET :offset
            """
        else:
            query_sql = f"""
                SELECT
                    sm.id,
                    sm.product_id,
                    sm.sku_snapshot AS sku,
                    sm.kind,
                    sm.quantity_before,
                    sm.quantity_after,
                    sm.stock_version_after,
                    COALESCE(
                        sm.receipt_id, sm.order_id, sm.adjustment_id
                    ) AS reference_id,
                    sm.occurred_at,
                    sm.actor_id,
                    NULL AS adjustment_reason
                FROM stock_movements sm
                {where_sql}
                ORDER BY sm.occurred_at DESC, sm.id DESC
                LIMIT :limit OFFSET :offset
            """

        count_sql = f"SELECT COUNT(*) FROM stock_movements sm {where_sql}"

        total = session.execute(text(count_sql), params).scalar() or 0
        rows = session.execute(text(query_sql), params).mappings().all()
        return [dict(row) for row in rows], total
