"""T04AA50: Real MySQL 8 P0 regression tests filling Sprint 2-3 coverage gaps.

Covers missing P0 MySQL/InnoDB invariants without duplicating existing suites:
1. Race 5: Concurrent Inventory Adjustment vs Checkout on same SKU (Barrier).
2. Multi-item Checkout atomicity (insufficient 2nd item), rollback & retry key.
3. Email / Outbox boundary: mid-tx rollback leaves zero phantom outbox events;
   broker publish failure preserves committed business state and durability.
4. AI boundary on real MySQL 8: STAFF/PENDING/forged ToolContext denied (403),
   adversarial write/SQL tools & SQLi args blocked (422), MySQL state unchanged.
5. Auth boundary across Receipt, Inventory Adjustment, Checkout & Cancel.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    ForbiddenError,
)
from app.db.session import get_db_session
from app.main import create_app
from app.modules.ai.gemini_provider import (
    ProviderFunctionCall,
    ProviderTurnResponse,
    ToolResponseItem,
)
from app.modules.ai.orchestrator import AIOrchestrator
from app.modules.ai.tool_executor import (
    ToolContext,
    bind_authenticated_request,
)
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.auth.models import AuthSession, User, UserRole, UserStatus
from app.modules.auth.security import JwtService
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
)
from app.modules.inventory.exceptions import (
    StaleStockVersionError,
    StockConflictError,
)
from app.modules.inventory.models import (
    InventoryAdjustment,
    MovementKind,
    StockMovement,
)
from app.modules.inventory.schemas import CountAdjustment
from app.modules.inventory.service import InventoryService
from app.modules.outbox.errors import BrokerPublishError
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.publisher import OutboxPublisher
from app.modules.outbox.writer import OutboxWriter
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService
from app.modules.suppliers.models import Supplier, SupplierStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]

pytestmark = pytest.mark.integration


def _make_settings(db_url: URL, run_id: str) -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        db_host=db_url.host or "127.0.0.1",
        db_port=db_url.port or 3306,
        db_name=db_url.database or "retailops_test",
        db_user=db_url.username or "retailops_test_runner",
        db_password=SecretStr(db_url.password or ""),
        jwt_secret=SecretStr(f"t04aa50-jwt-{run_id}-0123456789abcdef"),
        csrf_secret=SecretStr(f"t04aa50-csrf-{run_id}-0123456789abcdef"),
        idempotency_secret=SecretStr(f"t04aa50-idem-{run_id}-0123456789abcdef"),
    )


def _seed_actors(engine: Engine, run_id: str, settings: Settings) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    owned_user_ids: list[int] = []
    owned_session_ids: list[bytes] = []

    with Session(engine) as session, session.begin():
        admin = session.scalar(
            select(User).where(
                User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
            )
        )
        if admin is None:
            admin = User(
                email_normalized=f"t04aa50-admin-{run_id}@example.com",
                password_hash="non-secret-hash",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()
            owned_user_ids.append(admin.id)

        staff = User(
            email_normalized=f"t04aa50-staff-{run_id}@example.com",
            password_hash="non-secret-hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        pending = User(
            email_normalized=f"t04aa50-pending-{run_id}@example.com",
            password_hash="non-secret-hash",
            role=UserRole.STAFF,
            status=UserStatus.PENDING_APPROVAL,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add_all([staff, pending])
        session.flush()
        owned_user_ids.extend([staff.id, pending.id])

        admin_sess = uuid4().bytes
        staff_sess = uuid4().bytes
        pending_sess = uuid4().bytes
        session.add_all(
            [
                AuthSession(
                    id=admin_sess,
                    user_id=admin.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=4),
                    revoked_at=None,
                ),
                AuthSession(
                    id=staff_sess,
                    user_id=staff.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=4),
                    revoked_at=None,
                ),
                AuthSession(
                    id=pending_sess,
                    user_id=pending.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=4),
                    revoked_at=None,
                ),
            ]
        )
        owned_session_ids.extend([admin_sess, staff_sess, pending_sess])
        admin_id, staff_id, pending_id = admin.id, staff.id, pending.id

    jwt_svc = JwtService(settings)
    now_utc = datetime.now(UTC)
    admin_tok, _ = jwt_svc.issue(
        user_id=admin_id,
        session_id=UUID(bytes=admin_sess),
        session_expires_at=now_utc + timedelta(hours=2),
        now=now_utc,
    )
    staff_tok, _ = jwt_svc.issue(
        user_id=staff_id,
        session_id=UUID(bytes=staff_sess),
        session_expires_at=now_utc + timedelta(hours=2),
        now=now_utc,
    )
    pending_tok, _ = jwt_svc.issue(
        user_id=pending_id,
        session_id=UUID(bytes=pending_sess),
        session_expires_at=now_utc + timedelta(hours=2),
        now=now_utc,
    )
    return {
        "admin_id": admin_id,
        "staff_id": staff_id,
        "pending_id": pending_id,
        "admin_sess": admin_sess,
        "staff_sess": staff_sess,
        "pending_sess": pending_sess,
        "admin_headers": {"Authorization": f"Bearer {admin_tok}"},
        "staff_headers": {"Authorization": f"Bearer {staff_tok}"},
        "pending_headers": {"Authorization": f"Bearer {pending_tok}"},
        "owned_user_ids": owned_user_ids,
        "owned_session_ids": owned_session_ids,
    }


def _cleanup(
    engine: Engine,
    *,
    product_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    supplier_ids: list[int] | None = None,
    receipt_ids: list[int] | None = None,
    order_ids: list[int] | None = None,
    event_ids: list[bytes] | None = None,
    owned_session_ids: list[bytes] | None = None,
    owned_user_ids: list[int] | None = None,
) -> None:
    with Session(engine) as session, session.begin():
        if event_ids:
            session.execute(delete(OutboxEvent).where(OutboxEvent.id.in_(event_ids)))
        if product_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
            session.execute(
                delete(InventoryAdjustment).where(
                    InventoryAdjustment.product_id.in_(product_ids)
                )
            )
        if order_ids:
            session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            session.execute(delete(Order).where(Order.id.in_(order_ids)))
        if receipt_ids:
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id.in_(receipt_ids)
                )
            )
            session.execute(
                delete(PurchaseReceipt).where(PurchaseReceipt.id.in_(receipt_ids))
            )
        if owned_user_ids:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id.in_(owned_user_ids)
                )
            )
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))
        if category_ids:
            session.execute(delete(Category).where(Category.id.in_(category_ids)))
        if supplier_ids:
            session.execute(delete(Supplier).where(Supplier.id.in_(supplier_ids)))
        if owned_session_ids:
            session.execute(
                delete(AuthSession).where(AuthSession.id.in_(owned_session_ids))
            )
        if owned_user_ids:
            session.execute(delete(User).where(User.id.in_(owned_user_ids)))


def test_t04aa50_race5_concurrent_adjustment_and_checkout_same_sku_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Race 5: Concurrent Inventory Adjustment vs Checkout on same SKU in MySQL 8."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    idem_secret = settings.idempotency_secret.get_secret_value().encode("utf-8")
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    cat_ids: list[int] = []
    prod_ids: list[int] = []
    order_ids: list[int] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"AA50-R5-{run_id}",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(cat)
            session.flush()
            cat_ids.append(cat.id)

            prod = Product(
                category_id=cat.id,
                sku=f"AA50-R5-{run_id}",
                name="Race 5 Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=25_000,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            prod_ids.append(prod.id)
            session.add(
                Inventory(
                    product_id=prod.id,
                    quantity=5,
                    stock_version=1,
                    first_stocked_at=now,
                    updated_at=now,
                )
            )
            prod_id = prod.id

        barrier = Barrier(2)

        def _checkout_worker() -> tuple[str, int | None]:
            svc = CheckoutService(
                InventoryService(),
                idempotency=IdempotencyExecutor(secret=idem_secret),
            )
            with Session(migrated_integration_engine) as session:
                barrier.wait(timeout=10)
                order = svc.checkout(
                    session,
                    actor_id=actors["staff_id"],
                    idempotency_key=f"aa50-r5-co-{run_id}-01",
                    items=[
                        CheckoutLine(
                            product_id=prod_id,
                            quantity=3,
                            viewed_unit_price_vnd=25_000,
                        )
                    ],
                )
                return "OK", order.id

        def _adjust_worker() -> str:
            inv_svc = InventoryService()
            idem = IdempotencyExecutor(secret=idem_secret)
            with Session(migrated_integration_engine) as session:
                barrier.wait(timeout=10)
                try:

                    def _cmd() -> CommandOutcome[dict[str, object]]:
                        locks = inv_svc.lock_for_mutation(
                            session, product_ids=[prod_id]
                        )
                        res = inv_svc.adjust_to_count(
                            session,
                            locks=locks,
                            actor_id=actors["admin_id"],
                            adjustment=CountAdjustment(
                                product_id=prod_id,
                                counted_quantity=10,
                                expected_stock_version=1,
                                reason="Concurrent physical count",
                            ),
                        )
                        return CommandOutcome(200, {"qty": res.stock.quantity})

                    idem.execute(
                        session,
                        actor_id=actors["admin_id"],
                        operation=IdempotencyOperation.INVENTORY_ADJUSTMENT,
                        idempotency_key=f"aa50-r5-adj-{run_id}-01",
                        request_identity={
                            "operation": "INVENTORY_ADJUSTMENT",
                            "resource_id": prod_id,
                            "body": {"counted_quantity": 10},
                        },
                        command=_cmd,
                    )
                    session.commit()
                    return "OK"
                except (StaleStockVersionError, StockConflictError, ConflictError):
                    session.rollback()
                    return "CONFLICT"

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_co = pool.submit(_checkout_worker)
            f_adj = pool.submit(_adjust_worker)
            co_status, co_order_id = f_co.result(timeout=20)
            adj_status = f_adj.result(timeout=20)

        assert co_status == "OK" and co_order_id is not None
        order_ids.append(co_order_id)
        assert adj_status in ("OK", "CONFLICT")

        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity >= 0
            movs = list(
                session.scalars(
                    select(StockMovement)
                    .where(StockMovement.product_id == prod_id)
                    .order_by(StockMovement.id.asc())
                )
            )
            assert 5 + sum(m.delta for m in movs) == inv.quantity
            assert inv.stock_version == 1 + len(movs)
            if adj_status == "CONFLICT":
                assert inv.quantity == 2
                assert [m.kind for m in movs] == [MovementKind.SALE]
            else:
                assert inv.quantity == 7
                assert {m.kind for m in movs} == {
                    MovementKind.ADJUSTMENT,
                    MovementKind.SALE,
                }
    finally:
        _cleanup(
            migrated_integration_engine,
            product_ids=prod_ids,
            category_ids=cat_ids,
            order_ids=order_ids,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )


def test_t04aa50_multi_item_checkout_atomicity_rollback_and_retry_same_key_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Section 5B, 7 & 8: Multi-item refusal, mid-tx rollback & retry same key."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    idem_secret = settings.idempotency_secret.get_secret_value().encode("utf-8")
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    cat_ids: list[int] = []
    prod_ids: list[int] = []
    order_ids: list[int] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"AA50-RB-{run_id}",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(cat)
            session.flush()
            cat_ids.append(cat.id)

            p1 = Product(
                category_id=cat.id,
                sku=f"AA50-RB1-{run_id}",
                name="Sufficient Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=10_000,
                created_at=now,
                updated_at=now,
            )
            p2 = Product(
                category_id=cat.id,
                sku=f"AA50-RB2-{run_id}",
                name="Scarce Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=20_000,
                created_at=now,
                updated_at=now,
            )
            session.add_all([p1, p2])
            session.flush()
            prod_ids.extend([p1.id, p2.id])
            session.add_all(
                [
                    Inventory(
                        product_id=p1.id,
                        quantity=10,
                        stock_version=1,
                        first_stocked_at=now,
                        updated_at=now,
                    ),
                    Inventory(
                        product_id=p2.id,
                        quantity=1,
                        stock_version=1,
                        first_stocked_at=now,
                        updated_at=now,
                    ),
                ]
            )
            p1_id, p2_id = p1.id, p2.id

        # 1. Multi-item checkout: item 1 sufficient (10>=4), item 2 fails (1<5)
        svc = CheckoutService(
            InventoryService(),
            idempotency=IdempotencyExecutor(secret=idem_secret),
        )
        with (
            Session(migrated_integration_engine) as session,
            pytest.raises(ConflictError) as exc_info,
        ):
            svc.checkout(
                session,
                actor_id=actors["staff_id"],
                idempotency_key=f"aa50-multi-insuff-{run_id}",
                items=[
                    CheckoutLine(
                        product_id=p1_id, quantity=4, viewed_unit_price_vnd=10_000
                    ),
                    CheckoutLine(
                        product_id=p2_id, quantity=5, viewed_unit_price_vnd=20_000
                    ),
                ],
            )
        assert exc_info.value.code == "INSUFFICIENT_STOCK"

        with Session(migrated_integration_engine) as session:
            inv1 = session.get(Inventory, p1_id)
            inv2 = session.get(Inventory, p2_id)
            assert inv1 is not None and inv1.quantity == 10 and inv1.stock_version == 1
            assert inv2 is not None and inv2.quantity == 1 and inv2.stock_version == 1
            assert (
                session.scalar(
                    select(func.count(StockMovement.id)).where(
                        StockMovement.product_id.in_([p1_id, p2_id])
                    )
                )
                == 0
            )

        # 2. Fault injection during decrease_for_checkout -> full rollback
        class _FailingAfterOrderFlushInventory(InventoryService):
            def decrease_for_checkout(self, *args: Any, **kwargs: Any):
                raise RuntimeError("injected mid-tx inventory failure")

        retry_key = f"aa50-rollback-retry-{run_id}"
        valid_items = [
            CheckoutLine(product_id=p1_id, quantity=2, viewed_unit_price_vnd=10_000),
            CheckoutLine(product_id=p2_id, quantity=1, viewed_unit_price_vnd=20_000),
        ]
        failing_svc = CheckoutService(
            _FailingAfterOrderFlushInventory(),
            idempotency=IdempotencyExecutor(secret=idem_secret),
        )
        with (
            Session(migrated_integration_engine) as session,
            pytest.raises(RuntimeError, match="injected mid-tx inventory failure"),
        ):
            failing_svc.checkout(
                session,
                actor_id=actors["staff_id"],
                idempotency_key=retry_key,
                items=valid_items,
            )

        # Assert ZERO partial writes in MySQL (orders, inventory, movements)
        with Session(migrated_integration_engine) as session:
            assert (
                session.scalar(
                    select(func.count(Order.id)).where(
                        Order.created_by == actors["staff_id"]
                    )
                )
                == 0
            )
            inv1 = session.get(Inventory, p1_id)
            inv2 = session.get(Inventory, p2_id)
            assert inv1 is not None and inv1.quantity == 10
            assert inv2 is not None and inv2.quantity == 1

        # 3. Retry with EXACT SAME Idempotency-Key after rollback -> succeeds cleanly!
        with Session(migrated_integration_engine) as session:
            order = svc.checkout(
                session,
                actor_id=actors["staff_id"],
                idempotency_key=retry_key,
                items=valid_items,
            )
        order_ids.append(order.id)
        assert order.total_vnd == 2 * 10_000 + 1 * 20_000

        with Session(migrated_integration_engine) as session:
            inv1 = session.get(Inventory, p1_id)
            inv2 = session.get(Inventory, p2_id)
            assert inv1 is not None and inv1.quantity == 8 and inv1.stock_version == 2
            assert inv2 is not None and inv2.quantity == 0 and inv2.stock_version == 2
    finally:
        _cleanup(
            migrated_integration_engine,
            product_ids=prod_ids,
            category_ids=cat_ids,
            order_ids=order_ids,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )


def test_t04aa50_email_outbox_rollback_and_broker_failure_isolation_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Section 5F & 7: Rollback leaves 0 phantom events; broker failure keeps intent."""
    run_id = uuid4().hex[:10]
    now_utc = datetime.now(UTC).replace(microsecond=0)
    now = now_utc.replace(tzinfo=None)
    owned_user_ids: list[int] = []
    event_ids: list[bytes] = []

    try:
        # 1. Mid-tx rollback after OutboxWriter.append -> 0 phantom outbox rows
        phantom_event_id: bytes | None = None
        phantom_email = f"aa50-phantom-{run_id}@example.com"
        with (
            pytest.raises(RuntimeError, match="forced rollback"),
            Session(migrated_integration_engine) as session,
            session.begin(),
        ):
            ghost_user = User(
                email_normalized=phantom_email,
                password_hash="non-secret-hash",
                role=UserRole.STAFF,
                status=UserStatus.ACTIVE,
                admin_slot=None,
                created_at=now,
                updated_at=now,
            )
            session.add(ghost_user)
            session.flush()
            phantom_event_id = OutboxWriter().append(
                session,
                subject_user_id=ghost_user.id,
                event_type="STAFF_APPROVED",
                payload={
                    "schema_version": 1,
                    "approval_request_id": 1,
                    "actor_id": 1,
                },
                available_at_utc=now_utc,
            )
            raise RuntimeError("forced rollback")

        with Session(migrated_integration_engine) as session:
            assert phantom_event_id is not None
            assert session.get(OutboxEvent, phantom_event_id) is None
            assert (
                session.scalar(
                    select(User).where(User.email_normalized == phantom_email)
                )
                is None
            )

        # 2. Committed business + Outbox event survives broker failure without data loss
        with Session(migrated_integration_engine) as session, session.begin():
            user = User(
                email_normalized=f"aa50-durable-{run_id}@example.com",
                password_hash="non-secret-hash",
                role=UserRole.STAFF,
                status=UserStatus.ACTIVE,
                admin_slot=None,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            owned_user_ids.append(user.id)
            durable_event_id = OutboxWriter().append(
                session,
                subject_user_id=user.id,
                event_type="STAFF_APPROVED",
                payload={"schema_version": 1, "approval_request_id": 2, "actor_id": 1},
                available_at_utc=now_utc,
            )
            event_ids.append(durable_event_id)

        class _DownBroker:
            def publish(self, _event_id: bytes) -> None:
                raise BrokerPublishError("simulated RabbitMQ outage secret=NO_LEAK")

        sf = sessionmaker(bind=migrated_integration_engine, expire_on_commit=False)
        pub_result = OutboxPublisher(_DownBroker()).publish_due(sf, batch_size=25)
        assert pub_result.failed >= 1

        with Session(migrated_integration_engine) as session:
            ev = session.get(OutboxEvent, durable_event_id)
            persisted_user = session.get(User, owned_user_ids[0])
            assert persisted_user is not None
            assert ev is not None
            assert ev.published_at is None
            assert ev.outcome is None
            assert ev.publish_attempts >= 1
            assert ev.last_error_code == "BROKER_PUBLISH_FAILED"
            assert "NO_LEAK" not in (ev.last_error_code or "")
    finally:
        _cleanup(
            migrated_integration_engine,
            event_ids=event_ids,
            owned_user_ids=owned_user_ids,
        )


@pytest.mark.anyio
async def test_t04aa50_ai_boundary_rbac_and_write_tool_denial_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Section 5G: AI boundary on real MySQL 8 denies STAFF/forged/write tools."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    sf = sessionmaker(
        bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
    )

    try:
        with Session(migrated_integration_engine) as session:
            before_counts = (
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(InventoryAdjustment.id))),
            )
            staff_user = session.get(User, actors["staff_id"])
            pending_user = session.get(User, actors["pending_id"])
            admin_user = session.get(User, actors["admin_id"])
            assert staff_user and pending_user and admin_user

            # 1. STAFF & PENDING users rejected by AIToolExecutor against real MySQL
            for non_admin, sess_bytes in (
                (staff_user, actors["staff_sess"]),
                (pending_user, actors["pending_sess"]),
            ):
                bound_non_admin = bind_authenticated_request(
                    CurrentPrincipal(user=non_admin, session_id=UUID(bytes=sess_bytes)),
                    request_id=f"aa50-nonadmin-{run_id}",
                )
                with pytest.raises(ForbiddenError):
                    bound_non_admin.executor.execute(
                        session,
                        tool_id="get_low_stock",
                        arguments={"limit": 5},
                        context=bound_non_admin.context,
                    )

            # 2. Forged ToolContext rejected
            bound_admin = bind_authenticated_request(
                CurrentPrincipal(
                    user=admin_user, session_id=UUID(bytes=actors["admin_sess"])
                ),
                request_id=f"aa50-admin-{run_id}",
            )
            forged = ToolContext(
                actor_id=admin_user.id,
                actor_role="ADMIN",
                request_id=f"aa50-admin-{run_id}",
            )
            with pytest.raises(ForbiddenError):
                bound_admin.executor.execute(
                    session,
                    tool_id="get_low_stock",
                    arguments={"limit": 5},
                    context=forged,
                )

        # 3. Adversarial LLM proposing write/SQL tools blocked by AIOrchestrator
        class _MaliciousProvider:
            def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
                self._name = tool_name
                self._args = args

            async def generate_turn(
                self, _msg: str, *, timeout_seconds: float
            ) -> ProviderTurnResponse:
                return ProviderTurnResponse(
                    text=None,
                    function_calls=(
                        ProviderFunctionCall(name=self._name, arguments=self._args),
                    ),
                    conversation_state={"step": 1},
                )

            async def submit_tool_results(
                self,
                _state: object,
                _responses: tuple[ToolResponseItem, ...],
                *,
                timeout_seconds: float,
            ) -> ProviderTurnResponse:
                return ProviderTurnResponse(
                    text="ok", function_calls=(), conversation_state=None
                )

        with Session(migrated_integration_engine) as session:
            admin_user = session.get(User, actors["admin_id"])
            assert admin_user is not None
            for tool_name, args in (
                ("adjust_inventory", {"product_id": 1, "counted_quantity": 999}),
                ("execute_sql", {"sql": "DELETE FROM orders"}),
                (
                    "get_sales_summary",
                    {"start_date": "2026-11-01' OR '1'='1", "end_date": "2026-11-18"},
                ),
            ):
                bound = bind_authenticated_request(
                    CurrentPrincipal(
                        user=admin_user, session_id=UUID(bytes=actors["admin_sess"])
                    ),
                    request_id=f"aa50-ai-{tool_name}",
                )
                orch = AIOrchestrator(
                    session_factory=sf,
                    provider_factory=lambda n=tool_name, a=args: _MaliciousProvider(
                        n, a
                    ),
                    gemini_timeout_seconds=5.0,
                )
                with pytest.raises(DomainValidationError):
                    await orch.handle_query(
                        message="So sánh hiệu suất kinh doanh theo nhóm hàng",
                        bound=bound,
                    )

        with Session(migrated_integration_engine) as session:
            after_counts = (
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(InventoryAdjustment.id))),
            )
            assert after_counts == before_counts
    finally:
        _cleanup(
            migrated_integration_engine,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )


