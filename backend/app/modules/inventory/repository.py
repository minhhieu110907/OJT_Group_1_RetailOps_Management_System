"""Database query and persistence primitives for the Inventory module.

Transaction invariant:
- Neither ``InventoryQueryRepository`` nor ``InventoryMovementRepository`` ever
  calls ``commit()``, ``rollback()``, ``close()``, ``begin()``, or ``begin_nested()``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, literal, select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.modules.inventory.exceptions import (
    InventoryValidationError,
    StockConflictError,
    StockItemNotFoundError,
    is_mysql_lock_conflict_error,
)
from app.modules.inventory.models import (
    Inventory,
    InventoryAdjustment,
    MovementKind,
    Product,
    StockMovement,
)
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    MAX_STOCK_QUANTITY,
    LockedStock,
    StockLockSet,
)
from app.modules.products.models import CatalogStatus

MovementProvider = Callable[
    [Session, int, int, int | None, str | None],
    tuple[list[dict[str, Any]], int],
]


def get_session_transaction_identity(session: object) -> int:
    """Return a non-zero identity token for the session's active transaction.

    For real SQLAlchemy ``Session`` objects, returns ``id(tx)`` if a transaction
    is currently active, or ``0`` if no transaction is active (e.g. after a
    ``commit()`` or ``rollback()``). For lightweight unit-test session doubles
    that do not implement ``get_transaction()``, falls back to ``id(session)``.
    """
    get_tx = getattr(session, "get_transaction", None)
    if callable(get_tx):
        tx = get_tx()
        return id(tx) if tx is not None else 0
    return id(session)


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
        """Query append-only stock movement history from database."""
        if self._movement_provider is not None:
            return self._movement_provider(session, page, page_size, product_id, kind)

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

        count_sql = f"SELECT COUNT(*) FROM stock_movements sm {where_sql}"

        total = session.execute(text(count_sql), params).scalar() or 0
        rows = session.execute(text(query_sql), params).mappings().all()
        return [dict(row) for row in rows], total


class InventoryMovementRepository:
    """Persistence primitives for inventory locks, guarded updates, and movements.

    Transaction invariant:
    - This repository NEVER calls ``commit()``, ``rollback()``, ``close()``,
      ``begin()``, or ``begin_nested()``.
    """

    def lock_products_and_inventory(
        self,
        session: Session,
        sorted_product_ids: Sequence[int],
    ) -> StockLockSet:
        """Acquire FOR UPDATE locks in order: Product ID ASC -> Inventory ID ASC."""
        if not sorted_product_ids:
            return StockLockSet(
                rows={},
                session_identity=id(session),
                transaction_identity=get_session_transaction_identity(session),
            )

        ordered_ids = list(sorted_product_ids)
        try:
            products_by_id: dict[int, Product] = {}
            for product_id in ordered_ids:
                product = session.scalar(
                    select(Product)
                    .where(Product.id == product_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if product is not None:
                    products_by_id[product_id] = product

            missing_products = [pid for pid in ordered_ids if pid not in products_by_id]
            if missing_products:
                raise StockItemNotFoundError(product_ids=missing_products)

            inventories_by_id: dict[int, Inventory] = {}
            for product_id in ordered_ids:
                inv = session.scalar(
                    select(Inventory)
                    .where(Inventory.product_id == product_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if inv is not None:
                    inventories_by_id[product_id] = inv

            missing_inventories = [
                pid for pid in ordered_ids if pid not in inventories_by_id
            ]
            if missing_inventories:
                raise StockItemNotFoundError(product_ids=missing_inventories)
        except (OperationalError, DBAPIError) as error:
            if is_mysql_lock_conflict_error(error):
                raise StockConflictError(
                    "Xung đột khóa dữ liệu tồn kho (deadlock/timeout), "
                    "vui lòng thử lại."
                ) from error
            raise

        locked_rows: dict[int, LockedStock] = {}
        for pid in ordered_ids:
            prod = products_by_id[pid]
            inv = inventories_by_id[pid]
            locked_rows[pid] = LockedStock(
                product_id=pid,
                sku=prod.sku,
                name=prod.name,
                status=prod.status,
                sale_price_vnd=prod.sale_price_vnd,
                quantity=inv.quantity,
                stock_version=inv.stock_version,
            )

        return StockLockSet(
            rows=locked_rows,
            session_identity=id(session),
            transaction_identity=get_session_transaction_identity(session),
        )

    def guarded_update_balance(
        self,
        session: Session,
        *,
        product_id: int,
        expected_version: int,
        new_quantity: int,
        now: datetime,
    ) -> bool:
        """Atomically update inventory balance and increment stock_version by +1."""
        if new_quantity < 0:
            return False
        if new_quantity > MAX_STOCK_QUANTITY:
            # Defense in depth: never send an out-of-range INT to MySQL.
            raise InventoryValidationError(
                "Số lượng tồn kho sau biến động vượt quá giới hạn SQL INT.",
                details={
                    "product_id": product_id,
                    "max_quantity": MAX_STOCK_QUANTITY,
                },
            )

        first_stocked_expr = case(
            (
                (Inventory.first_stocked_at.is_(None)) & (new_quantity > 0),
                now,
            ),
            else_=Inventory.first_stocked_at,
        )

        stmt = (
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
                Inventory.stock_version == expected_version,
                new_quantity >= 0,
            )
            .values(
                quantity=new_quantity,
                stock_version=Inventory.stock_version + 1,
                first_stocked_at=first_stocked_expr,
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = session.execute(stmt)
        except (OperationalError, DBAPIError) as error:
            if is_mysql_lock_conflict_error(error):
                raise StockConflictError(
                    "Xung đột khóa dữ liệu tồn kho khi cập nhật số dư."
                ) from error
            raise

        return int(result.rowcount or 0) == 1

    def find_existing_movement(
        self,
        session: Session,
        *,
        kind: MovementKind,
        product_id: int,
        receipt_id: int | None = None,
        order_id: int | None = None,
        adjustment_id: int | None = None,
    ) -> StockMovement | None:
        """Look up an existing StockMovement for a single product and source ref."""
        stmt = select(StockMovement).where(
            StockMovement.product_id == product_id,
            StockMovement.kind == kind.value,
        )
        if kind == MovementKind.PURCHASE_CONFIRM:
            stmt = stmt.where(StockMovement.receipt_id == receipt_id)
        elif kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}:
            stmt = stmt.where(StockMovement.order_id == order_id)
        elif kind == MovementKind.ADJUSTMENT:
            stmt = stmt.where(StockMovement.adjustment_id == adjustment_id)

        return session.scalar(stmt)

    def find_movements_by_reference(
        self,
        session: Session,
        *,
        kind: MovementKind,
        reference_id: int,
    ) -> list[StockMovement]:
        """Look up all StockMovement rows recorded for a document reference."""
        stmt = select(StockMovement).where(StockMovement.kind == kind.value)
        if kind == MovementKind.PURCHASE_CONFIRM:
            stmt = stmt.where(StockMovement.receipt_id == reference_id)
        elif kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}:
            stmt = stmt.where(StockMovement.order_id == reference_id)
        else:
            stmt = stmt.where(StockMovement.adjustment_id == reference_id)

        stmt = stmt.order_by(StockMovement.product_id.asc(), StockMovement.id.asc())
        return list(session.scalars(stmt))

    def add_adjustment(
        self,
        session: Session,
        adjustment: InventoryAdjustment,
    ) -> InventoryAdjustment:
        """Stage and flush an InventoryAdjustment audit row."""
        session.add(adjustment)
        session.flush()
        return adjustment

    def add_movement(
        self,
        session: Session,
        movement: StockMovement,
    ) -> StockMovement:
        """Stage and flush a StockMovement ledger row."""
        session.add(movement)
        session.flush()
        return movement


__all__ = [
    "InventoryMovementRepository",
    "InventoryQueryRepository",
    "MovementProvider",
    "get_session_transaction_identity",
]
