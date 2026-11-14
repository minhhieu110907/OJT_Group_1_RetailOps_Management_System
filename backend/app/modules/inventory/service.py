"""Inventory query and mutation services.

Provides:
1. ``InventoryQueryService`` (T04A6BD): read-only paginated list and detail queries.
2. ``InventoryService`` (T04A653): unified stock mutation entry point
   ``apply_stock_change()``, thin wrappers (``increase``, ``decrease``,
   ``return_stock``, ``adjust``), and frozen CF-02 contract methods
   (``lock_for_mutation``, ``increase_for_receipt``, ``decrease_for_checkout``,
   ``restore_for_cancel``, ``adjust_to_count``).

Architectural invariants:
- Never calls ``session.commit()``, ``session.rollback()``, ``session.close()``,
  ``session.begin()``, or ``session.begin_nested()``.
- Enforces deterministic ascending lock order: Product ID ASC -> Inventory ID ASC.
- ``StockLockSet`` is bound to a single active ``(Session, SessionTransaction)``
  and is single-use (cannot be cached, reused after commit/rollback, or reused
  across multiple mutations).
- Guarantees non-negative inventory balances at both service and DB layers.
- Guarantees atomic whole-document idempotent replay or strict duplicate rejection
  before mutating any row.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.modules.inventory.exceptions import (
    DuplicateMovementError,
    InactiveProductStockError,
    InsufficientStockError,
    InventoryValidationError,
    StaleStockVersionError,
    StockConflictError,
    StockItemNotFoundError,
    classify_movement_integrity_error,
)
from app.modules.inventory.models import (
    InventoryAdjustment,
    MovementKind,
    MovementType,
    ProductStatus,
    ReferenceType,
    StockMovement,
)
from app.modules.inventory.repository import (
    InventoryMovementRepository,
    InventoryQueryRepository,
    get_session_transaction_identity,
)
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    MAX_STOCK_QUANTITY,
    AdjustmentResult,
    CountAdjustment,
    InventoryPage,
    InventoryRead,
    LowStockItem,
    LowStockPage,
    StockChangeItem,
    StockLine,
    StockLockSet,
    StockMovementAdminPage,
    StockMovementAdminRead,
    StockMovementPage,
    StockMovementRead,
    StockMovementResult,
    StockResult,
)

_MOVEMENT_TYPE_TO_KIND: dict[MovementType, MovementKind] = {
    MovementType.INCREASE: MovementKind.PURCHASE_CONFIRM,
    MovementType.DECREASE: MovementKind.SALE,
    MovementType.RETURN: MovementKind.ORDER_CANCEL,
    MovementType.ADJUST: MovementKind.ADJUSTMENT,
}

_MOVEMENT_KIND_TO_TYPE: dict[MovementKind, MovementType] = {
    MovementKind.PURCHASE_CONFIRM: MovementType.INCREASE,
    MovementKind.SALE: MovementType.DECREASE,
    MovementKind.ORDER_CANCEL: MovementType.RETURN,
    MovementKind.ADJUSTMENT: MovementType.ADJUST,
}

_KIND_TO_DEFAULT_REFERENCE_TYPE: dict[MovementKind, ReferenceType] = {
    MovementKind.PURCHASE_CONFIRM: ReferenceType.RECEIPT,
    MovementKind.SALE: ReferenceType.ORDER,
    MovementKind.ORDER_CANCEL: ReferenceType.ORDER,
    MovementKind.ADJUSTMENT: ReferenceType.ADJUSTMENT,
}


def _utc_now_naive() -> datetime:
    """Return current UTC timestamp as naive datetime(6) for MySQL storage."""
    return datetime.now(UTC).replace(tzinfo=None)


def _is_strict_int(value: object) -> bool:
    """Return True if value is a Python int and NOT a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _ensure_merged_quantity_in_int_range(product_id: int, quantity: int) -> None:
    """Reject a merged line quantity that cannot be stored in a SQL INT column."""
    if quantity > MAX_STOCK_QUANTITY:
        raise InventoryValidationError(
            "Tổng số lượng sau khi gộp vượt quá giới hạn SQL INT.",
            details={
                "product_id": product_id,
                "max_quantity": MAX_STOCK_QUANTITY,
            },
        )


def normalize_lock_order(product_ids: Sequence[int]) -> list[int]:
    """Validate, deduplicate, and sort product IDs in ascending lock order."""
    if not product_ids:
        raise InventoryValidationError(
            "Danh sách sản phẩm cần khóa không được để trống."
        )

    unique_ids: set[int] = set()
    for pid in product_ids:
        if not _is_strict_int(pid) or pid <= 0:
            raise InventoryValidationError(
                "Mã sản phẩm (product_id) phải là số nguyên dương."
            )
        unique_ids.add(pid)

    return sorted(unique_ids)


def merge_and_sort_stock_lines(lines: Sequence[StockLine]) -> list[StockLine]:
    """Validate, merge duplicate product lines, and sort by product_id ASC."""
    if not lines:
        raise InventoryValidationError(
            "Danh sách dòng biến động tồn kho không được để trống."
        )

    merged: dict[int, int] = {}
    for line in lines:
        if not _is_strict_int(line.product_id) or line.product_id <= 0:
            raise InventoryValidationError(
                "Mã sản phẩm (product_id) phải là số nguyên dương."
            )
        if not _is_strict_int(line.quantity) or line.quantity <= 0:
            raise InventoryValidationError(
                "Số lượng biến động (quantity) phải là số nguyên dương (> 0)."
            )
        merged[line.product_id] = merged.get(line.product_id, 0) + line.quantity
        _ensure_merged_quantity_in_int_range(line.product_id, merged[line.product_id])

    return [
        StockLine(product_id=pid, quantity=merged[pid]) for pid in sorted(merged.keys())
    ]