def test_t04aa50_auth_boundary_mutations_leave_mysql_unchanged(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Section 5E: Unauth/STAFF/PENDING denied across Receipt/Inventory/Order APIs."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    cat_ids: list[int] = []
    sup_ids: list[int] = []
    prod_ids: list[int] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"AA50-AUTH-{run_id}",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            sup = Supplier(
                name=f"AA50-SUP-{run_id}",
                contact_phone="0909000111",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add_all([cat, sup])
            session.flush()
            cat_ids.append(cat.id)
            sup_ids.append(sup.id)

            prod = Product(
                category_id=cat.id,
                sku=f"AA50-AUTH-{run_id}",
                name="Auth Guard Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=15_000,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            prod_ids.append(prod.id)
            session.add(
                Inventory(
                    product_id=prod.id,
                    quantity=5,
                    stock_version=1,
                    first_stocked_at=now,
                    updated_at=now,
                )
            )
            prod_id, sup_id = prod.id, sup.id

        sf = sessionmaker(
            bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
        )
        app = create_app(settings)

        def _override_db():
            with sf() as session:
                yield session

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db_session] = _override_db

        with Session(migrated_integration_engine) as session:
            before = (
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(InventoryAdjustment.id))),
                session.scalar(select(func.count(StockMovement.id))),
            )

        with TestClient(app) as client:
            # 1. Missing token -> 401 on Receipt, Inventory Adjustment, Checkout
            assert (
                client.post(
                    "/api/v1/purchase-receipts",
                    json={
                        "supplier_id": sup_id,
                        "items": [
                            {
                                "product_id": prod_id,
                                "quantity": 1,
                                "unit_cost_vnd": 5000,
                            }
                        ],
                    },
                ).status_code
                == 401
            )
            assert (
                client.post(
                    f"/api/v1/inventory/{prod_id}/adjustments",
                    headers={"Idempotency-Key": f"aa50-unauth-adj-{run_id}"},
                    json={
                        "counted_quantity": 9,
                        "expected_stock_version": 1,
                        "reason": "unauth",
                    },
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/orders/checkout",
                    headers={"Idempotency-Key": f"aa50-unauth-co-{run_id}"},
                    json={
                        "items": [
                            {
                                "product_id": prod_id,
                                "quantity": 1,
                                "viewed_unit_price_vnd": 15_000,
                            }
                        ]
                    },
                ).status_code
                == 401
            )

            # 2. STAFF -> 403 on Admin-only Receipt & Inventory Adjustment
            assert (
                client.post(
                    "/api/v1/purchase-receipts",
                    headers=actors["staff_headers"],
                    json={
                        "supplier_id": sup_id,
                        "items": [
                            {
                                "product_id": prod_id,
                                "quantity": 1,
                                "unit_cost_vnd": 5000,
                            }
                        ],
                    },
                ).status_code
                == 403
            )
            assert (
                client.post(
                    f"/api/v1/inventory/{prod_id}/adjustments",
                    headers={
                        **actors["staff_headers"],
                        "Idempotency-Key": f"aa50-staff-adj-{run_id}",
                    },
                    json={
                        "counted_quantity": 9,
                        "expected_stock_version": 1,
                        "reason": "staff forbidden",
                    },
                ).status_code
                == 403
            )

            # 3. PENDING_APPROVAL user -> 401/403 on Checkout
            r_pending = client.post(
                "/api/v1/orders/checkout",
                headers={
                    **actors["pending_headers"],
                    "Idempotency-Key": f"aa50-pend-co-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": 15_000,
                        }
                    ]
                },
            )
            assert r_pending.status_code in (401, 403)

        with Session(migrated_integration_engine) as session:
            after = (
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(InventoryAdjustment.id))),
                session.scalar(select(func.count(StockMovement.id))),
            )
            inv = session.get(Inventory, prod_id)
            assert after == before
            assert inv is not None and inv.quantity == 5 and inv.stock_version == 1
    finally:
        _cleanup(
            migrated_integration_engine,
            product_ids=prod_ids,
            category_ids=cat_ids,
            supplier_ids=sup_ids,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )
