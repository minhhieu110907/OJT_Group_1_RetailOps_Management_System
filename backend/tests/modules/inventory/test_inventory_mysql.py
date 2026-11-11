"""MySQL 8.4 integration and concurrency tests for InventoryService (T04A653)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from sqlalchemy import URL, create_engine, delete, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.inventory import (
    CountAdjustment,
    DuplicateMovementError,
    InsufficientStockError,
    Inventory,
    InventoryAdjustment,
    InventoryService,
    MovementKind,
    MovementType,
    Product,
    ProductStatus,
    ReferenceType,
    StaleStockVersionError,
    StockChangeItem,
    StockLine,
    StockMovement,
)
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_SKU_PREFIX = "T04A653-SKU-"
TEST_CAT_PREFIX = "T04A653_CAT_"
TEST_EMAIL_PREFIX = "t04a653_inv_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_inventory_test_rows(migrated_integration_engine: Engine) -> None:
    """Clean up all test rows created under T04A653 prefixes after each test."""
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{TEST_SKU_PREFIX}%"))
            )
        )
        if product_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
            session.execute(
                delete(InventoryAdjustment).where(
                    InventoryAdjustment.product_id.in_(product_ids)
                )
            )
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        session.execute(
            delete(Category).where(Category.name.like(f"{TEST_CAT_PREFIX}%"))
        )
        session.execute(
            delete(User).where(User.email_normalized.like(f"{TEST_EMAIL_PREFIX}%"))
        )


def _seed_actor_and_products(
    session: Session,
    suffix: str,
    *,
    quantities: list[int],
) -> tuple[int, list[int]]:
    """Seed an active test actor, category, and products with initial stock balances."""
    now = datetime(2026, 11, 11, 8, 0, 0)
    actor = User(
        email_normalized=f"{TEST_EMAIL_PREFIX}{suffix}@example.com",
        password_hash="$2b$04$test.actor.only.hash.value.for.inventory",
        role="STAFF",
        status="ACTIVE",
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    category = Category(
        name=f"{TEST_CAT_PREFIX}{suffix}",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add_all((actor, category))
    session.flush()

    product_ids: list[int] = []
    for idx, qty in enumerate(quantities, start=1):
        product = Product(
            category_id=category.id,
            sku=f"{TEST_SKU_PREFIX}{suffix.upper()}-{idx}",
            name=f"T04A653 Product {suffix} #{idx}",
            status=ProductStatus.ACTIVE.value,
            sale_price_vnd=50_000 * idx,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
        inv = Inventory(
            product_id=product.id,
            quantity=qty,
            stock_version=1 if qty > 0 else 0,
            first_stocked_at=now if qty > 0 else None,
            updated_at=now,
        )
        session.add(inv)
        product_ids.append(product.id)

    session.flush()
    return actor.id, product_ids


def test_schema_and_non_negative_stock_guard_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Acceptance #1: Stock never goes negative; over-deduction leaves DB untouched."""
    inspector = inspect(migrated_integration_engine)
    assert "inventory_adjustments" in inspector.get_table_names()
    assert "stock_movements" in inspector.get_table_names()

    service = InventoryService()
    with Session(migrated_integration_engine) as setup_session:
        actor_id, [product_id] = _seed_actor_and_products(
            setup_session, "nonneg", quantities=[5]
        )
        setup_session.commit()

    # 1. Attempting to deduct 6 when available is 5 raises InsufficientStockError
    with Session(migrated_integration_engine) as tx_session:
        with pytest.raises(InsufficientStockError) as exc_info:
            service.decrease(
                tx_session,
                items=[StockChangeItem(product_id=product_id, quantity=6)],
                reference_id=1001,
                actor_id=actor_id,
            )
        assert exc_info.value.details["available_quantity"] == 5
        assert exc_info.value.details["requested_quantity"] == 6
        tx_session.rollback()

    # Verify inventory balance, stock_version, and movements are completely unchanged
    with Session(migrated_integration_engine) as verify_session:
        inv = verify_session.get(Inventory, product_id)
        assert inv is not None
        assert inv.quantity == 5
        assert inv.stock_version == 1
        movement_count = verify_session.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.product_id == product_id
            )
        )
        assert movement_count == 0

        # Direct SQL/ORM attempt to set negative stock violates MySQL CHECK constraint
        inv.quantity = -1
        with pytest.raises(IntegrityError):
            verify_session.commit()
        verify_session.rollback()


