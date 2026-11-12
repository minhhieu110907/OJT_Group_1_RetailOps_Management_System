"""Unit tests for InventoryService validation, lock ordering, and tx invariants."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.inventory import (
    CountAdjustment,
    DuplicateMovementError,
    InactiveProductStockError,
    InsufficientStockError,
    InventoryAdjustment,
    InventoryMovementRepository,
    InventoryService,
    InventoryValidationError,
    LockedStock,
    MovementKind,
    ProductStatus,
    StaleStockVersionError,
    StockChangeItem,
    StockConflictError,
    StockItemNotFoundError,
    StockLine,
    StockLockSet,
    StockMovement,
    classify_movement_integrity_error,
    get_session_transaction_identity,
    merge_and_sort_stock_lines,
    normalize_lock_order,
)

FORBIDDEN_SESSION_METHODS = {
    "commit",
    "rollback",
    "close",
    "begin",
    "begin_nested",
}


class GuardedUnitSession:
    """Fake session that fails if any transaction boundary method is called."""

    def __init__(self, tx_token: object | None = None) -> None:
        self._tx_token = object() if tx_token is None else tx_token

    def get_transaction(self) -> object | None:
        return self._tx_token

    def rotate_transaction(self) -> None:
        """Simulate a new transaction after an external commit/rollback."""
        self._tx_token = object()

    def end_transaction(self) -> None:
        """Simulate a session with no active transaction."""
        self._tx_token = None

    def commit(self) -> None:  # pragma: no cover - defensive guard
        raise AssertionError("InventoryService must never call session.commit()")

    def rollback(self) -> None:  # pragma: no cover - defensive guard
        raise AssertionError("InventoryService must never call session.rollback()")

    def close(self) -> None:  # pragma: no cover - defensive guard
        raise AssertionError("InventoryService must never call session.close()")

    def begin(self) -> None:  # pragma: no cover - defensive guard
        raise AssertionError("InventoryService must never call session.begin()")

    def begin_nested(self) -> None:  # pragma: no cover - defensive guard
        raise AssertionError("InventoryService must never call session.begin_nested()")


@dataclass
class _InMemoryProductState:
    product_id: int
    sku: str
    name: str
    status: str
    sale_price_vnd: int
    quantity: int
    stock_version: int
    first_stocked_at: datetime | None = None


class FakeInventoryMovementRepository(InventoryMovementRepository):
    """In-memory repository recording exact lock acquisition order for unit tests."""

    def __init__(self, initial_states: Sequence[_InMemoryProductState]) -> None:
        self.states: dict[int, _InMemoryProductState] = {
            s.product_id: s for s in initial_states
        }
        self.lock_history: list[list[int]] = []
        self.movements: list[StockMovement] = []
        self.adjustments: list[InventoryAdjustment] = []
        self._next_movement_id = 1
        self._next_adjustment_id = 1

    def lock_products_and_inventory(  # type: ignore[override]
        self,
        session: object,
        sorted_product_ids: Sequence[int],
    ) -> StockLockSet:
        ordered = list(sorted_product_ids)
        self.lock_history.append(ordered)
        missing = [pid for pid in ordered if pid not in self.states]
        if missing:
            raise StockItemNotFoundError(product_ids=missing)
        rows = {
            pid: LockedStock(
                product_id=pid,
                sku=self.states[pid].sku,
                name=self.states[pid].name,
                status=self.states[pid].status,
                sale_price_vnd=self.states[pid].sale_price_vnd,
                quantity=self.states[pid].quantity,
                stock_version=self.states[pid].stock_version,
            )
            for pid in ordered
        }
        return StockLockSet(
            rows=rows,
            session_identity=id(session),
            transaction_identity=get_session_transaction_identity(session),
        )

    def guarded_update_balance(  # type: ignore[override]
        self,
        session: object,
        *,
        product_id: int,
        expected_version: int,
        new_quantity: int,
        now: datetime,
    ) -> bool:
        state = self.states.get(product_id)
        if state is None or state.stock_version != expected_version or new_quantity < 0:
            return False
        state.quantity = new_quantity
        state.stock_version += 1
        if new_quantity > 0 and state.first_stocked_at is None:
            state.first_stocked_at = now
        return True

    def find_existing_movement(  # type: ignore[override]
        self,
        session: object,
        *,
        kind: MovementKind,
        product_id: int,
        receipt_id: int | None = None,
        order_id: int | None = None,
        adjustment_id: int | None = None,
    ) -> StockMovement | None:
        for mov in self.movements:
            if mov.product_id != product_id or mov.kind != kind.value:
                continue
            if kind == MovementKind.PURCHASE_CONFIRM and mov.receipt_id == receipt_id:
                return mov
            if (
                kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}
                and mov.order_id == order_id
            ):
                return mov
            if kind == MovementKind.ADJUSTMENT and mov.adjustment_id == adjustment_id:
                return mov
        return None

    def find_movements_by_reference(  # type: ignore[override]
        self,
        session: object,
        *,
        kind: MovementKind,
        reference_id: int,
    ) -> list[StockMovement]:
        matched: list[StockMovement] = []
        for mov in self.movements:
            if mov.kind != kind.value:
                continue
            is_match = (
                (
                    kind == MovementKind.PURCHASE_CONFIRM
                    and mov.receipt_id == reference_id
                )
                or (
                    kind in {MovementKind.SALE, MovementKind.ORDER_CANCEL}
                    and mov.order_id == reference_id
                )
                or (
                    kind == MovementKind.ADJUSTMENT
                    and mov.adjustment_id == reference_id
                )
            )
            if is_match:
                matched.append(mov)
        return sorted(matched, key=lambda m: (m.product_id, m.id or 0))

    def add_adjustment(  # type: ignore[override]
        self,
        session: object,
        adjustment: InventoryAdjustment,
    ) -> InventoryAdjustment:
        adjustment.id = self._next_adjustment_id
        self._next_adjustment_id += 1
        self.adjustments.append(adjustment)
        return adjustment

    def add_movement(  # type: ignore[override]
        self,
        session: object,
        movement: StockMovement,
    ) -> StockMovement:
        movement.id = self._next_movement_id
        self._next_movement_id += 1
        self.movements.append(movement)
        return movement


def test_normalize_lock_order_sorts_and_deduplicates_ascending() -> None:
    assert normalize_lock_order([42, 7, 19, 7, 1, 42]) == [1, 7, 19, 42]

    for invalid_input in ([], [0], [-5], [True], ["1"]):  # type: ignore[list-item]
        with pytest.raises(InventoryValidationError):
            normalize_lock_order(invalid_input)  # type: ignore[arg-type]


def test_merge_and_sort_stock_lines_combines_duplicates_and_sorts() -> None:
    lines = [
        StockLine(product_id=30, quantity=2),
        StockLine(product_id=10, quantity=3),
        StockLine(product_id=20, quantity=1),
        StockLine(product_id=10, quantity=4),
    ]
    merged = merge_and_sort_stock_lines(lines)
    assert merged == [
        StockLine(product_id=10, quantity=7),
        StockLine(product_id=20, quantity=1),
        StockLine(product_id=30, quantity=2),
    ]

    for bad_lines in (
        [],
        [StockLine(product_id=0, quantity=1)],
        [StockLine(product_id=1, quantity=0)],
        [StockLine(product_id=1, quantity=-3)],
        [StockLine(product_id=True, quantity=1)],  # type: ignore[arg-type]
        [StockLine(product_id=1, quantity=True)],  # type: ignore[arg-type]
    ):
        with pytest.raises(InventoryValidationError):
            merge_and_sort_stock_lines(bad_lines)


def test_unified_apply_stock_change_merges_sorts_and_handles_all_four_types() -> None:
    fixed_now = datetime(2026, 11, 11, 9, 0, 0)
    repo = FakeInventoryMovementRepository(
        [
            _InMemoryProductState(
                product_id=10,
                sku="SKU-010",
                name="Product 10",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=50_000,
                quantity=0,
                stock_version=0,
            ),
            _InMemoryProductState(
                product_id=20,
                sku="SKU-020",
                name="Product 20",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=80_000,
                quantity=5,
                stock_version=2,
            ),
            _InMemoryProductState(
                product_id=30,
                sku="SKU-030",
                name="Product 30",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=90_000,
                quantity=12,
                stock_version=1,
            ),
        ]
    )
    service = InventoryService(repository=repo, clock=lambda: fixed_now)
    session = GuardedUnitSession()

    # 1. INCREASE with reversed + duplicate product order -> locks [10, 20] ascending
    inc_results = service.increase(
        session,  # type: ignore[arg-type]
        items=[
            StockChangeItem(product_id=20, quantity=3),
            StockChangeItem(product_id=10, quantity=4),
            StockChangeItem(product_id=10, quantity=6),
        ],
        reference_id=101,
        actor_id=1,
    )
    assert repo.lock_history[-1] == [10, 20]
    assert [
        (r.product_id, r.quantity_before, r.quantity_after, r.delta)
        for r in inc_results
    ] == [
        (10, 0, 10, 10),
        (20, 5, 8, 3),
    ]
    assert [r.stock_version_after for r in inc_results] == [1, 3]
    assert repo.states[10].first_stocked_at == fixed_now

    # 2a. Default (idempotent_replay=False): HTTP replay belongs to the shared
    # IdempotencyExecutor, so a repeated reference is rejected without mutation.
    with pytest.raises(DuplicateMovementError):
        service.increase(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(product_id=10, quantity=10),
                StockChangeItem(product_id=20, quantity=3),
            ],
            reference_id=101,
            actor_id=1,
        )
    assert repo.states[10].quantity == 10
    assert repo.states[10].stock_version == 1
    assert len(repo.movements) == 2

    # 2b. Explicit opt-in replay with identical reference + quantities
    retry_results = service.increase(
        session,  # type: ignore[arg-type]
        items=[
            StockChangeItem(
                product_id=10,
                quantity=10,
                expected_stock_version=0,
            ),
            StockChangeItem(
                product_id=20,
                quantity=3,
                expected_stock_version=2,
            ),
        ],
        reference_id=101,
        actor_id=1,
        idempotent_replay=True,
    )
    assert [r.movement_created for r in retry_results] == [False, False]
    assert repo.states[10].quantity == 10
    assert repo.states[10].stock_version == 1
    assert len(repo.movements) == 2

    # Partial batch replay (missing product 20 from reference_id=101) -> rejected
    with pytest.raises(DuplicateMovementError):
        service.increase(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=10, quantity=10)],
            reference_id=101,
            actor_id=1,
            idempotent_replay=True,
        )

    # Mixed batch replay (existing product 10 + unrecorded product 30 on ref 101)
    # MUST be rejected before mutating product 30!
    with pytest.raises(DuplicateMovementError):
        service.increase(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(product_id=10, quantity=10),
                StockChangeItem(product_id=20, quantity=3),
                StockChangeItem(product_id=30, quantity=5),
            ],
            reference_id=101,
            actor_id=1,
            idempotent_replay=True,
        )
    assert repo.states[30].quantity == 12
    assert repo.states[30].stock_version == 1

    # Conflicting quantity on same reference_id must raise DuplicateMovementError
    with pytest.raises(DuplicateMovementError):
        service.increase(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(product_id=10, quantity=99),
                StockChangeItem(product_id=20, quantity=3),
            ],
            reference_id=101,
            actor_id=1,
            idempotent_replay=True,
        )

    # 3. DECREASE (Checkout)
    dec_results = service.decrease(
        session,  # type: ignore[arg-type]
        items=[StockChangeItem(product_id=10, quantity=4)],
        reference_id=501,
        actor_id=2,
    )
    assert dec_results[0].quantity_before == 10
    assert dec_results[0].quantity_after == 6
    assert dec_results[0].delta == -4
    assert dec_results[0].stock_version_after == 2

    # 4. RETURN (Order Cancel)
    ret_results = service.return_stock(
        session,  # type: ignore[arg-type]
        items=[StockChangeItem(product_id=10, quantity=4)],
        reference_id=501,
        actor_id=2,
    )
    assert ret_results[0].quantity_before == 6
    assert ret_results[0].quantity_after == 10
    assert ret_results[0].delta == 4
    assert ret_results[0].stock_version_after == 3

    # 5. ADJUST (physical count): non-zero delta & zero delta (no-op)
    adj_changed = service.adjust(
        session,  # type: ignore[arg-type]
        items=[
            StockChangeItem(
                product_id=10,
                counted_quantity=7,
                expected_stock_version=3,
            )
        ],
        actor_id=1,
        note="Kiểm kê cuối ca phát hiện hao hụt 3 đơn vị",
    )
    assert adj_changed[0].movement_created is True
    assert adj_changed[0].quantity_before == 10
    assert adj_changed[0].quantity_after == 7
    assert adj_changed[0].delta == -3
    assert adj_changed[0].stock_version_after == 4
    assert adj_changed[0].audit_id is not None

    # No-op adjustment (counted_quantity == current quantity): creates audit ONLY
    movements_before_noop = len(repo.movements)
    adj_noop = service.adjust(
        session,  # type: ignore[arg-type]
        items=[
            StockChangeItem(
                product_id=10,
                counted_quantity=7,
                expected_stock_version=4,
            )
        ],
        actor_id=1,
        note="Kiểm kê khớp tồn kho thực tế",
    )
    assert adj_noop[0].movement_created is False
    assert adj_noop[0].movement_id is None
    assert adj_noop[0].audit_id is not None
    assert adj_noop[0].stock_version_after == 4
    assert len(repo.movements) == movements_before_noop
    assert len(repo.adjustments) == 2

    # Stale expected_stock_version MUST raise StaleStockVersionError (409)
    with pytest.raises(StaleStockVersionError):
        service.adjust(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(
                    product_id=10,
                    counted_quantity=7,
                    expected_stock_version=3,
                )
            ],
            actor_id=1,
            note="Stale version",
        )


def test_negative_stock_inactive_product_and_lock_lifecycle_guards() -> None:
    repo = FakeInventoryMovementRepository(
        [
            _InMemoryProductState(
                product_id=1,
                sku="SKU-ACTIVE",
                name="Active Product",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=20_000,
                quantity=5,
                stock_version=1,
            ),
            _InMemoryProductState(
                product_id=2,
                sku="SKU-INACTIVE",
                name="Inactive Product",
                status=ProductStatus.INACTIVE.value,
                sale_price_vnd=20_000,
                quantity=5,
                stock_version=1,
            ),
        ]
    )
    service = InventoryService(repository=repo)
    session = GuardedUnitSession()

    # Insufficient stock raises 409 InsufficientStockError without modifying balance
    with pytest.raises(InsufficientStockError) as exc_info:
        service.decrease(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=1, quantity=6)],
            reference_id=900,
            actor_id=1,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "INSUFFICIENT_STOCK"
    assert repo.states[1].quantity == 5
    assert repo.states[1].stock_version == 1

    # INACTIVE product is rejected for receipt/checkout but allowed for adjustment
    with pytest.raises(InactiveProductStockError):
        service.increase(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=2, quantity=1)],
            reference_id=901,
            actor_id=1,
        )
    with pytest.raises(InactiveProductStockError):
        service.decrease(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=2, quantity=1)],
            reference_id=902,
            actor_id=1,
        )

    # Lock lifecycle check 1: passing StockLockSet uses it directly without re-locking
    locks = service.lock_for_mutation(session, product_ids=[2])  # type: ignore[arg-type]
    lock_calls_before = len(repo.lock_history)
    adj_inactive = service.adjust_to_count(
        session,  # type: ignore[arg-type]
        locks=locks,
        actor_id=1,
        adjustment=CountAdjustment(
            product_id=2,
            counted_quantity=4,
            expected_stock_version=1,
            reason="Kiểm kê hàng ngừng kinh doanh",
        ),
    )
    assert len(repo.lock_history) == lock_calls_before
    assert adj_inactive.stock.quantity == 4
    assert adj_inactive.stock.stock_version == 2
    assert locks.is_consumed is True

    # Lock lifecycle check 2: reusing an already-consumed StockLockSet is rejected
    with pytest.raises(StockConflictError):
        service.adjust_to_count(
            session,  # type: ignore[arg-type]
            locks=locks,
            actor_id=1,
            adjustment=CountAdjustment(
                product_id=2,
                counted_quantity=3,
                expected_stock_version=2,
                reason="Tái dùng lockset cũ",
            ),
        )

    # Lock lifecycle check 3: StockLockSet across transaction rotation is rejected
    tx_locks = service.lock_for_mutation(session, product_ids=[1])  # type: ignore[arg-type]
    session.rotate_transaction()
    with pytest.raises(StockConflictError):
        service.decrease_for_checkout(
            session,  # type: ignore[arg-type]
            locks=tx_locks,
            order_id=997,
            actor_id=1,
            lines=[StockLine(product_id=1, quantity=1)],
        )

    # Lock lifecycle check 4: Forged StockLockSet without session_identity is rejected
    forged_locks = StockLockSet(rows=tx_locks.rows)
    with pytest.raises(StockConflictError):
        service.decrease_for_checkout(
            session,  # type: ignore[arg-type]
            locks=forged_locks,
            order_id=998,
            actor_id=1,
            lines=[StockLine(product_id=1, quantity=1)],
        )

    # Lock lifecycle check 5: Cross-session StockLockSet reuse is rejected
    other_session = GuardedUnitSession()
    foreign_locks = service.lock_for_mutation(other_session, product_ids=[1])  # type: ignore[arg-type]
    with pytest.raises(StockConflictError):
        service.decrease_for_checkout(
            session,  # type: ignore[arg-type]
            locks=foreign_locks,
            order_id=999,
            actor_id=1,
            lines=[StockLine(product_id=1, quantity=1)],
        )


def test_quantity_overflow_beyond_sql_int_is_rejected_without_mutation() -> None:
    max_int = 2_147_483_647
    repo = FakeInventoryMovementRepository(
        [
            _InMemoryProductState(
                product_id=1,
                sku="SKU-NEAR-MAX",
                name="Near max product",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=1_000,
                quantity=max_int - 5,
                stock_version=4,
            ),
        ]
    )
    service = InventoryService(repository=repo)
    session = GuardedUnitSession()

    # (a) Merged duplicate lines exceeding SQL INT -> 422 before any lock
    lock_calls_before = len(repo.lock_history)
    with pytest.raises(InventoryValidationError) as merged_exc:
        service.increase(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(product_id=1, quantity=max_int),
                StockChangeItem(product_id=1, quantity=1),
            ],
            reference_id=7001,
            actor_id=1,
        )
    assert merged_exc.value.status_code == 422
    assert len(repo.lock_history) == lock_calls_before
    with pytest.raises(InventoryValidationError):
        merge_and_sort_stock_lines(
            [
                StockLine(product_id=1, quantity=max_int),
                StockLine(product_id=1, quantity=1),
            ]
        )

    # (b) Current balance + delta exceeding SQL INT -> 422, no row/movement written
    with pytest.raises(InventoryValidationError) as result_exc:
        service.increase_for_receipt(
            session,  # type: ignore[arg-type]
            locks=service.lock_for_mutation(session, product_ids=[1]),  # type: ignore[arg-type]
            receipt_id=7002,
            actor_id=1,
            lines=[StockLine(product_id=1, quantity=6)],
        )
    assert result_exc.value.details["max_quantity"] == max_int
    assert repo.states[1].quantity == max_int - 5
    assert repo.states[1].stock_version == 4
    assert repo.movements == []

    # Exactly reaching SQL INT max is allowed
    reached = service.increase(
        session,  # type: ignore[arg-type]
        items=[StockChangeItem(product_id=1, quantity=5)],
        reference_id=7003,
        actor_id=1,
    )
    assert reached[0].quantity_after == max_int

    # (c) Physical count above SQL INT -> 422
    with pytest.raises(InventoryValidationError):
        service.adjust(
            session,  # type: ignore[arg-type]
            items=[
                StockChangeItem(
                    product_id=1,
                    counted_quantity=max_int + 1,
                    expected_stock_version=5,
                )
            ],
            actor_id=1,
            note="Kiểm kê vượt giới hạn",
        )
    assert repo.states[1].quantity == max_int


def test_inventory_module_never_calls_transaction_boundary_methods() -> None:
    module_dir = Path(__file__).resolve().parents[3] / "app" / "modules" / "inventory"
    for py_file in module_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in FORBIDDEN_SESSION_METHODS, (
                    f"{py_file.name}:{node.lineno} calls forbidden transaction "
                    f"method '{node.func.attr}()'"
                )


def _make_mock_integrity_error(errno: int, msg: str) -> IntegrityError:
    class MockDBAPIError(Exception):
        pass

    orig = MockDBAPIError(errno, msg)
    return IntegrityError("INSERT INTO stock_movements ...", {}, orig)


def test_classify_movement_integrity_error() -> None:
    # 1. Duplicate movement constraints -> "duplicate_movement"
    dup_receipt = _make_mock_integrity_error(
        1062,
        "Duplicate entry '1-10' for key "
        "'stock_movements.uq_stock_movements_receipt_product'",
    )
    assert classify_movement_integrity_error(dup_receipt) == "duplicate_movement"

    dup_order = _make_mock_integrity_error(
        1062,
        "Duplicate entry '1-10-SALE' for key 'uq_stock_movements_order_product_kind'",
    )
    assert classify_movement_integrity_error(dup_order) == "duplicate_movement"

    dup_adj = _make_mock_integrity_error(
        1062,
        "Duplicate entry '1-10' for key "
        "'stock_movements.uq_stock_movements_adjustment_product'",
    )
    assert classify_movement_integrity_error(dup_adj) == "duplicate_movement"

    # 2. Version conflict constraint -> "version_conflict"
    version_conflict = _make_mock_integrity_error(
        1062,
        "Duplicate entry '1-2' for key "
        "'stock_movements.uq_stock_movements_product_version_after'",
    )
    assert classify_movement_integrity_error(version_conflict) == "version_conflict"

    # 3. Foreign key violation (1452) -> "other"
    fk_error = _make_mock_integrity_error(
        1452,
        "Cannot add or update a child row: a foreign key constraint fails "
        "(`stock_movements`, CONSTRAINT `fk_stock_movements_receipt_item`)",
    )
    assert classify_movement_integrity_error(fk_error) == "other"

    # 4. Check constraint violation (3819) -> "other"
    check_error = _make_mock_integrity_error(
        3819,
        "Check constraint 'ck_stock_movements_quantities_and_version' is violated.",
    )
    assert classify_movement_integrity_error(check_error) == "other"

    # 5. Non-MySQL or unknown error -> "other"
    unknown_error = IntegrityError(
        "INSERT ...", {}, Exception("database integrity failure")
    )
    assert classify_movement_integrity_error(unknown_error) == "other"


def test_service_integrity_error_propagation_and_classification() -> None:
    repo = FakeInventoryMovementRepository(
        [
            _InMemoryProductState(
                product_id=1,
                sku="SKU-ERR",
                name="Error Product",
                status=ProductStatus.ACTIVE.value,
                sale_price_vnd=10_000,
                quantity=10,
                stock_version=1,
            )
        ]
    )
    session = GuardedUnitSession()

    # Case A: Unknown / FK IntegrityError is NOT converted to DuplicateMovementError.
    # It must propagate up as IntegrityError without masking.
    class FailingRepo(FakeInventoryMovementRepository):
        def add_movement(self, session: object, movement: StockMovement) -> None:
            raise _make_mock_integrity_error(
                1452,
                "Cannot add or update a child row: a foreign key constraint fails",
            )

    failing_service = InventoryService(
        repository=FailingRepo(list(repo.states.values()))
    )
    with pytest.raises(IntegrityError) as exc_info:
        failing_service.increase(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=1, quantity=5)],
            reference_id=101,
            actor_id=1,
        )
    assert not isinstance(exc_info.value, DuplicateMovementError)

    # Case B: Version conflict on movement insert raises StockConflictError.
    class VersionConflictRepo(FakeInventoryMovementRepository):
        def add_movement(self, session: object, movement: StockMovement) -> None:
            raise _make_mock_integrity_error(
                1062,
                "Duplicate entry '1-2' for key "
                "'stock_movements.uq_stock_movements_product_version_after'",
            )

    vc_service = InventoryService(
        repository=VersionConflictRepo(list(repo.states.values()))
    )
    with pytest.raises(StockConflictError):
        vc_service.increase(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=1, quantity=5)],
            reference_id=102,
            actor_id=1,
        )

    # Case C: Duplicate document constraint raises DuplicateMovementError.
    class DuplicateMovementRepo(FakeInventoryMovementRepository):
        def add_movement(self, session: object, movement: StockMovement) -> None:
            raise _make_mock_integrity_error(
                1062,
                "Duplicate entry '103-1' for key "
                "'stock_movements.uq_stock_movements_receipt_product'",
            )

    dup_service = InventoryService(
        repository=DuplicateMovementRepo(list(repo.states.values()))
    )
    with pytest.raises(DuplicateMovementError):
        dup_service.increase(
            session,  # type: ignore[arg-type]
            items=[StockChangeItem(product_id=1, quantity=5)],
            reference_id=103,
            actor_id=1,
        )
