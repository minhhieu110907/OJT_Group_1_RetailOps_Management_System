"""MySQL integration and concurrency evidence for T04A73C checkout."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    IdempotencyKeyReusedError,
    InvalidStateError,
)
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import IdempotencyExecutor
from app.modules.inventory import (
    Inventory,
    InventoryService,
    Product,
    StockConflictError,
    StockMovement,
)
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService, OrderService
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_SKU_PREFIX = "T04A73C-SKU-"
TEST_CATEGORY_PREFIX = "T04A73C-CAT-"
TEST_EMAIL_PREFIX = "t04a73c-"
IDEMPOTENCY_SECRET = b"t04a73c-integration-secret-32-bytes"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_checkout_rows(migrated_integration_engine: Engine) -> None:
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        actor_ids = list(
            session.scalars(
                select(User.id).where(
                    User.email_normalized.like(f"{TEST_EMAIL_PREFIX}%")
                )
            )
        )
        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{TEST_SKU_PREFIX}%"))
            )
        )
        order_ids = (
            list(
                session.scalars(select(Order.id).where(Order.created_by.in_(actor_ids)))
            )
            if actor_ids
            else []
        )
        if order_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.order_id.in_(order_ids))
            )
            session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            session.execute(delete(Order).where(Order.id.in_(order_ids)))
        if actor_ids:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id.in_(actor_ids)
                )
            )
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))
        if actor_ids:
            session.execute(delete(User).where(User.id.in_(actor_ids)))
        session.execute(
            delete(Category).where(Category.name.like(f"{TEST_CATEGORY_PREFIX}%"))
        )


def seed_checkout(
    engine: Engine,
    suffix: str,
    *,
    quantity: int = 5,
    price: int = 50_000,
    status: str = "ACTIVE",
) -> tuple[int, int]:
    now = datetime(2026, 11, 13, 8, 0)
    with Session(engine) as session, session.begin():
        actor = User(
            email_normalized=f"{TEST_EMAIL_PREFIX}{suffix}@example.com",
            password_hash="$2b$04$checkout.integration.test.hash",
            role="STAFF",
            status="ACTIVE",
            admin_slot=None,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        category = Category(
            name=f"{TEST_CATEGORY_PREFIX}{suffix}",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add_all((actor, category))
        session.flush()
        product = Product(
            category_id=category.id,
            sku=f"{TEST_SKU_PREFIX}{suffix}",
            name=f"Checkout product {suffix}",
            status=status,
            sale_price_vnd=price,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
        session.add(
            Inventory(
                product_id=product.id,
                quantity=quantity,
                stock_version=1 if quantity else 0,
                first_stocked_at=now if quantity else None,
                updated_at=now,
            )
        )
        session.flush()
        return actor.id, product.id


def checkout_service(inventory: InventoryService | None = None) -> CheckoutService:
    return CheckoutService(
        inventory or InventoryService(),
        idempotency=IdempotencyExecutor(secret=IDEMPOTENCY_SECRET),
    )


def checkout_line(product_id: int, *, quantity: int = 1, price: int = 50_000):
    return CheckoutLine(
        product_id=product_id,
        quantity=quantity,
        viewed_unit_price_vnd=price,
    )


def test_migration_has_order_movement_fk(migrated_integration_engine: Engine) -> None:
    inspector = inspect(migrated_integration_engine)
    foreign_keys = inspector.get_foreign_keys("stock_movements")
    order_fk = next(
        fk for fk in foreign_keys if fk["name"] == "fk_stock_movements_order_item"
    )
    assert order_fk["constrained_columns"] == ["order_id", "product_id"]
    assert order_fk["referred_table"] == "order_items"
    assert order_fk["referred_columns"] == ["order_id", "product_id"]


def test_success_replay_and_different_payload_conflict(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, "replay", quantity=5
    )
    service = checkout_service()
    with Session(migrated_integration_engine) as session:
        first = service.checkout(
            session,
            actor_id=actor_id,
            idempotency_key="checkout-replay-key-0001",
            items=[
                checkout_line(product_id, quantity=1),
                checkout_line(product_id, quantity=1),
            ],
        )
        replay = service.checkout(
            session,
            actor_id=actor_id,
            idempotency_key="checkout-replay-key-0001",
            items=[
                checkout_line(product_id, quantity=1),
                checkout_line(product_id, quantity=1),
            ],
        )
        assert replay == first
        with pytest.raises(IdempotencyKeyReusedError):
            service.checkout(
                session,
                actor_id=actor_id,
                idempotency_key="checkout-replay-key-0001",
                items=[checkout_line(product_id, quantity=1)],
            )

    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 1
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 3
        assert (
            verify.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.order_id == first.id,
                    StockMovement.kind == "SALE",
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    ("viewed_price", "quantity", "expected_code"),
    [(49_000, 1, "PRICE_CHANGED"), (50_000, 6, "INSUFFICIENT_STOCK")],
)
def test_refusal_has_no_business_mutation(
    migrated_integration_engine: Engine,
    viewed_price: int,
    quantity: int,
    expected_code: str,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, expected_code.lower(), quantity=5
    )
    with Session(migrated_integration_engine) as session:
        with pytest.raises(ConflictError) as exc_info:
            checkout_service().checkout(
                session,
                actor_id=actor_id,
                idempotency_key=f"checkout-{expected_code.lower()}-0001",
                items=[
                    checkout_line(product_id, quantity=quantity, price=viewed_price)
                ],
            )
        assert exc_info.value.code == expected_code

    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 0
        )
        assert (
            verify.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id == product_id
                )
            )
            == 0
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 5


class FailingInventory(InventoryService):
    def decrease_for_checkout(self, *args: object, **kwargs: object):
        raise RuntimeError("failure after order flush")


def test_failure_after_order_flush_rolls_back_everything(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, "rollback", quantity=2
    )
    with (
        Session(migrated_integration_engine) as session,
        pytest.raises(RuntimeError, match="failure after order flush"),
    ):
        checkout_service(FailingInventory()).checkout(
            session,
            actor_id=actor_id,
            idempotency_key="checkout-rollback-key-0001",
            items=[checkout_line(product_id)],
        )

    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 0
        )
        assert (
            verify.scalar(
                select(func.count(IdempotencyRecord.user_id)).where(
                    IdempotencyRecord.user_id == actor_id
                )
            )
            == 0
        )
        assert (
            verify.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id == product_id
                )
            )
            == 0
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 2


def run_concurrent_checkout(
    engine: Engine,
    barrier: threading.Barrier,
    *,
    actor_id: int,
    product_id: int,
    key: str,
) -> tuple[str, int | str]:
    with Session(engine) as session:
        barrier.wait(timeout=5)
        try:
            result = checkout_service().checkout(
                session,
                actor_id=actor_id,
                idempotency_key=key,
                items=[checkout_line(product_id)],
            )
            return "success", result.id
        except ConflictError as error:
            return "conflict", error.code


def test_two_different_keys_compete_for_single_stock(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, "race-different", quantity=1
    )
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                run_concurrent_checkout,
                migrated_integration_engine,
                barrier,
                actor_id=actor_id,
                product_id=product_id,
                key=f"checkout-race-different-{index}",
            )
            for index in (1, 2)
        ]
        results = [future.result(timeout=15) for future in futures]

    assert sum(result[0] == "success" for result in results) == 1
    assert ("conflict", "INSUFFICIENT_STOCK") in results
    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 1
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 0


def test_concurrent_same_key_creates_one_order(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, "race-same", quantity=2
    )
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                run_concurrent_checkout,
                migrated_integration_engine,
                barrier,
                actor_id=actor_id,
                product_id=product_id,
                key="checkout-race-same-key-0001",
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=15) for future in futures]

    successes = [result for result in results if result[0] == "success"]
    assert successes
    assert len({result[1] for result in successes}) == 1
    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 1
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 1


def test_lock_timeout_rolls_back_claim_and_business_state(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id = seed_checkout(
        migrated_integration_engine, "lock-timeout", quantity=2
    )
    blocker = Session(migrated_integration_engine)
    try:
        blocker.scalar(
            select(Product).where(Product.id == product_id).with_for_update()
        )

        def attempt() -> str:
            with Session(migrated_integration_engine) as session:
                session.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
                with pytest.raises(StockConflictError):
                    checkout_service().checkout(
                        session,
                        actor_id=actor_id,
                        idempotency_key="checkout-lock-timeout-0001",
                        items=[checkout_line(product_id)],
                    )
                return "rolled_back"

        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(attempt).result(timeout=10) == "rolled_back"
    finally:
        blocker.rollback()
        blocker.close()

    with Session(migrated_integration_engine) as verify:
        assert (
            verify.scalar(
                select(func.count(Order.id)).where(Order.created_by == actor_id)
            )
            == 0
        )
        assert (
            verify.scalar(
                select(func.count(IdempotencyRecord.user_id)).where(
                    IdempotencyRecord.user_id == actor_id
                )
            )
            == 0
        )
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 2


def cancel_service(
    *,
    now: datetime,
    inventory: InventoryService | None = None,
) -> OrderService:
    return OrderService(
        inventory or InventoryService(),
        idempotency=IdempotencyExecutor(secret=IDEMPOTENCY_SECRET),
        clock=lambda: now.replace(tzinfo=UTC),
    )


def create_order_for_cancel(
    engine: Engine, suffix: str, *, quantity: int = 2
) -> tuple[int, int, int, datetime]:
    actor_id, product_id = seed_checkout(engine, suffix, quantity=5)
    sold_at = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)
    checkout = CheckoutService(
        InventoryService(),
        idempotency=IdempotencyExecutor(secret=IDEMPOTENCY_SECRET),
        clock=lambda: sold_at,
    )
    with Session(engine) as session:
        order = checkout.checkout(
            session,
            actor_id=actor_id,
            idempotency_key=f"checkout-for-cancel-{suffix}",
            items=[checkout_line(product_id, quantity=quantity)],
        )
    return actor_id, product_id, order.id, sold_at


def test_cancel_replay_restores_stock_and_movement_once(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id, order_id, sold_at = create_order_for_cancel(
        migrated_integration_engine, "cancel-replay"
    )
    service = cancel_service(now=sold_at + timedelta(minutes=15))
    with Session(migrated_integration_engine) as session:
        first = service.cancel(
            session,
            actor_id=actor_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="  Customer mistake  ",
            idempotency_key="cancel-replay-key-0001",
        )
        replay = service.cancel(
            session,
            actor_id=actor_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Customer mistake",
            idempotency_key="cancel-replay-key-0001",
        )
    assert replay == first
    with Session(migrated_integration_engine) as verify:
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 5
        assert (
            verify.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.order_id == order_id,
                    StockMovement.kind == "ORDER_CANCEL",
                )
            )
            == 1
        )


def test_cancel_same_key_different_reason_or_order_conflicts(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id, first_order_id, sold_at = create_order_for_cancel(
        migrated_integration_engine, "cancel-conflict", quantity=1
    )
    with Session(migrated_integration_engine) as session:
        second_order = CheckoutService(
            InventoryService(),
            idempotency=IdempotencyExecutor(secret=IDEMPOTENCY_SECRET),
            clock=lambda: sold_at,
        ).checkout(
            session,
            actor_id=actor_id,
            idempotency_key="checkout-second-cancel-conflict",
            items=[checkout_line(product_id)],
        )
        service = cancel_service(now=sold_at + timedelta(minutes=1))
        service.cancel(
            session,
            actor_id=actor_id,
            actor_role="STAFF",
            order_id=first_order_id,
            reason="Reason one",
            idempotency_key="cancel-conflict-key-0001",
        )
        for target_order, reason in (
            (first_order_id, "Reason two"),
            (second_order.id, "Reason one"),
        ):
            with pytest.raises(IdempotencyKeyReusedError):
                service.cancel(
                    session,
                    actor_id=actor_id,
                    actor_role="STAFF",
                    order_id=target_order,
                    reason=reason,
                    idempotency_key="cancel-conflict-key-0001",
                )


class FailingRestoreInventory(InventoryService):
    def restore_for_cancel(self, *args: object, **kwargs: object):
        raise RuntimeError("restore failed")


def test_cancel_restore_failure_rolls_back_order_claim_and_stock(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id, order_id, sold_at = create_order_for_cancel(
        migrated_integration_engine, "cancel-rollback"
    )
    with (
        Session(migrated_integration_engine) as session,
        pytest.raises(RuntimeError, match="restore failed"),
    ):
        cancel_service(
            now=sold_at + timedelta(minutes=1),
            inventory=FailingRestoreInventory(),
        ).cancel(
            session,
            actor_id=actor_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Rollback test",
            idempotency_key="cancel-rollback-key-0001",
        )
    with Session(migrated_integration_engine) as verify:
        order = verify.get(Order, order_id)
        inventory = verify.get(Inventory, product_id)
        assert order is not None and order.status == "COMPLETED"
        assert inventory is not None and inventory.quantity == 3
        assert (
            verify.scalar(
                select(func.count(IdempotencyRecord.user_id)).where(
                    IdempotencyRecord.user_id == actor_id,
                    IdempotencyRecord.operation == "CANCEL_ORDER",
                )
            )
            == 0
        )


def test_two_different_keys_cancel_once_concurrently(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id, order_id, sold_at = create_order_for_cancel(
        migrated_integration_engine, "cancel-race"
    )
    barrier = threading.Barrier(2)

    def attempt(index: int) -> str:
        with Session(migrated_integration_engine) as session:
            barrier.wait(timeout=5)
            try:
                cancel_service(now=sold_at + timedelta(minutes=1)).cancel(
                    session,
                    actor_id=actor_id,
                    actor_role="STAFF",
                    order_id=order_id,
                    reason="Concurrent cancel",
                    idempotency_key=f"cancel-race-key-{index:04d}",
                )
                return "success"
            except InvalidStateError:
                return "invalid_state"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, index) for index in (1, 2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) == ["invalid_state", "success"]
    with Session(migrated_integration_engine) as verify:
        inventory = verify.get(Inventory, product_id)
        assert inventory is not None and inventory.quantity == 5
        assert (
            verify.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.order_id == order_id,
                    StockMovement.kind == "ORDER_CANCEL",
                )
            )
            == 1
        )


def test_cancel_order_header_lock_timeout_rolls_back_idempotency_claim(
    migrated_integration_engine: Engine,
) -> None:
    actor_id, product_id, order_id, sold_at = create_order_for_cancel(
        migrated_integration_engine, "cancel-lock-timeout"
    )
    blocker = Session(migrated_integration_engine)
    try:
        blocker.scalar(select(Order).where(Order.id == order_id).with_for_update())

        def attempt() -> None:
            with Session(migrated_integration_engine) as session:
                session.execute(text("SET SESSION innodb_lock_wait_timeout = 1"))
                with pytest.raises(OperationalError):
                    cancel_service(now=sold_at + timedelta(minutes=1)).cancel(
                        session,
                        actor_id=actor_id,
                        actor_role="STAFF",
                        order_id=order_id,
                        reason="Lock timeout",
                        idempotency_key="cancel-lock-timeout-key-0001",
                    )

        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(attempt).result(timeout=10)
    finally:
        blocker.rollback()
        blocker.close()

    with Session(migrated_integration_engine) as verify:
        order = verify.get(Order, order_id)
        inventory = verify.get(Inventory, product_id)
        assert order is not None and order.status == "COMPLETED"
        assert inventory is not None and inventory.quantity == 3
        assert (
            verify.scalar(
                select(func.count(IdempotencyRecord.user_id)).where(
                    IdempotencyRecord.user_id == actor_id,
                    IdempotencyRecord.operation == "CANCEL_ORDER",
                )
            )
            == 0
        )
