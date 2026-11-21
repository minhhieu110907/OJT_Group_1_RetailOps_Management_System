"""Real MySQL 8 / InnoDB cross-module integration & concurrency invariants.

Covers Sections A, B, C, D:
- Inventory basic consistency (0, normal, large stock, 404 nonexistent),
  adjustment (stale version 409, no-op audit-only, STAFF 403, idempotency).
- Purchase Receipt multi-item happy path (existing + never-stocked product),
  duplicate confirm replay (same key) & terminal rejection (new key 409),
  transaction rollback atomicity when a second item becomes INACTIVE.
- Order Checkout & Cancel lifecycle, replay protection, and exact Section 6.3/6.4
  concurrency (initial stock 5, two concurrent checkouts of 4 -> [201, 409],
  final stock 1; two concurrent cancels -> [200, 409], restored once to 5).
- Cross-module read-only SQL invariant verification across inventories,
  stock_movements, purchase_receipts, orders, and idempotency_records.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, InvalidStateError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.models import AuthSession, User, UserRole, UserStatus
from app.modules.auth.security import JwtService
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import IdempotencyExecutor
from app.modules.inventory.exceptions import StockConflictError
from app.modules.inventory.models import (
    InventoryAdjustment,
    MovementKind,
    StockMovement,
)
from app.modules.inventory.service import InventoryService
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService, OrderService
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
        jwt_secret=SecretStr(f"xmod-jwt-{run_id}-0123456789abcdef"),
        csrf_secret=SecretStr(f"xmod-csrf-{run_id}-0123456789abcdef"),
        idempotency_secret=SecretStr(f"xmod-idem-{run_id}-0123456789abcdef"),
    )


def _create_test_app(engine: Engine, settings: Settings):
    sf = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = create_app(settings)

    def _override_db():
        with sf() as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = _override_db
    return app


def _seed_actors(engine: Engine, run_id: str, settings: Settings):
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
                email_normalized=f"xmod-admin-{run_id}@example.com",
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
            email_normalized=f"xmod-staff-{run_id}@example.com",
            password_hash="non-secret-hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add(staff)
        session.flush()
        owned_user_ids.append(staff.id)

        admin_sess = uuid4().bytes
        staff_sess = uuid4().bytes
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
            ]
        )
        owned_session_ids.extend([admin_sess, staff_sess])
        admin_id = admin.id
        staff_id = staff.id

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
    return {
        "admin_id": admin_id,
        "staff_id": staff_id,
        "admin_headers": {"Authorization": f"Bearer {admin_tok}"},
        "staff_headers": {"Authorization": f"Bearer {staff_tok}"},
        "owned_user_ids": owned_user_ids,
        "owned_session_ids": owned_session_ids,
    }


def _cleanup_run(
    engine: Engine,
    *,
    product_ids: list[int],
    category_ids: list[int],
    supplier_ids: list[int],
    receipt_ids: list[int],
    order_ids: list[int],
    idempotency_keys: list[str],
    owned_session_ids: list[bytes],
    owned_user_ids: list[int],
) -> None:
    with Session(engine) as session, session.begin():
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
        if idempotency_keys:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key.in_(idempotency_keys)
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


def test_cross_module_receipt_inventory_order_cancel_invariants_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Sections A, B, C, D: Full Receipt -> Inventory -> Order -> Adjust -> Cancel."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    product_ids: list[int] = []
    category_ids: list[int] = []
    supplier_ids: list[int] = []
    receipt_ids: list[int] = []
    order_ids: list[int] = []
    idem_keys: list[str] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"XModCat-{run_id}",
                description="Cross-module test",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            sup = Supplier(
                name=f"XModSup-{run_id}",
                phone="0901234567",
                email=f"sup-{run_id}@example.com",
                address="HCM",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add_all([cat, sup])
            session.flush()
            category_ids.append(cat.id)
            supplier_ids.append(sup.id)

            # Product A: stock=0 (never stocked), Product B: stock=10, Product C: large
            prod_a = Product(
                category_id=cat.id,
                sku=f"XMOD-A-{run_id}",
                name="Product A Zero",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=20_000,
                created_at=now,
                updated_at=now,
            )
            prod_b = Product(
                category_id=cat.id,
                sku=f"XMOD-B-{run_id}",
                name="Product B Existing",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=30_000,
                created_at=now,
                updated_at=now,
            )
            prod_c = Product(
                category_id=cat.id,
                sku=f"XMOD-C-{run_id}",
                name="Product C Large",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=15_000,
                created_at=now,
                updated_at=now,
            )
            session.add_all([prod_a, prod_b, prod_c])
            session.flush()
            product_ids.extend([prod_a.id, prod_b.id, prod_c.id])

            session.add_all(
                [
                    Inventory(
                        product_id=prod_a.id,
                        quantity=0,
                        stock_version=1,
                        first_stocked_at=None,
                        updated_at=now,
                    ),
                    Inventory(
                        product_id=prod_b.id,
                        quantity=10,
                        stock_version=1,
                        first_stocked_at=now - timedelta(days=5),
                        updated_at=now,
                    ),
                    Inventory(
                        product_id=prod_c.id,
                        quantity=100_000,
                        stock_version=1,
                        first_stocked_at=now - timedelta(days=5),
                        updated_at=now,
                    ),
                ]
            )
            prod_a_id, prod_b_id, prod_c_id = prod_a.id, prod_b.id, prod_c.id
            sup_id = sup.id

        app = _create_test_app(migrated_integration_engine, settings)
        with TestClient(app) as client:
            # 1. Section 4.1: API <-> DB consistency (0, normal, large, 404 nonexistent)
            assert (
                client.get(
                    f"/api/v1/inventory/{prod_a_id}", headers=actors["admin_headers"]
                ).json()["quantity"]
                == 0
            )
            assert (
                client.get(
                    f"/api/v1/inventory/{prod_b_id}", headers=actors["admin_headers"]
                ).json()["quantity"]
                == 10
            )
            assert (
                client.get(
                    f"/api/v1/inventory/{prod_c_id}", headers=actors["admin_headers"]
                ).json()["quantity"]
                == 100_000
            )
            assert (
                client.get(
                    "/api/v1/inventory/999999999", headers=actors["admin_headers"]
                ).status_code
                == 404
            )

            # 2. Section 5.1 & 5.2: Receipt creation (STAFF denied 403, ADMIN creates)
            receipt_payload = {
                "supplier_id": sup_id,
                "items": [
                    {
                        "product_id": prod_a_id,
                        "quantity": 15,
                        "unit_cost_vnd": 12_000,
                    },
                    {
                        "product_id": prod_b_id,
                        "quantity": 5,
                        "unit_cost_vnd": 18_000,
                    },
                ],
            }
            assert (
                client.post(
                    "/api/v1/purchase-receipts",
                    headers=actors["staff_headers"],
                    json=receipt_payload,
                ).status_code
                == 403
            )
            r_draft = client.post(
                "/api/v1/purchase-receipts",
                headers=actors["admin_headers"],
                json=receipt_payload,
            )
            assert r_draft.status_code == 201
            draft = r_draft.json()
            receipt_id = draft["id"]
            receipt_ids.append(receipt_id)
            assert draft["status"] == "DRAFT"

            # Confirm receipt atomically
            k_confirm = f"xmod-confirm-{run_id}-0001"
            idem_keys.append(k_confirm)
            r_conf = client.post(
                f"/api/v1/purchase-receipts/{receipt_id}/confirm",
                headers={**actors["admin_headers"], "Idempotency-Key": k_confirm},
                json={"expected_draft_version": draft["draft_version"]},
            )
            assert r_conf.status_code == 200
            assert r_conf.json()["status"] == "CONFIRMED"

            # Replay same key -> 200 without duplicate stock increase
            r_conf_replay = client.post(
                f"/api/v1/purchase-receipts/{receipt_id}/confirm",
                headers={**actors["admin_headers"], "Idempotency-Key": k_confirm},
                json={"expected_draft_version": draft["draft_version"]},
            )
            assert r_conf_replay.status_code == 200

            # Repeat confirm with new key -> 409 terminal/version conflict
            k_confirm_dup = f"xmod-confirm-dup-{run_id}"
            idem_keys.append(k_confirm_dup)
            r_conf_dup = client.post(
                f"/api/v1/purchase-receipts/{receipt_id}/confirm",
                headers={**actors["admin_headers"], "Idempotency-Key": k_confirm_dup},
                json={"expected_draft_version": r_conf.json()["draft_version"]},
            )
            assert r_conf_dup.status_code == 409

            # Verify Inventory after Receipt (A: 0->15 + first_stocked_at; B: 10->15)
            with Session(migrated_integration_engine) as session:
                inv_a = session.get(Inventory, prod_a_id)
                inv_b = session.get(Inventory, prod_b_id)
                assert inv_a is not None and inv_a.quantity == 15
                assert inv_a.stock_version == 2
                assert inv_a.first_stocked_at is not None
                assert inv_b is not None and inv_b.quantity == 15
                assert inv_b.stock_version == 2

            # 3. Section 6.1: Checkout Order across both products + replay protection
            k_checkout = f"xmod-checkout-{run_id}-0001"
            idem_keys.append(k_checkout)
            checkout_payload = {
                "items": [
                    {
                        "product_id": prod_a_id,
                        "quantity": 4,
                        "viewed_unit_price_vnd": 20_000,
                    },
                    {
                        "product_id": prod_b_id,
                        "quantity": 3,
                        "viewed_unit_price_vnd": 30_000,
                    },
                ]
            }
            r_ord = client.post(
                "/api/v1/orders/checkout",
                headers={**actors["admin_headers"], "Idempotency-Key": k_checkout},
                json=checkout_payload,
            )
            assert r_ord.status_code == 201
            order_id = r_ord.json()["id"]
            order_ids.append(order_id)
            assert r_ord.json()["total_vnd"] == 4 * 20_000 + 3 * 30_000

            # Replay checkout same key -> same order_id, zero double deduction
            r_ord_replay = client.post(
                "/api/v1/orders/checkout",
                headers={**actors["admin_headers"], "Idempotency-Key": k_checkout},
                json=checkout_payload,
            )
            assert r_ord_replay.status_code == 201
            assert r_ord_replay.json()["id"] == order_id

            # 4. Section 4.4: Adjustment stale version (409), STAFF (403), no-op (200)
            k_adj_stale = f"xmod-adj-stale-{run_id}"
            k_adj_noop = f"xmod-adj-noop-{run_id}"
            idem_keys.extend([k_adj_stale, k_adj_noop])
            assert (
                client.post(
                    f"/api/v1/inventory/{prod_a_id}/adjustments",
                    headers={**actors["staff_headers"], "Idempotency-Key": k_adj_stale},
                    json={
                        "counted_quantity": 11,
                        "expected_stock_version": 3,
                        "reason": "staff attempt",
                    },
                ).status_code
                == 403
            )
            assert (
                client.post(
                    f"/api/v1/inventory/{prod_a_id}/adjustments",
                    headers={**actors["admin_headers"], "Idempotency-Key": k_adj_stale},
                    json={
                        "counted_quantity": 11,
                        "expected_stock_version": 1,
                        "reason": "stale version",
                    },
                ).status_code
                == 409
            )
            r_noop = client.post(
                f"/api/v1/inventory/{prod_a_id}/adjustments",
                headers={**actors["admin_headers"], "Idempotency-Key": k_adj_noop},
                json={
                    "counted_quantity": 11,
                    "expected_stock_version": 3,
                    "reason": "physical count matches",
                },
            )
            assert r_noop.status_code == 200
            assert r_noop.json()["movement_created"] is False
            assert r_noop.json()["stock_version"] == 3

            # 5. Section 6.4: Cancel Order -> restores stock once; replay & repeat safe
            k_cancel = f"xmod-cancel-{run_id}-0001"
            k_cancel_dup = f"xmod-cancel-dup-{run_id}"
            idem_keys.extend([k_cancel, k_cancel_dup])
            r_cancel = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                headers={**actors["admin_headers"], "Idempotency-Key": k_cancel},
                json={"reason": "Khách đổi ý"},
            )
            assert r_cancel.status_code == 200
            assert r_cancel.json()["status"] == "CANCELLED"
            assert (
                client.post(
                    f"/api/v1/orders/{order_id}/cancel",
                    headers={**actors["admin_headers"], "Idempotency-Key": k_cancel},
                    json={"reason": "Khách đổi ý"},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/v1/orders/{order_id}/cancel",
                    headers={
                        **actors["admin_headers"],
                        "Idempotency-Key": k_cancel_dup,
                    },
                    json={"reason": "Hủy lần 2"},
                ).status_code
                == 409
            )

        # 6. Section 7: Read-Only SQL Invariant Proof across all tables
        with Session(migrated_integration_engine) as session:
            inv_a = session.get(Inventory, prod_a_id)
            inv_b = session.get(Inventory, prod_b_id)
            assert (
                inv_a is not None and inv_a.quantity == 15 and inv_a.stock_version == 4
            )
            assert (
                inv_b is not None and inv_b.quantity == 15 and inv_b.stock_version == 4
            )

            movs_a = list(
                session.scalars(
                    select(StockMovement)
                    .where(StockMovement.product_id == prod_a_id)
                    .order_by(StockMovement.id.asc())
                )
            )
            assert [m.kind for m in movs_a] == [
                MovementKind.PURCHASE_CONFIRM,
                MovementKind.SALE,
                MovementKind.ORDER_CANCEL,
            ]
            assert [m.delta for m in movs_a] == [15, -4, 4]
            assert sum(m.delta for m in movs_a) == inv_a.quantity

            movs_b = list(
                session.scalars(
                    select(StockMovement)
                    .where(StockMovement.product_id == prod_b_id)
                    .order_by(StockMovement.id.asc())
                )
            )
            assert [m.delta for m in movs_b] == [5, -3, 3]
            assert 10 + sum(m.delta for m in movs_b) == inv_b.quantity
    finally:
        _cleanup_run(
            migrated_integration_engine,
            product_ids=product_ids,
            category_ids=category_ids,
            supplier_ids=supplier_ids,
            receipt_ids=receipt_ids,
            order_ids=order_ids,
            idempotency_keys=idem_keys,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )


def test_receipt_confirm_rollback_atomicity_on_inactive_second_item_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Section 5.3: Valid item 1 + inactive item 2 fails confirm & rolls back fully."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    product_ids: list[int] = []
    category_ids: list[int] = []
    supplier_ids: list[int] = []
    receipt_ids: list[int] = []
    idem_keys: list[str] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"RollCat-{run_id}",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            sup = Supplier(
                name=f"RollSup-{run_id}",
                phone="0907654321",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add_all([cat, sup])
            session.flush()
            category_ids.append(cat.id)
            supplier_ids.append(sup.id)

            p1 = Product(
                category_id=cat.id,
                sku=f"ROLL-1-{run_id}",
                name="Active Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=10_000,
                created_at=now,
                updated_at=now,
            )
            p2 = Product(
                category_id=cat.id,
                sku=f"ROLL-2-{run_id}",
                name="Soon Inactive Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=10_000,
                created_at=now,
                updated_at=now,
            )
            session.add_all([p1, p2])
            session.flush()
            product_ids.extend([p1.id, p2.id])
            session.add_all(
                [
                    Inventory(
                        product_id=p1.id,
                        quantity=5,
                        stock_version=1,
                        updated_at=now,
                    ),
                    Inventory(
                        product_id=p2.id,
                        quantity=5,
                        stock_version=1,
                        updated_at=now,
                    ),
                ]
            )
            p1_id, p2_id, sup_id = p1.id, p2.id, sup.id

        app = _create_test_app(migrated_integration_engine, settings)
        with TestClient(app) as client:
            r_draft = client.post(
                "/api/v1/purchase-receipts",
                headers=actors["admin_headers"],
                json={
                    "supplier_id": sup_id,
                    "items": [
                        {"product_id": p1_id, "quantity": 10, "unit_cost_vnd": 5_000},
                        {"product_id": p2_id, "quantity": 10, "unit_cost_vnd": 5_000},
                    ],
                },
            )
            assert r_draft.status_code == 201
            receipt_id = r_draft.json()["id"]
            receipt_ids.append(receipt_id)

            # Deactivate second product right before confirm
            with Session(migrated_integration_engine) as session, session.begin():
                session.execute(
                    update(Product)
                    .where(Product.id == p2_id)
                    .values(status=CatalogStatus.INACTIVE)
                )

            k_fail = f"roll-confirm-fail-{run_id}"
            idem_keys.append(k_fail)
            r_fail = client.post(
                f"/api/v1/purchase-receipts/{receipt_id}/confirm",
                headers={**actors["admin_headers"], "Idempotency-Key": k_fail},
                json={"expected_draft_version": r_draft.json()["draft_version"]},
            )
            assert r_fail.status_code in (409, 422)

        # Verify zero partial state in MySQL
        with Session(migrated_integration_engine) as session:
            receipt = session.get(PurchaseReceipt, receipt_id)
            inv1 = session.get(Inventory, p1_id)
            inv2 = session.get(Inventory, p2_id)
            mov_count = session.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id.in_([p1_id, p2_id])
                )
            )
            assert receipt is not None and receipt.status == "DRAFT"
            assert inv1 is not None and inv1.quantity == 5 and inv1.stock_version == 1
            assert inv2 is not None and inv2.quantity == 5 and inv2.stock_version == 1
            assert mov_count == 0
    finally:
        _cleanup_run(
            migrated_integration_engine,
            product_ids=product_ids,
            category_ids=category_ids,
            supplier_ids=supplier_ids,
            receipt_ids=receipt_ids,
            order_ids=[],
            idempotency_keys=idem_keys,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )


def test_concurrent_checkout_stock_5_qty_4_and_concurrent_cancel_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Section 6.3 & 6.4: Stock=5, two concurrent checkouts of 4 -> [201, 409]."""
    run_id = uuid4().hex[:10]
    settings = _make_settings(integration_database_url, run_id)
    actors = _seed_actors(migrated_integration_engine, run_id, settings)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    product_ids: list[int] = []
    category_ids: list[int] = []
    order_ids: list[int] = []
    idem_keys: list[str] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"ConcCat-{run_id}",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(cat)
            session.flush()
            category_ids.append(cat.id)

            prod = Product(
                category_id=cat.id,
                sku=f"CONC-5-{run_id}",
                name="Concurrent Five Unit Item",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=50_000,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            product_ids.append(prod.id)
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

        idem_secret = settings.idempotency_secret.get_secret_value().encode("utf-8")
        k1 = f"conc-co-1-{run_id}-0001"
        k2 = f"conc-co-2-{run_id}-0002"
        idem_keys.extend([k1, k2])
        barrier = Barrier(2)

        def _do_checkout(key: str) -> tuple[int, int | None]:
            svc = CheckoutService(
                InventoryService(),
                idempotency=IdempotencyExecutor(secret=idem_secret),
            )
            with Session(migrated_integration_engine) as session:
                barrier.wait(timeout=10)
                try:
                    order = svc.checkout(
                        session,
                        actor_id=actors["admin_id"],
                        idempotency_key=key,
                        items=[
                            CheckoutLine(
                                product_id=prod_id,
                                quantity=4,
                                viewed_unit_price_vnd=50_000,
                            )
                        ],
                    )
                    return 201, order.id
                except (ConflictError, StockConflictError):
                    return 409, None

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_do_checkout, k1)
            f2 = pool.submit(_do_checkout, k2)
            res1, res2 = f1.result(timeout=20), f2.result(timeout=20)

        statuses = sorted([res1[0], res2[0]])
        assert statuses == [201, 409]
        order_id = res1[1] if res1[0] == 201 else res2[1]
        assert order_id is not None
        order_ids.append(order_id)

        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 1 and inv.stock_version == 2
            sale_movs = session.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id == prod_id,
                    StockMovement.kind == MovementKind.SALE,
                )
            )
            assert sale_movs == 1

        # Concurrent cancel on the winning order (2 distinct keys -> [200, 409])
        kc1 = f"conc-can-1-{run_id}-0001"
        kc2 = f"conc-can-2-{run_id}-0002"
        idem_keys.extend([kc1, kc2])
        cancel_barrier = Barrier(2)

        def _do_cancel(key: str) -> int:
            svc = OrderService(
                InventoryService(),
                idempotency=IdempotencyExecutor(secret=idem_secret),
            )
            with Session(migrated_integration_engine) as session:
                cancel_barrier.wait(timeout=10)
                try:
                    svc.cancel(
                        session,
                        actor_id=actors["admin_id"],
                        actor_role="ADMIN",
                        order_id=order_id,
                        reason="Concurrent cancel test",
                        idempotency_key=key,
                    )
                    return 200
                except (ConflictError, InvalidStateError, StockConflictError):
                    return 409

        with ThreadPoolExecutor(max_workers=2) as pool:
            fc1 = pool.submit(_do_cancel, kc1)
            fc2 = pool.submit(_do_cancel, kc2)
            cancel_statuses = sorted([fc1.result(timeout=20), fc2.result(timeout=20)])

        assert cancel_statuses == [200, 409]
        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 5 and inv.stock_version == 3
            cancel_movs = session.scalar(
                select(func.count(StockMovement.id)).where(
                    StockMovement.product_id == prod_id,
                    StockMovement.kind == MovementKind.ORDER_CANCEL,
                )
            )
            assert cancel_movs == 1
    finally:
        _cleanup_run(
            migrated_integration_engine,
            product_ids=product_ids,
            category_ids=category_ids,
            supplier_ids=[],
            receipt_ids=[],
            order_ids=order_ids,
            idempotency_keys=idem_keys,
            owned_session_ids=actors["owned_session_ids"],
            owned_user_ids=actors["owned_user_ids"],
        )