def test_atomic_rollback_on_mid_transaction_or_caller_failure(
    migrated_integration_engine: Engine,
) -> None:
    """Acceptance #2: Error mid-batch or after update rolls back stock & movements."""
    service = InventoryService()
    with Session(migrated_integration_engine) as setup_session:
        actor_id, [p1_id, p2_id] = _seed_actor_and_products(
            setup_session, "rollback", quantities=[10, 2]
        )
        setup_session.commit()

    # Case A: Multi-item decrease where item 1 has enough stock (10 >= 4)
    # but item 2 lacks stock (2 < 5) -> neither item is persisted after rollback.
    with Session(migrated_integration_engine) as tx_session:
        with pytest.raises(InsufficientStockError):
            service.decrease(
                tx_session,
                items=[
                    StockChangeItem(product_id=p1_id, quantity=4),
                    StockChangeItem(product_id=p2_id, quantity=5),
                ],
                reference_id=2001,
                actor_id=actor_id,
            )
        tx_session.rollback()

    # Case B: Stock change succeeds and flushes, then caller encounters a downstream
    # business error before commit and rolls back -> both stock and movement roll back.
    with Session(migrated_integration_engine) as caller_session:
        res = service.decrease(
            caller_session,
            items=[StockChangeItem(product_id=p1_id, quantity=4)],
            reference_id=2002,
            actor_id=actor_id,
        )
        assert res[0].quantity_after == 6
        # Simulate caller error after InventoryService flush
        caller_session.rollback()

    with Session(migrated_integration_engine) as verify_session:
        inv1 = verify_session.get(Inventory, p1_id)
        inv2 = verify_session.get(Inventory, p2_id)
        assert inv1 is not None and inv1.quantity == 10 and inv1.stock_version == 1
        assert inv2 is not None and inv2.quantity == 2 and inv2.stock_version == 1
        movements = list(
            verify_session.scalars(
                select(StockMovement).where(
                    StockMovement.product_id.in_([p1_id, p2_id])
                )
            )
        )
        assert movements == []


def test_idempotent_retry_and_unique_movement_per_reference(
    migrated_integration_engine: Engine,
) -> None:
    """Acceptance #3: Repeated call with same reference creates only 1 movement."""
    service = InventoryService()
    with Session(migrated_integration_engine) as setup_session:
        actor_id, [product_id] = _seed_actor_and_products(
            setup_session, "idem", quantities=[10]
        )
        setup_session.commit()

    with Session(migrated_integration_engine) as session1:
        first = service.decrease(
            session1,
            items=[StockChangeItem(product_id=product_id, quantity=3)],
            reference_id=3001,
            actor_id=actor_id,
        )
        session1.commit()

    # Retry with the exact same reference_id=3001 and quantity=3
    with Session(migrated_integration_engine) as session2:
        second = service.decrease(
            session2,
            items=[StockChangeItem(product_id=product_id, quantity=3)],
            reference_id=3001,
            actor_id=actor_id,
        )
        session2.commit()

    assert first[0].movement_id == second[0].movement_id
    assert first[0].movement_created is True
    assert second[0].movement_created is False
    assert second[0].quantity_before == 10
    assert second[0].quantity_after == 7

    # CF-02 strict mode (idempotent_replay=False) rejects duplicate order cancel
    with Session(migrated_integration_engine) as cancel_session:
        locks = service.lock_for_mutation(cancel_session, product_ids=[product_id])
        service.restore_for_cancel(
            cancel_session,
            locks=locks,
            order_id=3001,
            actor_id=actor_id,
            lines=[StockLine(product_id=product_id, quantity=3)],
        )
        cancel_session.commit()

    with Session(migrated_integration_engine) as dup_cancel_session:
        locks = service.lock_for_mutation(dup_cancel_session, product_ids=[product_id])
        with pytest.raises(DuplicateMovementError):
            service.restore_for_cancel(
                dup_cancel_session,
                locks=locks,
                order_id=3001,
                actor_id=actor_id,
                lines=[StockLine(product_id=product_id, quantity=3)],
            )
        dup_cancel_session.rollback()

    with Session(migrated_integration_engine) as verify_session:
        inv = verify_session.get(Inventory, product_id)
        assert inv is not None
        assert inv.quantity == 10
        assert inv.stock_version == 3
        movements = list(
            verify_session.scalars(
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.id.asc())
            )
        )
        assert len(movements) == 2
        assert [m.kind for m in movements] == [
            MovementKind.SALE.value,
            MovementKind.ORDER_CANCEL.value,
        ]