class InventoryQueryService:
    """Orchestrates inventory read queries and builds response DTOs."""

    def __init__(self, repository: InventoryQueryRepository | None = None) -> None:
        self._repository = repository or InventoryQueryRepository()

    def list_inventory(
        self,
        session: Session,
        page: int,
        page_size: int,
        category_id: int | None = None,
        status: str | None = None,
        in_stock: bool | None = None,
    ) -> InventoryPage:
        """Fetch paginated inventory items and return as InventoryPage."""
        items, total = self._repository.list_inventory(
            session=session,
            page=page,
            page_size=page_size,
            category_id=category_id,
            status=status,
            in_stock=in_stock,
        )
        return InventoryPage(
            items=[InventoryRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_inventory(self, session: Session, product_id: int) -> InventoryRead:
        """Fetch inventory item by product ID or raise ResourceNotFoundError."""
        item = self._repository.get_by_product_id(
            session=session, product_id=product_id
        )
        if item is None:
            raise ResourceNotFoundError(
                "Không tìm thấy thông tin tồn kho cho sản phẩm yêu cầu."
            )
        return InventoryRead.model_validate(item)

    def get_low_stock(
        self,
        session: Session,
        page: int,
        page_size: int,
        threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
    ) -> LowStockPage:
        """Fetch active products with inventory quantity <= threshold."""
        items, total = self._repository.list_low_stock(
            session=session,
            page=page,
            page_size=page_size,
            threshold=threshold,
        )
        return LowStockPage(
            items=[LowStockItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements_admin(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
    ) -> StockMovementAdminPage:
        """Fetch audited stock movement history for ADMIN."""
        items, total = self._repository.list_stock_movements(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
        return StockMovementAdminPage(
            items=[StockMovementAdminRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements_staff(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
    ) -> StockMovementPage:
        """Fetch safe public stock movement history for STAFF."""
        items, total = self._repository.list_stock_movements(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
        staff_items: list[StockMovementRead] = []
        for item in items:
            item_data = {
                "id": item["id"],
                "product_id": item["product_id"],
                "sku": item["sku"],
                "kind": item["kind"],
                "quantity_before": item["quantity_before"],
                "quantity_after": item["quantity_after"],
                "stock_version_after": item["stock_version_after"],
                "reference_id": item["reference_id"],
                "occurred_at": item["occurred_at"],
            }
            staff_items.append(StockMovementRead.model_validate(item_data))

        return StockMovementPage(
            items=staff_items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
        is_admin: bool = False,
    ) -> StockMovementPage | StockMovementAdminPage:
        """Fetch stock movement history with role-appropriate projection."""
        if is_admin:
            return self.list_stock_movements_admin(
                session=session,
                page=page,
                page_size=page_size,
                product_id=product_id,
                kind=kind,
            )
        return self.list_stock_movements_staff(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )


class InventoryService:
    """Unified Inventory Service for stock mutations and CF-02 contract port."""

    def __init__(
        self,
        repository: InventoryMovementRepository | None = None,
        clock: Callable[[], datetime] = _utc_now_naive,
    ) -> None:
        self._repository = repository or InventoryMovementRepository()
        self._clock = clock

    # ------------------------------------------------------------------
    # Locking primitive (CF-02)
    # ------------------------------------------------------------------

    def lock_for_mutation(
        self,
        session: Session,
        *,
        product_ids: Sequence[int],
    ) -> StockLockSet:
        """Lock Product rows ASC then Inventory rows ASC under SELECT ... FOR UPDATE."""
        sorted_ids = normalize_lock_order(product_ids)
        return self._repository.lock_products_and_inventory(session, sorted_ids)

    # ------------------------------------------------------------------
    # Unified entry point + thin wrappers
    # ------------------------------------------------------------------

    def apply_stock_change(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        movement_type: MovementType | MovementKind | str,
        reference_type: ReferenceType | str | None = None,
        reference_id: int | None = None,
        actor_id: int,
        note: str | None = None,
        locks: StockLockSet | None = None,
        idempotent_replay: bool = False,
    ) -> list[StockMovementResult]:
        """Unified entry point for INCREASE, DECREASE, RETURN, and ADJUST changes."""
        if not _is_strict_int(actor_id) or actor_id <= 0:
            raise InventoryValidationError("actor_id phải là số nguyên dương.")
        if not items:
            raise InventoryValidationError(
                "Danh sách sản phẩm biến động (items) không được rỗng."
            )

        kind, resolved_type = self._resolve_movement_kind(movement_type)
        resolved_ref_type = self._resolve_reference_type(kind, reference_type)

        if kind == MovementKind.ADJUSTMENT:
            return self._apply_adjustments(
                session,
                items=items,
                actor_id=actor_id,
                note=note,
                locks=locks,
            )

        if (
            reference_id is None
            or not _is_strict_int(reference_id)
            or reference_id <= 0
        ):
            raise InventoryValidationError(
                "reference_id phải là số nguyên dương đối với "
                "nghiệp vụ tăng/giảm/hoàn tồn."
            )

        normalized_items = self._normalize_and_merge_delta_items(items)
        active_locks = self._consume_or_acquire_lock_set(
            session,
            locks=locks,
            required_product_ids=[item.product_id for item in normalized_items],
        )

        # Look up all existing movements for (kind, reference_id) before mutating
        existing_by_pid = self._load_reference_movements_map(
            session,
            kind=kind,
            reference_id=reference_id,
            candidate_product_ids=[item.product_id for item in normalized_items],
        )

        if existing_by_pid:
            if not idempotent_replay:
                first_dup_pid = next(iter(existing_by_pid.keys()))
                raise DuplicateMovementError(
                    details={
                        "product_id": first_dup_pid,
                        "kind": kind.value,
                        "reference_id": reference_id,
                    }
                )

            requested_pids = {item.product_id for item in normalized_items}
            if requested_pids != set(existing_by_pid.keys()):
                raise DuplicateMovementError(
                    details={
                        "kind": kind.value,
                        "reference_id": reference_id,
                        "requested_product_ids": sorted(requested_pids),
                        "recorded_product_ids": sorted(existing_by_pid.keys()),
                    }
                )

            replayed_results: list[StockMovementResult] = []
            for item in normalized_items:
                assert item.quantity is not None
                signed_delta = (
                    -item.quantity if kind == MovementKind.SALE else item.quantity
                )
                existing = existing_by_pid[item.product_id]
                version_before = existing.stock_version_after - 1
                if (
                    existing.delta != signed_delta
                    or existing.actor_id != actor_id
                    or (
                        item.expected_stock_version is not None
                        and item.expected_stock_version != version_before
                    )
                ):
                    raise DuplicateMovementError(
                        details={
                            "product_id": item.product_id,
                            "kind": kind.value,
                            "reference_id": reference_id,
                        }
                    )

                replayed_results.append(
                    StockMovementResult(
                        movement_id=existing.id,
                        product_id=existing.product_id,
                        sku_snapshot=existing.sku_snapshot,
                        kind=kind,
                        movement_type=resolved_type,
                        reference_type=resolved_ref_type,
                        reference_id=reference_id,
                        actor_id=existing.actor_id,
                        quantity_before=existing.quantity_before,
                        quantity_after=existing.quantity_after,
                        delta=existing.delta,
                        stock_version_before=version_before,
                        stock_version_after=existing.stock_version_after,
                        occurred_at=existing.occurred_at,
                        movement_created=False,
                    )
                )
            return replayed_results

        # Pre-validate all locked rows before mutating any row
        for item in normalized_items:
            assert item.quantity is not None
            locked = active_locks.rows[item.product_id]
            if (
                kind in {MovementKind.PURCHASE_CONFIRM, MovementKind.SALE}
                and locked.status != ProductStatus.ACTIVE.value
            ):
                raise InactiveProductStockError(product_id=item.product_id)

            if (
                item.expected_stock_version is not None
                and locked.stock_version != item.expected_stock_version
            ):
                raise StaleStockVersionError(
                    product_id=item.product_id,
                    expected_stock_version=item.expected_stock_version,
                    current_stock_version=locked.stock_version,
                )

            signed_delta = (
                -item.quantity if kind == MovementKind.SALE else item.quantity
            )
            if locked.quantity + signed_delta < 0:
                raise InsufficientStockError(
                    product_id=item.product_id,
                    requested_quantity=item.quantity,
                    available_quantity=locked.quantity,
                )
            if locked.quantity + signed_delta > MAX_STOCK_QUANTITY:
                raise InventoryValidationError(
                    "Số lượng tồn kho sau biến động vượt quá giới hạn SQL INT.",
                    details={
                        "product_id": item.product_id,
                        "current_quantity": locked.quantity,
                        "requested_quantity": item.quantity,
                        "max_quantity": MAX_STOCK_QUANTITY,
                    },
                )

        now = self._normalize_timestamp(self._clock())
        results: list[StockMovementResult] = []

        for item in normalized_items:
            assert item.quantity is not None
            locked = active_locks.rows[item.product_id]
            signed_delta = (
                -item.quantity if kind == MovementKind.SALE else item.quantity
            )
            new_quantity = locked.quantity + signed_delta

            updated = self._repository.guarded_update_balance(
                session,
                product_id=item.product_id,
                expected_version=locked.stock_version,
                new_quantity=new_quantity,
                now=now,
            )
            if not updated:
                raise StockConflictError(
                    details={
                        "product_id": item.product_id,
                        "expected_stock_version": locked.stock_version,
                    }
                )

            new_version = locked.stock_version + 1
            movement = StockMovement(
                product_id=item.product_id,
                actor_id=actor_id,
                kind=kind.value,
                receipt_id=(
                    reference_id if kind == MovementKind.PURCHASE_CONFIRM else None
                ),
                order_id=(
                    reference_id
                    if kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}
                    else None
                ),
                adjustment_id=None,
                sku_snapshot=locked.sku,
                quantity_before=locked.quantity,
                quantity_after=new_quantity,
                stock_version_after=new_version,
                occurred_at=now,
            )
            try:
                self._repository.add_movement(session, movement)
            except IntegrityError as error:
                classification = classify_movement_integrity_error(error)
                if classification == "duplicate_movement":
                    raise DuplicateMovementError(
                        details={
                            "product_id": item.product_id,
                            "kind": kind.value,
                            "reference_id": reference_id,
                        }
                    ) from error
                if classification == "version_conflict":
                    raise StockConflictError(
                        details={
                            "product_id": item.product_id,
                            "stock_version": new_version,
                        }
                    ) from error
                raise

            results.append(
                StockMovementResult(
                    movement_id=movement.id,
                    product_id=item.product_id,
                    sku_snapshot=locked.sku,
                    kind=kind,
                    movement_type=resolved_type,
                    reference_type=resolved_ref_type,
                    reference_id=reference_id,
                    actor_id=actor_id,
                    quantity_before=locked.quantity,
                    quantity_after=new_quantity,
                    delta=signed_delta,
                    stock_version_before=locked.stock_version,
                    stock_version_after=new_version,
                    occurred_at=now,
                    movement_created=True,
                )
            )

        return results

    def increase(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        reference_id: int,
        actor_id: int,
        reference_type: ReferenceType | str = ReferenceType.RECEIPT,
        note: str | None = None,
        locks: StockLockSet | None = None,
        idempotent_replay: bool = False,
    ) -> list[StockMovementResult]:
        """Thin wrapper to increase stock (Receipt confirmation)."""
        return self.apply_stock_change(
            session,
            items=items,
            movement_type=MovementType.INCREASE,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
            note=note,
            locks=locks,
            idempotent_replay=idempotent_replay,
        )

    def decrease(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        reference_id: int,
        actor_id: int,
        reference_type: ReferenceType | str = ReferenceType.ORDER,
        note: str | None = None,
        locks: StockLockSet | None = None,
        idempotent_replay: bool = False,
    ) -> list[StockMovementResult]:
        """Thin wrapper to decrease stock (POS Checkout)."""
        return self.apply_stock_change(
            session,
            items=items,
            movement_type=MovementType.DECREASE,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
            note=note,
            locks=locks,
            idempotent_replay=idempotent_replay,
        )

    def return_stock(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        reference_id: int,
        actor_id: int,
        reference_type: ReferenceType | str = ReferenceType.ORDER,
        note: str | None = None,
        locks: StockLockSet | None = None,
        idempotent_replay: bool = False,
    ) -> list[StockMovementResult]:
        """Thin wrapper to restore stock on order cancellation."""
        return self.apply_stock_change(
            session,
            items=items,
            movement_type=MovementType.RETURN,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
            note=note,
            locks=locks,
            idempotent_replay=idempotent_replay,
        )

    def adjust(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        actor_id: int,
        note: str,
        locks: StockLockSet | None = None,
    ) -> list[StockMovementResult]:
        """Thin wrapper for physical count stock adjustment (counted_quantity)."""
        return self.apply_stock_change(
            session,
            items=items,
            movement_type=MovementType.ADJUST,
            reference_type=ReferenceType.ADJUSTMENT,
            actor_id=actor_id,
            note=note,
            locks=locks,
        )

    # ------------------------------------------------------------------
    # CF-02 Contract Methods (used by Checkout, Cancel, Receipt, Adjustment)
    # ------------------------------------------------------------------

    def increase_for_receipt(
        self,
        session: Session,
        *,
        locks: StockLockSet,
        receipt_id: int,
        actor_id: int,
        lines: Sequence[StockLine],
    ) -> list[StockResult]:
        """CF-02 contract: increase stock for a confirmed purchase receipt."""
        merged = merge_and_sort_stock_lines(lines)
        outcomes = self.apply_stock_change(
            session,
            items=[
                StockChangeItem(product_id=line.product_id, quantity=line.quantity)
                for line in merged
            ],
            movement_type=MovementKind.PURCHASE_CONFIRM,
            reference_type=ReferenceType.RECEIPT,
            reference_id=receipt_id,
            actor_id=actor_id,
            locks=locks,
            idempotent_replay=False,
        )
        return [
            StockResult(
                product_id=res.product_id,
                quantity=res.quantity_after,
                stock_version=res.stock_version_after,
            )
            for res in outcomes
        ]

    def decrease_for_checkout(
        self,
        session: Session,
        *,
        locks: StockLockSet,
        order_id: int,
        actor_id: int,
        lines: Sequence[StockLine],
    ) -> list[StockResult]:
        """CF-02 contract: decrease stock for a completed POS order."""
        merged = merge_and_sort_stock_lines(lines)
        outcomes = self.apply_stock_change(
            session,
            items=[
                StockChangeItem(product_id=line.product_id, quantity=line.quantity)
                for line in merged
            ],
            movement_type=MovementKind.SALE,
            reference_type=ReferenceType.ORDER,
            reference_id=order_id,
            actor_id=actor_id,
            locks=locks,
            idempotent_replay=False,
        )
        return [
            StockResult(
                product_id=res.product_id,
                quantity=res.quantity_after,
                stock_version=res.stock_version_after,
            )
            for res in outcomes
        ]

    def restore_for_cancel(
        self,
        session: Session,
        *,
        locks: StockLockSet,
        order_id: int,
        actor_id: int,
        lines: Sequence[StockLine],
    ) -> list[StockResult]:
        """CF-02 contract: restore stock once when a completed order is cancelled."""
        merged = merge_and_sort_stock_lines(lines)
        outcomes = self.apply_stock_change(
            session,
            items=[
                StockChangeItem(product_id=line.product_id, quantity=line.quantity)
                for line in merged
            ],
            movement_type=MovementKind.ORDER_CANCEL,
            reference_type=ReferenceType.ORDER,
            reference_id=order_id,
            actor_id=actor_id,
            locks=locks,
            idempotent_replay=False,
        )
        return [
            StockResult(
                product_id=res.product_id,
                quantity=res.quantity_after,
                stock_version=res.stock_version_after,
            )
            for res in outcomes
        ]

    def adjust_to_count(
        self,
        session: Session,
        *,
        locks: StockLockSet,
        actor_id: int,
        adjustment: CountAdjustment,
    ) -> AdjustmentResult:
        """CF-02 contract: adjust stock to counted_quantity with version guard."""
        outcomes = self.apply_stock_change(
            session,
            items=[
                StockChangeItem(
                    product_id=adjustment.product_id,
                    counted_quantity=adjustment.counted_quantity,
                    expected_stock_version=adjustment.expected_stock_version,
                )
            ],
            movement_type=MovementKind.ADJUSTMENT,
            reference_type=ReferenceType.ADJUSTMENT,
            actor_id=actor_id,
            note=adjustment.reason,
            locks=locks,
        )
        res = outcomes[0]
        assert res.audit_id is not None
        return AdjustmentResult(
            stock=StockResult(
                product_id=res.product_id,
                quantity=res.quantity_after,
                stock_version=res.stock_version_after,
            ),
            audit_id=res.audit_id,
            movement_created=res.movement_created,
            movement=res if res.movement_created else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_adjustments(
        self,
        session: Session,
        *,
        items: Sequence[StockChangeItem],
        actor_id: int,
        note: str | None,
        locks: StockLockSet | None,
    ) -> list[StockMovementResult]:
        cleaned_reason = (note or "").strip()
        if not cleaned_reason:
            raise InventoryValidationError(
                "Lý do kiểm kê (reason/note) không được để trống."
            )
        if len(cleaned_reason) > 500:
            raise InventoryValidationError(
                "Lý do kiểm kê không được vượt quá 500 ký tự."
            )

        seen_pids: set[int] = set()
        for item in items:
            if not _is_strict_int(item.product_id) or item.product_id <= 0:
                raise InventoryValidationError(
                    "Mã sản phẩm (product_id) phải là số nguyên dương."
                )
            if item.product_id in seen_pids:
                raise InventoryValidationError(
                    "Không được truyền trùng product_id trong cùng lệnh kiểm kê."
                )
            seen_pids.add(item.product_id)
            if (
                item.counted_quantity is None
                or not _is_strict_int(item.counted_quantity)
                or item.counted_quantity < 0
                or item.counted_quantity > MAX_STOCK_QUANTITY
            ):
                raise InventoryValidationError(
                    "Số lượng kiểm kê thực tế (counted_quantity) "
                    "phải là số nguyên trong khoảng 0..2147483647."
                )
            if (
                item.expected_stock_version is None
                or not _is_strict_int(item.expected_stock_version)
                or item.expected_stock_version < 0
            ):
                raise InventoryValidationError(
                    "Phiên bản tồn kho dự kiến (expected_stock_version) "
                    "phải là số nguyên >= 0."
                )

        sorted_items = sorted(items, key=lambda x: x.product_id)
        active_locks = self._consume_or_acquire_lock_set(
            session,
            locks=locks,
            required_product_ids=[item.product_id for item in sorted_items],
        )

        # Verify all expected_stock_versions before writing anything (stale always 409)
        for item in sorted_items:
            assert item.expected_stock_version is not None
            locked = active_locks.rows[item.product_id]
            if locked.stock_version != item.expected_stock_version:
                raise StaleStockVersionError(
                    product_id=item.product_id,
                    expected_stock_version=item.expected_stock_version,
                    current_stock_version=locked.stock_version,
                )

        now = self._normalize_timestamp(self._clock())
        results: list[StockMovementResult] = []

        for item in sorted_items:
            assert item.counted_quantity is not None
            assert item.expected_stock_version is not None
            locked = active_locks.rows[item.product_id]
            delta = item.counted_quantity - locked.quantity

            audit = InventoryAdjustment(
                product_id=item.product_id,
                actor_id=actor_id,
                reason=cleaned_reason,
                quantity_before=locked.quantity,
                counted_quantity=item.counted_quantity,
                version_before=locked.stock_version,
                created_at=now,
            )
            self._repository.add_adjustment(session, audit)

            # SRS INV-02: if counted_quantity == current quantity, record audit only
            # (no StockMovement, no stock_version increment).
            if delta == 0:
                results.append(
                    StockMovementResult(
                        movement_id=None,
                        product_id=item.product_id,
                        sku_snapshot=locked.sku,
                        kind=MovementKind.ADJUSTMENT,
                        movement_type=MovementType.ADJUST,
                        reference_type=ReferenceType.ADJUSTMENT,
                        reference_id=audit.id,
                        actor_id=actor_id,
                        quantity_before=locked.quantity,
                        quantity_after=locked.quantity,
                        delta=0,
                        stock_version_before=locked.stock_version,
                        stock_version_after=locked.stock_version,
                        occurred_at=now,
                        movement_created=False,
                        audit_id=audit.id,
                    )
                )
                continue

            updated = self._repository.guarded_update_balance(
                session,
                product_id=item.product_id,
                expected_version=locked.stock_version,
                new_quantity=item.counted_quantity,
                now=now,
            )
            if not updated:
                raise StockConflictError(
                    details={
                        "product_id": item.product_id,
                        "expected_stock_version": locked.stock_version,
                    }
                )

            new_version = locked.stock_version + 1
            movement = StockMovement(
                product_id=item.product_id,
                actor_id=actor_id,
                kind=MovementKind.ADJUSTMENT.value,
                receipt_id=None,
                order_id=None,
                adjustment_id=audit.id,
                sku_snapshot=locked.sku,
                quantity_before=locked.quantity,
                quantity_after=item.counted_quantity,
                stock_version_after=new_version,
                occurred_at=now,
            )
            try:
                self._repository.add_movement(session, movement)
            except IntegrityError as error:
                classification = classify_movement_integrity_error(error)
                if classification == "duplicate_movement":
                    raise DuplicateMovementError(
                        details={
                            "product_id": item.product_id,
                            "kind": MovementKind.ADJUSTMENT.value,
                            "reference_id": audit.id,
                        }
                    ) from error
                if classification == "version_conflict":
                    raise StockConflictError(
                        details={
                            "product_id": item.product_id,
                            "stock_version": new_version,
                        }
                    ) from error
                raise

            results.append(
                StockMovementResult(
                    movement_id=movement.id,
                    product_id=item.product_id,
                    sku_snapshot=locked.sku,
                    kind=MovementKind.ADJUSTMENT,
                    movement_type=MovementType.ADJUST,
                    reference_type=ReferenceType.ADJUSTMENT,
                    reference_id=audit.id,
                    actor_id=actor_id,
                    quantity_before=locked.quantity,
                    quantity_after=item.counted_quantity,
                    delta=delta,
                    stock_version_before=locked.stock_version,
                    stock_version_after=new_version,
                    occurred_at=now,
                    movement_created=True,
                    audit_id=audit.id,
                )
            )

        return results

    def _consume_or_acquire_lock_set(
        self,
        session: Session,
        *,
        locks: StockLockSet | None,
        required_product_ids: Sequence[int],
    ) -> StockLockSet:
        sorted_ids = normalize_lock_order(required_product_ids)
        if locks is None:
            acquired = self.lock_for_mutation(session, product_ids=sorted_ids)
            acquired.mark_consumed()
            return acquired

        if locks.session_identity is None or locks.session_identity != id(session):
            raise StockConflictError(
                "StockLockSet thuộc về một Session/Transaction khác "
                "và không được tái sử dụng."
            )

        current_tx_identity = get_session_transaction_identity(session)
        if current_tx_identity == 0 or (
            locks.transaction_identity is not None
            and locks.transaction_identity != current_tx_identity
        ):
            raise StockConflictError(
                "StockLockSet đã hết hiệu lực do giao dịch (transaction) "
                "đã kết thúc hoặc thay đổi."
            )

        if locks.is_consumed:
            raise StockConflictError(
                "StockLockSet đã được sử dụng cho một thao tác biến động trước đó "
                "và không được phép tái sử dụng."
            )

        missing = [pid for pid in sorted_ids if pid not in locks.rows]
        if missing:
            raise StockItemNotFoundError(product_ids=missing)

        locks.mark_consumed()
        return locks

    def _load_reference_movements_map(
        self,
        session: Session,
        *,
        kind: MovementKind,
        reference_id: int,
        candidate_product_ids: Sequence[int],
    ) -> dict[int, StockMovement]:
        movements = self._repository.find_movements_by_reference(
            session,
            kind=kind,
            reference_id=reference_id,
        )
        by_pid: dict[int, StockMovement] = {m.product_id: m for m in movements}
        if not by_pid:
            for pid in candidate_product_ids:
                existing = self._find_reference_movement(
                    session,
                    kind=kind,
                    product_id=pid,
                    reference_id=reference_id,
                )
                if existing is not None:
                    by_pid[pid] = existing
        return by_pid

    def _find_reference_movement(
        self,
        session: Session,
        *,
        kind: MovementKind,
        product_id: int,
        reference_id: int,
    ) -> StockMovement | None:
        if kind == MovementKind.PURCHASE_CONFIRM:
            return self._repository.find_existing_movement(
                session,
                kind=kind,
                product_id=product_id,
                receipt_id=reference_id,
            )
        if kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}:
            return self._repository.find_existing_movement(
                session,
                kind=kind,
                product_id=product_id,
                order_id=reference_id,
            )
        return None

    @staticmethod
    def _normalize_and_merge_delta_items(
        items: Sequence[StockChangeItem],
    ) -> list[StockChangeItem]:
        merged_quantities: dict[int, int] = {}
        expected_versions: dict[int, int | None] = {}

        for item in items:
            if not _is_strict_int(item.product_id) or item.product_id <= 0:
                raise InventoryValidationError(
                    "Mã sản phẩm (product_id) phải là số nguyên dương."
                )
            if (
                item.quantity is None
                or not _is_strict_int(item.quantity)
                or item.quantity <= 0
            ):
                raise InventoryValidationError(
                    "Số lượng biến động (quantity) phải là số nguyên dương (> 0)."
                )
            if item.counted_quantity is not None:
                raise InventoryValidationError(
                    "Không truyền counted_quantity cho nghiệp vụ "
                    "INCREASE/DECREASE/RETURN."
                )
            if item.expected_stock_version is not None and (
                not _is_strict_int(item.expected_stock_version)
                or item.expected_stock_version < 0
            ):
                raise InventoryValidationError(
                    "expected_stock_version phải là số nguyên >= 0."
                )

            pid = item.product_id
            if (
                pid in expected_versions
                and item.expected_stock_version is not None
                and expected_versions[pid] is not None
                and expected_versions[pid] != item.expected_stock_version
            ):
                raise InventoryValidationError(
                    "Các dòng trùng product_id không được có "
                    "expected_stock_version mâu thuẫn."
                )
            if item.expected_stock_version is not None:
                expected_versions[pid] = item.expected_stock_version
            else:
                expected_versions.setdefault(pid, None)

            merged_quantities[pid] = merged_quantities.get(pid, 0) + item.quantity
            _ensure_merged_quantity_in_int_range(pid, merged_quantities[pid])

        return [
            StockChangeItem(
                product_id=pid,
                quantity=merged_quantities[pid],
                expected_stock_version=expected_versions[pid],
            )
            for pid in sorted(merged_quantities.keys())
        ]

    @staticmethod
    def _resolve_movement_kind(
        movement_type: MovementType | MovementKind | str,
    ) -> tuple[MovementKind, MovementType]:
        if isinstance(movement_type, MovementKind):
            return movement_type, _MOVEMENT_KIND_TO_TYPE[movement_type]
        if isinstance(movement_type, MovementType):
            return _MOVEMENT_TYPE_TO_KIND[movement_type], movement_type
        if isinstance(movement_type, str):
            upper = movement_type.strip().upper()
            if upper in MovementType.__members__:
                mt = MovementType(upper)
                return _MOVEMENT_TYPE_TO_KIND[mt], mt
            if upper in MovementKind.__members__:
                mk = MovementKind(upper)
                return mk, _MOVEMENT_KIND_TO_TYPE[mk]
        raise InventoryValidationError(
            f"Loại biến động tồn kho không hợp lệ: {movement_type!r}."
        )

    @staticmethod
    def _resolve_reference_type(
        kind: MovementKind,
        reference_type: ReferenceType | str | None,
    ) -> ReferenceType:
        expected = _KIND_TO_DEFAULT_REFERENCE_TYPE[kind]
        if reference_type is None:
            return expected
        if isinstance(reference_type, ReferenceType):
            resolved = reference_type
        elif isinstance(reference_type, str):
            upper = reference_type.strip().upper()
            if upper not in ReferenceType.__members__:
                raise InventoryValidationError(
                    f"Loại tham chiếu (reference_type) không hợp lệ: "
                    f"{reference_type!r}."
                )
            resolved = ReferenceType(upper)
        else:
            raise InventoryValidationError("reference_type không hợp lệ.")

        if resolved != expected:
            raise InventoryValidationError(
                f"Loại biến động {kind.value} yêu cầu reference_type={expected.value}, "
                f"nhận {resolved.value}."
            )
        return resolved

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


__all__ = [
    "InventoryQueryService",
    "InventoryService",
    "merge_and_sort_stock_lines",
    "normalize_lock_order",
]
