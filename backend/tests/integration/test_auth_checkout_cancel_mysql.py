"""MySQL E2E & concurrency regression suite for Auth -> Checkout -> Cancel [T04A9CA]."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, InvalidStateError
from app.db.session import get_db_session
from app.infrastructure.dependencies import enforce_login_rate_limit, get_rate_limiter
from app.infrastructure.rate_limit import RateLimitResult
from app.main import create_app
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.security import JwtService, PasswordHasher
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import IdempotencyExecutor
from app.modules.inventory import InventoryService, StockConflictError
from app.modules.inventory.models import MovementKind, StockMovement
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService, OrderService
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration
__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class _NoopRateLimiter:
    async def check(self, **_kwargs: Any) -> RateLimitResult:
        return RateLimitResult(allowed=True, count=1, retry_after=60)


def _build_http_app(
    engine: Engine,
    database_url: Any,
    *,
    run_id: str,
):
    sf = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        environment="development",
        db_host=database_url.host or "127.0.0.1",
        db_port=database_url.port or 3306,
        db_name=database_url.database or "retailops_test",
        db_user=database_url.username or "retailops_test_runner",
        db_password=SecretStr(database_url.password or ""),
        jwt_secret=SecretStr(f"t04a9ca-jwt-secret-{run_id}-0123456789"),
        csrf_secret=SecretStr(f"t04a9ca-csrf-secret-{run_id}-0123456789"),
        idempotency_secret=SecretStr(f"t04a9ca-idem-secret-{run_id}-0123456789"),
        auth_cookie_secure=False,
    )
    app = create_app(settings)

    def _override_db():
        with sf() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_rate_limiter] = lambda: _NoopRateLimiter()
    app.dependency_overrides[enforce_login_rate_limit] = lambda: None
    return app, sf, settings


def _cleanup_run(
    engine: Engine,
    *,
    product_ids: tuple[int, ...],
    category_ids: tuple[int, ...],
    user_ids: tuple[int, ...],
) -> None:
    """Delete only exact records owned by this test run in strict FK order."""
    with Session(engine) as session, session.begin():
        order_ids: list[int] = []
        if user_ids:
            order_ids = list(
                session.scalars(select(Order.id).where(Order.created_by.in_(user_ids)))
            )
        if product_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
        if order_ids:
            session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            session.execute(delete(Order).where(Order.id.in_(order_ids)))
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))
        if category_ids:
            session.execute(delete(Category).where(Category.id.in_(category_ids)))
        if user_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.user_id.in_(user_ids))
            )
            sess_ids = list(
                session.scalars(
                    select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
                )
            )
            if sess_ids:
                session.execute(
                    delete(RefreshToken).where(RefreshToken.session_id.in_(sess_ids))
                )
                session.execute(delete(AuthSession).where(AuthSession.id.in_(sess_ids)))
            session.execute(delete(User).where(User.id.in_(user_ids)))


def _seed_users_and_product(
    engine: Engine,
    *,
    run_id: str,
    initial_stock: int,
    unit_price_vnd: int = 20_000,
) -> tuple[int, int, str, str, int, int]:
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    hasher = PasswordHasher(work_factor=4)
    pw = "RegressionPass!123"
    staff1_email = f"t04a9ca-s1-{run_id}@example.com"
    staff2_email = f"t04a9ca-s2-{run_id}@example.com"
    with Session(engine) as session, session.begin():
        s1 = User(
            email_normalized=staff1_email,
            password_hash=hasher.hash(pw),
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        s2 = User(
            email_normalized=staff2_email,
            password_hash=hasher.hash(pw),
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        cat = Category(
            name=f"T04A9CA-Cat-{run_id}",
            description="Regression category",
            status=CatalogStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add_all([s1, s2, cat])
        session.flush()
        prod = Product(
            category_id=cat.id,
            sku=f"T04A9CA-{run_id}",
            name=f"Regression Item {run_id}",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=unit_price_vnd,
            created_at=now,
            updated_at=now,
        )
        session.add(prod)
        session.flush()
        session.add(
            Inventory(
                product_id=prod.id,
                quantity=initial_stock,
                stock_version=1,
                first_stocked_at=now,
                updated_at=now,
            )
        )
        return s1.id, s2.id, staff1_email, staff2_email, cat.id, prod.id


def test_auth_checkout_cancel_lifecycle_rbac_and_invariants_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: Any,
) -> None:
    """Groups A, B, C: Auth 401/403/revocation, Checkout, Cancel, Replay, invariants."""
    run_id = uuid4().hex[:12]
    initial_stock = 10
    unit_price = 25_000
    s1_id, s2_id, s1_email, s2_email, cat_id, prod_id = _seed_users_and_product(
        migrated_integration_engine,
        run_id=run_id,
        initial_stock=initial_stock,
        unit_price_vnd=unit_price,
    )
    app, sf, settings = _build_http_app(
        migrated_integration_engine, integration_database_url, run_id=run_id
    )
    pw = "RegressionPass!123"

    try:
        with TestClient(app) as client:
            # A1. Unauthenticated & invalid token -> 401
            r_no_auth = client.post(
                "/api/v1/orders/checkout",
                headers={"Idempotency-Key": f"t04a9ca-noauth-{run_id}"},
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_no_auth.status_code == 401

            r_bad_tok = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": "Bearer invalid.jwt.token",
                    "Idempotency-Key": f"t04a9ca-badtok-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_bad_tok.status_code == 401

            # A2. Expired JWT -> 401
            expired_now = datetime.now(UTC) - timedelta(hours=1)
            expired_tok, _ = JwtService(settings).issue(
                user_id=s1_id,
                session_id=uuid4(),
                session_expires_at=expired_now + timedelta(minutes=5),
                now=expired_now,
            )
            r_exp = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {expired_tok}",
                    "Idempotency-Key": f"t04a9ca-exptok-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_exp.status_code == 401

            # Login Staff 1 and Staff 2
            l1 = client.post(
                "/api/v1/auth/login", json={"email": s1_email, "password": pw}
            )
            assert l1.status_code == 200
            s1_token = l1.json()["access_token"]
            csrf_resp = client.get(
                "/api/v1/auth/csrf",
                headers={"Authorization": f"Bearer {s1_token}"},
            )
            assert csrf_resp.status_code == 200
            s1_csrf = csrf_resp.json()["csrf_token"]

            with TestClient(app) as client2:
                l2 = client2.post(
                    "/api/v1/auth/login", json={"email": s2_email, "password": pw}
                )
                assert l2.status_code == 200
                s2_token = l2.json()["access_token"]

            # B1. Valid Checkout (qty=3) + Idempotency Replay + Conflict
            checkout_key = f"t04a9ca-chk-1-{run_id}"
            payload = {
                "items": [
                    {
                        "product_id": prod_id,
                        "quantity": 3,
                        "viewed_unit_price_vnd": unit_price,
                    }
                ]
            }
            r_chk = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": checkout_key,
                },
                json=payload,
            )
            assert r_chk.status_code == 201
            order_id = r_chk.json()["id"]
            assert r_chk.json()["status"] == OrderStatus.COMPLETED.value
            assert r_chk.json()["total_vnd"] == 3 * unit_price

            r_chk_replay = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": checkout_key,
                },
                json=payload,
            )
            assert r_chk_replay.status_code == 201
            assert r_chk_replay.json()["id"] == order_id

            r_chk_conflict = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": checkout_key,
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_chk_conflict.status_code == 409

            # B2. Insufficient stock -> 409, stock unchanged
            r_oversell = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": f"t04a9ca-oversell-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 999,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_oversell.status_code == 409

            # A3. Staff 2 cannot cancel Staff 1's order -> 403
            r_forbid_cancel = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                headers={
                    "Authorization": f"Bearer {s2_token}",
                    "Idempotency-Key": f"t04a9ca-forbid-{run_id}",
                },
                json={"reason": "Khong phai nguoi tao don"},
            )
            assert r_forbid_cancel.status_code == 403

            # C1. Staff 1 cancels own order -> 200 + replay 200 + new-key repeat 409
            cancel_key = f"t04a9ca-can-1-{run_id}"
            r_can = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": cancel_key,
                },
                json={"reason": "Khach doi y"},
            )
            assert r_can.status_code == 200
            assert r_can.json()["status"] == OrderStatus.CANCELLED.value

            r_can_replay = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": cancel_key,
                },
                json={"reason": "Khach doi y"},
            )
            assert r_can_replay.status_code == 200

            r_can_again = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": f"t04a9ca-can-2-{run_id}",
                },
                json={"reason": "Huy lan nua"},
            )
            assert r_can_again.status_code == 409

            # A4. Logout revokes session -> old access token rejected (401)
            r_logout = client.post(
                "/api/v1/auth/logout",
                headers={
                    "X-CSRF-Token": s1_csrf,
                    "Origin": settings.cors_origin_allowlist[0],
                },
            )
            assert r_logout.status_code == 204

            r_after_logout = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {s1_token}",
                    "Idempotency-Key": f"t04a9ca-revoked-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_after_logout.status_code == 401

        # Verify MySQL state & Stock Invariant directly
        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None
            assert inv.quantity == initial_stock  # 10 - 3 + 3 == 10
            assert inv.stock_version == 3  # initial(1) -> sale(2) -> cancel(3)

            movements = list(
                session.scalars(
                    select(StockMovement)
                    .where(
                        StockMovement.product_id == prod_id,
                        StockMovement.order_id == order_id,
                    )
                    .order_by(StockMovement.id)
                )
            )
            assert [(m.kind, m.delta) for m in movements] == [
                (MovementKind.SALE.value, -3),
                (MovementKind.ORDER_CANCEL.value, 3),
            ]
    finally:
        _cleanup_run(
            migrated_integration_engine,
            product_ids=(prod_id,),
            category_ids=(cat_id,),
            user_ids=(s1_id, s2_id),
        )


def test_checkout_and_cancel_concurrency_and_interaction_mysql(
    migrated_integration_engine: Engine,
    integration_database_url: Any,
) -> None:
    """Groups D, E, F: Concurrent checkout oversell guard, cancel once, interaction."""
    run_id = uuid4().hex[:12]
    unit_price = 30_000
    s1_id, s2_id, s1_email, s2_email, cat_id, prod_id = _seed_users_and_product(
        migrated_integration_engine,
        run_id=run_id,
        initial_stock=1,
        unit_price_vnd=unit_price,
    )
    app, _sf, settings = _build_http_app(
        migrated_integration_engine, integration_database_url, run_id=run_id
    )
    idem_secret = settings.idempotency_secret.get_secret_value().encode("utf-8")

    def _checkout_worker(barrier: threading.Barrier, actor_id: int, key: str) -> int:
        svc = CheckoutService(
            InventoryService(),
            idempotency=IdempotencyExecutor(secret=idem_secret),
        )
        with Session(migrated_integration_engine) as session:
            barrier.wait(timeout=5)
            try:
                svc.checkout(
                    session,
                    actor_id=actor_id,
                    idempotency_key=key,
                    items=[
                        CheckoutLine(
                            product_id=prod_id,
                            quantity=1,
                            viewed_unit_price_vnd=unit_price,
                        )
                    ],
                )
                return 201
            except (ConflictError, StockConflictError):
                return 409

    def _cancel_worker(
        barrier: threading.Barrier, actor_id: int, oid: int, key: str
    ) -> int:
        svc = OrderService(
            InventoryService(),
            idempotency=IdempotencyExecutor(secret=idem_secret),
        )
        with Session(migrated_integration_engine) as session:
            barrier.wait(timeout=5)
            try:
                svc.cancel(
                    session,
                    actor_id=actor_id,
                    actor_role="STAFF",
                    order_id=oid,
                    reason="Huy dong thoi",
                    idempotency_key=key,
                )
                return 200
            except (ConflictError, InvalidStateError, StockConflictError):
                return 409

    try:
        # Group D: Initial stock = 1, 2 concurrent checkouts (qty=1) -> 1x201, 1x409
        barrier_d = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_checkout_worker, barrier_d, s1_id, f"t04a9ca-d1-{run_id}")
            f2 = pool.submit(_checkout_worker, barrier_d, s2_id, f"t04a9ca-d2-{run_id}")
            statuses_d = sorted([f1.result(timeout=15), f2.result(timeout=15)])
        assert statuses_d == [201, 409]

        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 0
            winning_order = session.scalar(
                select(Order).where(Order.created_by.in_((s1_id, s2_id)))
            )
            assert winning_order is not None
            win_order_id = winning_order.id
            win_actor_id = winning_order.created_by

        # Group E: Two concurrent cancels for the same order -> 1x200, 1x409, stock = 1
        barrier_e = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            c1 = pool.submit(
                _cancel_worker,
                barrier_e,
                win_actor_id,
                win_order_id,
                f"t04a9ca-e1-{run_id}",
            )
            c2 = pool.submit(
                _cancel_worker,
                barrier_e,
                win_actor_id,
                win_order_id,
                f"t04a9ca-e2-{run_id}",
            )
            statuses_e = sorted([c1.result(timeout=15), c2.result(timeout=15)])
        assert statuses_e == [200, 409]

        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 1

        # Group F: Checkout + Cancel interaction on same product (stock 1 -> 0 -> race)
        with TestClient(app) as client:
            t1 = client.post(
                "/api/v1/auth/login",
                json={"email": s1_email, "password": "RegressionPass!123"},
            ).json()["access_token"]
            r_pre = client.post(
                "/api/v1/orders/checkout",
                headers={
                    "Authorization": f"Bearer {t1}",
                    "Idempotency-Key": f"t04a9ca-f0-{run_id}",
                },
                json={
                    "items": [
                        {
                            "product_id": prod_id,
                            "quantity": 1,
                            "viewed_unit_price_vnd": unit_price,
                        }
                    ]
                },
            )
            assert r_pre.status_code == 201
            pre_order_id = r_pre.json()["id"]

        # Stock is now 0; cancel pre_order (+1) concurrently with a checkout (-1)
        barrier_f = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fc = pool.submit(
                _cancel_worker, barrier_f, s1_id, pre_order_id, f"t04a9ca-fcan-{run_id}"
            )
            fk = pool.submit(
                _checkout_worker, barrier_f, s2_id, f"t04a9ca-fchk-{run_id}"
            )
            can_code = fc.result(timeout=15)
            chk_code = fk.result(timeout=15)

        assert can_code == 200
        assert chk_code in {201, 409}
        expected_final_stock = 0 if chk_code == 201 else 1
        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None
            assert inv.quantity == expected_final_stock
            assert inv.quantity >= 0
    finally:
        _cleanup_run(
            migrated_integration_engine,
            product_ids=(prod_id,),
            category_ids=(cat_id,),
            user_ids=(s1_id, s2_id),
        )