def test_concurrent_decreases_on_single_product_prevent_oversell(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Acceptance #4: Concurrent deductions on 1 product never oversell."""
    with Session(migrated_integration_engine) as setup_session:
        actor_id, [product_id] = _seed_actor_and_products(
            setup_session, "conc_single", quantities=[5]
        )
        setup_session.commit()

    worker_count = 8
    barrier = threading.Barrier(worker_count)
    concurrent_engine = create_engine(
        integration_database_url,
        pool_pre_ping=True,
        pool_size=worker_count,
        max_overflow=2,
        connect_args={"connect_timeout": 5},
    )

    def worker_checkout(idx: int) -> str:
        svc = InventoryService()
        with Session(concurrent_engine) as worker_session:
            barrier.wait(timeout=10)
            try:
                svc.decrease(
                    worker_session,
                    items=[StockChangeItem(product_id=product_id, quantity=1)],
                    reference_id=4000 + idx,
                    actor_id=actor_id,
                    idempotent_replay=False,
                )
                worker_session.commit()
                return "SUCCESS"
            except InsufficientStockError:
                worker_session.rollback()
                return "INSUFFICIENT"

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            outcomes = list(pool.map(worker_checkout, range(1, worker_count + 1)))
    finally:
        concurrent_engine.dispose()

    assert outcomes.count("SUCCESS") == 5
    assert outcomes.count("INSUFFICIENT") == 3

    with Session(migrated_integration_engine) as verify_session:
        inv = verify_session.get(Inventory, product_id)
        assert inv is not None
        assert inv.quantity == 0
        assert inv.stock_version == 6  # initial version 1 + 5 successful deductions
        movements = list(
            verify_session.scalars(
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.stock_version_after.asc())
            )
        )
        assert len(movements) == 5
        assert [m.quantity_after for m in movements] == [4, 3, 2, 1, 0]
        assert [m.stock_version_after for m in movements] == [2, 3, 4, 5, 6]


