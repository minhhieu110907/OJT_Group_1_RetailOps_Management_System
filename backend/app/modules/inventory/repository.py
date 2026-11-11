"""SQLAlchemy repository for Inventory locking, guarded updates, and Stock Movements."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, select, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.modules.inventory.exceptions import (
    StockConflictError,
    StockItemNotFoundError,
)
from app.modules.inventory.models import (
    Inventory,
    InventoryAdjustment,
    MovementKind,
    Product,
    StockMovement,
)
from app.modules.inventory.schemas import LockedStock, StockLockSet

MYSQL_LOCK_WAIT_TIMEOUT_CODE = 1205
MYSQL_DEADLOCK_CODE = 1213


def is_mysql_lock_conflict_error(error: DBAPIError) -> bool:
    """Return True when MySQL reports InnoDB deadlock (1213) or lock timeout (1205)."""
    orig = getattr(error, "orig", None)
    args = getattr(orig, "args", ())
    if args and isinstance(args[0], int):
        return args[0] in {MYSQL_LOCK_WAIT_TIMEOUT_CODE, MYSQL_DEADLOCK_CODE}
    text_msg = str(orig if orig is not None else error).lower()
    return "deadlock" in text_msg or "lock wait timeout" in text_msg


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
            return StockLockSet(rows={}, session_identity=id(session))

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

        return StockLockSet(rows=locked_rows, session_identity=id(session))

    def guarded_update_balance(
        self,
        session: Session,
        *,
        product_id: int,
        expected_version: int,
        new_quantity: int,
        now: datetime,
    ) -> bool:
        """Atomically update inventory balance with version and non-negative guards."""
        if new_quantity < 0:
            return False

        first_stocked_expr = (
            case(
                (Inventory.first_stocked_at.is_(None), now),
                else_=Inventory.first_stocked_at,
            )
            if new_quantity > 0
            else Inventory.first_stocked_at
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
            session.flush()
        except (OperationalError, DBAPIError) as error:
            if is_mysql_lock_conflict_error(error):
                raise StockConflictError(
                    "Xung đột cập nhật tồn kho đồng thời, vui lòng thử lại."
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
        """Look up an already-recorded movement for the same business reference."""
        if kind == MovementKind.PURCHASE_CONFIRM and receipt_id is not None:
            return session.scalar(
                select(StockMovement).where(
                    StockMovement.receipt_id == receipt_id,
                    StockMovement.product_id == product_id,
                )
            )
        if (
            kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}
            and order_id is not None
        ):
            return session.scalar(
                select(StockMovement).where(
                    StockMovement.order_id == order_id,
                    StockMovement.product_id == product_id,
                    StockMovement.kind == kind.value,
                )
            )
        if kind == MovementKind.ADJUSTMENT and adjustment_id is not None:
            return session.scalar(
                select(StockMovement).where(
                    StockMovement.adjustment_id == adjustment_id,
                    StockMovement.product_id == product_id,
                )
            )
        return None

    def add_adjustment(
        self,
        session: Session,
        adjustment: InventoryAdjustment,
    ) -> InventoryAdjustment:
        """Persist an InventoryAdjustment audit row and flush to obtain its ID."""
        session.add(adjustment)
        session.flush()
        return adjustment

    def add_movement(
        self,
        session: Session,
        movement: StockMovement,
    ) -> StockMovement:
        """Persist a StockMovement ledger row and flush to obtain its ID."""
        session.add(movement)
        session.flush()
        return movement