def test_concurrent_multi_item_reversed_input_order_does_not_deadlock(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Acceptance #5: Reversed item order in parallel transactions avoids deadlock."""
    with Session(migrated_integration_engine) as setup_session:
        actor_id, [p1, p2, p3] = _seed_actor_and_products(
            setup_session, "conc_order", quantities=[20, 20, 20]
        )
        setup_session.commit()

    worker_count = 6
    barrier = threading.Barrier(worker_count)
    concurrent_engine = create_engine(
        integration_database_url,
        pool_pre_ping=True,
        pool_size=worker_count,
        max_overflow=2,
        connect_args={"connect_timeout": 5},
    )

    # Even workers pass [p3, p1, p2], odd workers pass [p2, p3, p1]
    def worker_multi_item(idx: int) -> bool:
        svc = InventoryService()
        input_order = [p3, p1, p2] if idx % 2 == 0 else [p2, p3, p1]
        items = [StockChangeItem(product_id=pid, quantity=2) for pid in input_order]
        with Session(concurrent_engine) as worker_session:
            barrier.wait(timeout=10)
            svc.decrease(
                worker_session,
                items=items,
                reference_id=5000 + idx,
                actor_id=actor_id,
                idempotent_replay=False,
            )
            worker_session.commit()
            return True

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            results = list(pool.map(worker_multi_item, range(1, worker_count + 1)))
    finally:
        concurrent_engine.dispose()

    assert results == [True] * worker_count

    with Session(migrated_integration_engine) as verify_session:
        for pid in (p1, p2, p3):
            inv = verify_session.get(Inventory, pid)
            assert inv is not None
            assert inv.quantity == 20 - (worker_count * 2) == 8
            assert inv.stock_version == 1 + worker_count == 7


def test_all_four_operations_and_before_after_movement_ledger_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Acceptance #6: Full lifecycle INCREASE -> DECREASE -> RETURN -> ADJUST."""
    t0 = datetime(2026, 11, 11, 10, 0, 0)
    timestamps = [t0 + timedelta(minutes=i) for i in range(10)]
    service = InventoryService(clock=lambda: timestamps.pop(0))

    with Session(migrated_integration_engine) as setup_session:
        actor_id, [product_id] = _seed_actor_and_products(
            setup_session, "lifecycle", quantities=[0]
        )
        setup_session.commit()

    with Session(migrated_integration_engine) as session:
        # 1. INCREASE (0 -> 15): sets first_stocked_at = t0, stock_version 0 -> 1
        inc = service.apply_stock_change(
            session,
            items=[StockChangeItem(product_id=product_id, quantity=15)],
            movement_type=MovementType.INCREASE,
            reference_type=ReferenceType.RECEIPT,
            reference_id=6001,
            actor_id=actor_id,
        )
        assert inc[0].quantity_before == 0
        assert inc[0].quantity_after == 15
        assert inc[0].delta == 15
        assert inc[0].stock_version_before == 0
        assert inc[0].stock_version_after == 1
        session.commit()

    with Session(migrated_integration_engine) as session:
        inv_after_inc = session.get(Inventory, product_id)
        assert inv_after_inc is not None
        assert inv_after_inc.first_stocked_at == t0

        # 2. DECREASE (15 -> 0): depletes stock to 0, first_stocked_at MUST remain t0
        dec = service.apply_stock_change(
            session,
            items=[StockChangeItem(product_id=product_id, quantity=15)],
            movement_type=MovementType.DECREASE,
            reference_type=ReferenceType.ORDER,
            reference_id=6002,
            actor_id=actor_id,
        )
        assert dec[0].quantity_before == 15
        assert dec[0].quantity_after == 0
        assert dec[0].delta == -15
        assert dec[0].stock_version_after == 2

        # 3. RETURN (0 -> 15): restores cancelled order, first_stocked_at still t0
        ret = service.apply_stock_change(
            session,
            items=[StockChangeItem(product_id=product_id, quantity=15)],
            movement_type=MovementType.RETURN,
            reference_type=ReferenceType.ORDER,
            reference_id=6002,
            actor_id=actor_id,
        )
        assert ret[0].quantity_before == 0
        assert ret[0].quantity_after == 15
        assert ret[0].delta == 15
        assert ret[0].stock_version_after == 3

        # 4. ADJUST (15 -> 12): physical count finds 12 units
        adj = service.apply_stock_change(
            session,
            items=[
                StockChangeItem(
                    product_id=product_id,
                    counted_quantity=12,
                    expected_stock_version=3,
                )
            ],
            movement_type=MovementType.ADJUST,
            reference_type=ReferenceType.ADJUSTMENT,
            actor_id=actor_id,
            note="Kiểm kê định kỳ phát hiện thiếu 3 sản phẩm",
        )
        assert adj[0].quantity_before == 15
        assert adj[0].quantity_after == 12
        assert adj[0].delta == -3
        assert adj[0].stock_version_after == 4
        assert adj[0].movement_created is True
        assert adj[0].audit_id is not None

        # 5. ADJUST no-op (12 -> 12): creates audit row, NO movement, version stays 4
        locks = service.lock_for_mutation(session, product_ids=[product_id])
        noop_adj = service.adjust_to_count(
            session,
            locks=locks,
            actor_id=actor_id,
            adjustment=CountAdjustment(
                product_id=product_id,
                counted_quantity=12,
                expected_stock_version=4,
                reason="Kiểm kê lại lần 2 khớp số lượng 12",
            ),
        )
        assert noop_adj.movement_created is False
        assert noop_adj.stock.quantity == 12
        assert noop_adj.stock.stock_version == 4

        # 6. Stale version in ADJUST raises 409 StaleStockVersionError
        with pytest.raises(StaleStockVersionError):
            service.adjust_to_count(
                session,
                locks=locks,
                actor_id=actor_id,
                adjustment=CountAdjustment(
                    product_id=product_id,
                    counted_quantity=12,
                    expected_stock_version=3,
                    reason="Version cũ phải bị từ chối",
                ),
            )
        session.commit()

    with Session(migrated_integration_engine) as verify_session:
        final_inv = verify_session.get(Inventory, product_id)
        assert final_inv is not None
        assert final_inv.quantity == 12
        assert final_inv.stock_version == 4
        assert final_inv.first_stocked_at == t0

        movements = list(
            verify_session.scalars(
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.stock_version_after.asc())
            )
        )
        assert len(movements) == 4
        assert [
            (
                m.kind,
                m.quantity_before,
                m.quantity_after,
                m.delta,
                m.stock_version_after,
            )
            for m in movements
        ] == [
            (MovementKind.PURCHASE_CONFIRM.value, 0, 15, 15, 1),
            (MovementKind.SALE.value, 15, 0, -15, 2),
            (MovementKind.ORDER_CANCEL.value, 0, 15, 15, 3),
            (MovementKind.ADJUSTMENT.value, 15, 12, -3, 4),
        ]

        adjustments = list(
            verify_session.scalars(
                select(InventoryAdjustment)
                .where(InventoryAdjustment.product_id == product_id)
                .order_by(InventoryAdjustment.id.asc())
            )
        )
        assert len(adjustments) == 2
        assert [
            (a.quantity_before, a.counted_quantity, a.version_before)
            for a in adjustments
        ] == [
            (15, 12, 3),
            (12, 12, 4),
        ]
