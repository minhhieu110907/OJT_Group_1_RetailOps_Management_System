"""Integration tests for POST /api/v1/inventory/{product_id}/adjustments (T04A758)."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import AuthSession, User, UserRole, UserStatus
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import AuthService
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import IdempotencyOperation
from app.modules.idempotency.validation import key_digest
from app.modules.inventory.models import (
    Inventory,
    InventoryAdjustment,
    MovementKind,
    Product,
    ProductStatus,
    StockMovement,
)
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_SKU_PREFIX = "T04A758-SKU-"
TEST_CAT_PREFIX = "T04A758_CAT_"
TEST_EMAIL_PREFIX = "t04a758_adj_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class _TrackedCleanup:
    def __init__(self) -> None:
        self.session_ids: list[bytes] = []
        self.idempotency_digests: list[bytes] = []
        self.user_ids: list[int] = []
        self.product_ids: list[int] = []
        self.category_ids: list[int] = []
        self.created_admin_id: int | None = None


@pytest.fixture
def tracked_cleanup(
    migrated_integration_engine: Engine,
) -> Generator[_TrackedCleanup]:
    """Clean up only rows created by this test.

    Never touches shared admin sessions or other tests' idempotency records.
    """
    tracker = _TrackedCleanup()
    _cleanup_prefixed_fixtures(migrated_integration_engine)
    try:
        yield tracker
    finally:
        _cleanup_tracked(migrated_integration_engine, tracker)
        _cleanup_prefixed_fixtures(migrated_integration_engine)


def _cleanup_prefixed_fixtures(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(
                    User.email_normalized.like(f"{TEST_EMAIL_PREFIX}%"),
                    User.admin_slot.is_(None),
                )
            )
        )
        if user_ids:
            session.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
            )

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

        if user_ids:
            session.execute(delete(User).where(User.id.in_(user_ids)))

        session.execute(
            delete(Category).where(Category.name.like(f"{TEST_CAT_PREFIX}%"))
        )


def _cleanup_tracked(engine: Engine, tracker: _TrackedCleanup) -> None:
    with Session(engine) as session, session.begin():
        if tracker.idempotency_digests:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.operation
                    == IdempotencyOperation.INVENTORY_ADJUSTMENT.value,
                    IdempotencyRecord.key_digest.in_(tracker.idempotency_digests),
                )
            )

        if tracker.session_ids:
            session.execute(
                delete(AuthSession).where(AuthSession.id.in_(tracker.session_ids))
            )

        if tracker.product_ids:
            session.execute(
                delete(StockMovement).where(
                    StockMovement.product_id.in_(tracker.product_ids)
                )
            )
            session.execute(
                delete(InventoryAdjustment).where(
                    InventoryAdjustment.product_id.in_(tracker.product_ids)
                )
            )
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(tracker.product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(tracker.product_ids)))

        if tracker.user_ids:
            session.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(tracker.user_ids))
            )
            session.execute(delete(User).where(User.id.in_(tracker.user_ids)))

        if tracker.created_admin_id is not None:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == tracker.created_admin_id
                )
            )
            session.execute(
                delete(AuthSession).where(
                    AuthSession.user_id == tracker.created_admin_id
                )
            )
            session.execute(delete(User).where(User.id == tracker.created_admin_id))

        if tracker.category_ids:
            session.execute(
                delete(Category).where(Category.id.in_(tracker.category_ids))
            )


def _make_test_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("t" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("s" * 32),
    )


class AdjustmentApiContext:
    def __init__(
        self,
        engine: Engine,
        app: Any,
        settings: Settings,
        tracker: _TrackedCleanup,
        admin_id: int,
        admin_headers: dict[str, str],
        staff_id: int,
        staff_headers: dict[str, str],
        product_id: int,
    ) -> None:
        self.engine = engine
        self.app = app
        self.settings = settings
        self.tracker = tracker
        self.admin_id = admin_id
        self.admin_headers = admin_headers
        self.staff_id = staff_id
        self.staff_headers = staff_headers
        self.product_id = product_id

    def track_key(self, idempotency_key: str) -> str:
        digest = self.key_digest_for(idempotency_key)
        if digest not in self.tracker.idempotency_digests:
            self.tracker.idempotency_digests.append(digest)
        return idempotency_key

    def key_digest_for(self, idempotency_key: str) -> bytes:
        # IdempotencyExecutor reads get_settings().require_idempotency_secret().
        return key_digest(idempotency_key, get_settings().require_idempotency_secret())


def _setup_test_context(
    engine: Engine,
    tracker: _TrackedCleanup,
    *,
    initial_quantity: int = 10,
    initial_version: int = 0,
) -> AdjustmentApiContext:
    now = datetime.now(UTC).replace(tzinfo=None)
    suffix = uuid4().hex[:8]
    settings = _make_test_settings()
    auth_srv = AuthService(settings, password_hasher=PasswordHasher(work_factor=4))

    admin_sid = uuid4()
    staff_sid = uuid4()
    session_expires = now + timedelta(hours=2)

    with Session(engine) as session:
        admin = session.scalar(select(User).where(User.admin_slot == 1))
        created_admin = False
        if admin is None:
            admin = User(
                email_normalized=f"{TEST_EMAIL_PREFIX}admin@example.com",
                password_hash="$2b$04$test.actor.hash",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()
            created_admin = True

        staff = User(
            email_normalized=f"{TEST_EMAIL_PREFIX}staff_{suffix}@example.com",
            password_hash="$2b$04$test.actor.hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        cat = Category(
            name=f"{TEST_CAT_PREFIX}{suffix}",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add_all((staff, cat))
        session.flush()

        prod = Product(
            sku=f"{TEST_SKU_PREFIX}{suffix}",
            name=f"Adjustment Test Product {suffix}",
            category_id=cat.id,
            status=ProductStatus.ACTIVE.value,
            sale_price_vnd=50_000,
            created_at=now,
            updated_at=now,
        )
        session.add(prod)
        session.flush()

        inv = Inventory(
            product_id=prod.id,
            quantity=initial_quantity,
            stock_version=initial_version,
            first_stocked_at=now,
            updated_at=now,
        )
        session.add(inv)

        session.add_all(
            [
                AuthSession(
                    id=admin_sid.bytes,
                    user_id=admin.id,
                    created_at=now,
                    expires_at=session_expires,
                    revoked_at=None,
                ),
                AuthSession(
                    id=staff_sid.bytes,
                    user_id=staff.id,
                    created_at=now,
                    expires_at=session_expires,
                    revoked_at=None,
                ),
            ]
        )
        session.commit()
        admin_id = admin.id
        staff_id = staff.id
        product_id = prod.id
        category_id = cat.id

    tracker.session_ids.extend([admin_sid.bytes, staff_sid.bytes])
    tracker.user_ids.append(staff_id)
    tracker.product_ids.append(product_id)
    tracker.category_ids.append(category_id)
    if created_admin:
        tracker.created_admin_id = admin_id

    admin_token, _ = auth_srv.jwt.issue(
        user_id=admin_id,
        session_id=admin_sid,
        session_expires_at=session_expires,
        now=now.replace(tzinfo=UTC),
    )
    staff_token, _ = auth_srv.jwt.issue(
        user_id=staff_id,
        session_id=staff_sid,
        session_expires_at=session_expires,
        now=now.replace(tzinfo=UTC),
    )

    app = create_app(settings)

    class UnavailableRedis:
        async def eval(self, *_args, **_kwargs):
            raise RedisError("test Redis outage")

    app.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_auth_service] = lambda: auth_srv

    def override_db() -> Generator[Session]:
        with Session(engine, expire_on_commit=False) as s:
            try:
                yield s
            except Exception:
                s.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_db

    return AdjustmentApiContext(
        engine=engine,
        app=app,
        settings=settings,
        tracker=tracker,
        admin_id=admin_id,
        admin_headers={"Authorization": f"Bearer {admin_token}"},
        staff_id=staff_id,
        staff_headers={"Authorization": f"Bearer {staff_token}"},
        product_id=product_id,
    )


@pytest.mark.anyio
async def test_admin_adjust_success_creates_movement_and_audit(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 1: Admin adjusts stock increase -> 200, creates movement and audit."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    idem_key = ctx.track_key("adj-key-success-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 15,
                "expected_stock_version": 0,
                "reason": "Thực tế kiểm đếm thừa 5 gói",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["product_id"] == ctx.product_id
        assert data["quantity"] == 15
        assert data["stock_version"] == 1
        assert data["movement_created"] is True
        audit_id = data["audit_id"]
        assert audit_id > 0

    # Direct database verification
    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 15
        assert inv.stock_version == 1

        audit = session.scalar(
            select(InventoryAdjustment).where(InventoryAdjustment.id == audit_id)
        )
        assert audit is not None
        assert audit.product_id == ctx.product_id
        assert audit.actor_id == ctx.admin_id
        assert audit.quantity_before == 10
        assert audit.counted_quantity == 15
        assert audit.version_before == 0
        assert audit.reason == "Thực tế kiểm đếm thừa 5 gói"

        movement = session.scalar(
            select(StockMovement).where(StockMovement.adjustment_id == audit_id)
        )
        assert movement is not None
        assert movement.product_id == ctx.product_id
        assert movement.actor_id == ctx.admin_id
        assert movement.kind == MovementKind.ADJUSTMENT.value
        assert movement.quantity_before == 10
        assert movement.quantity_after == 15
        assert movement.delta == 5
        assert movement.stock_version_after == 1


@pytest.mark.anyio
async def test_admin_adjust_decrease_success(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 2: Admin adjusts stock decrease -> 200, movement delta negative."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=1,
    )
    idem_key = ctx.track_key("adj-key-decrease-002")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 4,
                "expected_stock_version": 1,
                "reason": "Hao hụt rách bao bì",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quantity"] == 4
        assert data["stock_version"] == 2
        assert data["movement_created"] is True
        audit_id = data["audit_id"]

    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 4
        assert inv.stock_version == 2

        movement = session.scalar(
            select(StockMovement).where(StockMovement.adjustment_id == audit_id)
        )
        assert movement is not None
        assert movement.delta == -6
        assert movement.quantity_before == 10
        assert movement.quantity_after == 4
        assert movement.stock_version_after == 2


@pytest.mark.anyio
async def test_admin_adjust_no_op_audit_only(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 3: No-op adjustment (counted == current) -> 200, Audit only, no Movement."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=3,
    )
    idem_key = ctx.track_key("adj-key-noop-003")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 10,
                "expected_stock_version": 3,
                "reason": "Kiểm kê định kỳ không chênh lệch",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == ctx.product_id
        assert data["quantity"] == 10
        assert data["stock_version"] == 3
        assert data["movement_created"] is False
        audit_id = data["audit_id"]
        assert audit_id > 0

    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 10
        assert inv.stock_version == 3

        audit = session.scalar(
            select(InventoryAdjustment).where(InventoryAdjustment.id == audit_id)
        )
        assert audit is not None
        assert audit.quantity_before == 10
        assert audit.counted_quantity == 10

        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.adjustment_id == audit_id)
            )
        )
        assert len(movements) == 0


@pytest.mark.anyio
async def test_adjust_stale_stock_version_returns_409(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 4: Stale expected version -> 409 STALE_STOCK_VERSION, no writes."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=2,
    )
    idem_key = ctx.track_key("adj-key-stale-004")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 15,
                "expected_stock_version": 1,  # Stale, actual is 2
                "reason": "Kiểm kê sai version",
            },
        )
        assert resp.status_code == 409
        err = resp.json()
        assert err["code"] == "STALE_STOCK_VERSION"

    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 10
        assert inv.stock_version == 2

        audits = list(
            session.scalars(
                select(InventoryAdjustment).where(
                    InventoryAdjustment.product_id == ctx.product_id
                )
            )
        )
        assert len(audits) == 0


@pytest.mark.anyio
async def test_adjust_concurrent_same_expected_version_one_winner(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 5: Concurrent requests with same expected version -> 1 wins (200), 1 409."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    key_a = ctx.track_key("adj-conc-key-001a")
    key_b = ctx.track_key("adj-conc-key-002b")

    results: list[tuple[int, dict[str, Any]]] = []

    async def _send(counted: int, key: str) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
        ) as c:
            r = await c.post(
                f"/api/v1/inventory/{ctx.product_id}/adjustments",
                headers={**ctx.admin_headers, "Idempotency-Key": key},
                json={
                    "counted_quantity": counted,
                    "expected_stock_version": 0,
                    "reason": f"Concurrent count {counted}",
                },
            )
            results.append((r.status_code, r.json()))

    import anyio

    async with anyio.create_task_group() as tg:
        tg.start_soon(_send, 12, key_a)
        tg.start_soon(_send, 14, key_b)

    assert sorted(s for s, _ in results) == [200, 409]
    conflict_bodies = [body for status_code, body in results if status_code == 409]
    assert len(conflict_bodies) == 1
    assert conflict_bodies[0]["code"] in {"STALE_STOCK_VERSION", "STOCK_CONFLICT"}

    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.stock_version == 1
        assert inv.quantity in {12, 14}

        audits = list(
            session.scalars(
                select(InventoryAdjustment).where(
                    InventoryAdjustment.product_id == ctx.product_id
                )
            )
        )
        assert len(audits) == 1

        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.product_id == ctx.product_id)
            )
        )
        assert len(movements) == 1


@pytest.mark.anyio
async def test_adjust_rbac_permissions(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 6: ADMIN -> 200, STAFF -> 403, Unauthenticated -> 401."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    idem_key = ctx.track_key("adj-rbac-key-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        # 1. Anonymous -> 401
        anon_resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={"Idempotency-Key": idem_key},
            json={
                "counted_quantity": 12,
                "expected_stock_version": 0,
                "reason": "Anonymous attempt",
            },
        )
        assert anon_resp.status_code == 401
        assert anon_resp.json()["code"] == "UNAUTHENTICATED"

        # 2. Staff -> 403
        staff_resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.staff_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 12,
                "expected_stock_version": 0,
                "reason": "Staff attempt",
            },
        )
        assert staff_resp.status_code == 403
        assert staff_resp.json()["code"] == "FORBIDDEN"

        # 3. Admin -> 200
        admin_resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 12,
                "expected_stock_version": 0,
                "reason": "Admin authorized attempt",
            },
        )
        assert admin_resp.status_code == 200
        assert admin_resp.json()["quantity"] == 12


@pytest.mark.anyio
async def test_adjust_idempotency_replay_identical_response(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 7: Same Idempotency-Key + same payload replays identical 200 response."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    idem_key = ctx.track_key("adj-idem-replay-001")
    payload = {
        "counted_quantity": 18,
        "expected_stock_version": 0,
        "reason": "Replay test",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json=payload,
        )
        assert first.status_code == 200
        first_data = first.json()

        second = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json=payload,
        )
        assert second.status_code == 200
        second_data = second.json()

        assert first_data == second_data

    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 18
        assert inv.stock_version == 1

        audits = list(
            session.scalars(
                select(InventoryAdjustment).where(
                    InventoryAdjustment.product_id == ctx.product_id
                )
            )
        )
        assert len(audits) == 1

        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.product_id == ctx.product_id)
            )
        )
        assert len(movements) == 1


@pytest.mark.anyio
async def test_adjust_idempotency_different_payload_returns_409(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 8: Reused key with different payload returns 409 IDEMPOTENCY_KEY_REUSED."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    idem_key = ctx.track_key("adj-idem-conflict-002")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 18,
                "expected_stock_version": 0,
                "reason": "Original intent",
            },
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 25,  # Changed!
                "expected_stock_version": 0,
                "reason": "Different payload intent",
            },
        )
        assert second.status_code == 409
        assert second.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.anyio
async def test_adjust_validation_errors_return_422(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 9: Invalid request schemas and headers return 422 VALIDATION_ERROR."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=10,
        initial_version=0,
    )
    valid_key = ctx.track_key("adj-valid-key-42200")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        # Negative counted_quantity
        r_neg = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": valid_key},
            json={
                "counted_quantity": -1,
                "expected_stock_version": 0,
                "reason": "Reason",
            },
        )
        assert r_neg.status_code == 422
        assert r_neg.json()["code"] == "VALIDATION_ERROR"

        # Empty reason
        r_empty_reason = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": valid_key},
            json={
                "counted_quantity": 5,
                "expected_stock_version": 0,
                "reason": "   ",
            },
        )
        assert r_empty_reason.status_code == 422
        assert r_empty_reason.json()["code"] == "VALIDATION_ERROR"

        # Missing Idempotency-Key header
        r_no_key = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers=ctx.admin_headers,
            json={
                "counted_quantity": 5,
                "expected_stock_version": 0,
                "reason": "Valid reason",
            },
        )
        assert r_no_key.status_code == 422
        assert r_no_key.json()["code"] == "VALIDATION_ERROR"

        # Key too short (< 16 chars)
        r_short_key = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": "short-key"},
            json={
                "counted_quantity": 5,
                "expected_stock_version": 0,
                "reason": "Valid reason",
            },
        )
        assert r_short_key.status_code == 422
        assert r_short_key.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_adjust_nonexistent_product_returns_404(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 10: Nonexistent product_id -> 404 RESOURCE_NOT_FOUND."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key("adj-key-notfound-404")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/inventory/99999999/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 10,
                "expected_stock_version": 0,
                "reason": "Checking 404",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
async def test_adjust_transaction_atomicity_on_failure(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 11: Mid-transaction failure after partial writes rolls back atomically."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        initial_quantity=20,
        initial_version=5,
    )
    idem_key = ctx.track_key("adj-atomicity-fail-001")

    # Inject a failure AFTER IdempotencyRecord claim, InventoryAdjustment insert,
    # and Inventory balance update have been flushed to the MySQL transaction.
    from app.modules.inventory.repository import InventoryMovementRepository

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Simulated mid-transaction failure after partial writes")

    monkeypatch.setattr(InventoryMovementRepository, "add_movement", _boom)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            f"/api/v1/inventory/{ctx.product_id}/adjustments",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={
                "counted_quantity": 30,
                "expected_stock_version": 5,
                "reason": "Atomicity rollback test",
            },
        )
        assert resp.status_code == 500

    # Verify partial writes (Inventory, Audit, Movement, IdempotencyRecord) rolled back
    with Session(ctx.engine) as session:
        inv = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_id)
        )
        assert inv is not None
        assert inv.quantity == 20
        assert inv.stock_version == 5

        audits = list(
            session.scalars(
                select(InventoryAdjustment).where(
                    InventoryAdjustment.product_id == ctx.product_id
                )
            )
        )
        assert len(audits) == 0

        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.product_id == ctx.product_id)
            )
        )
        assert len(movements) == 0

        records = list(
            session.scalars(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation
                    == IdempotencyOperation.INVENTORY_ADJUSTMENT.value,
                    IdempotencyRecord.key_digest == ctx.key_digest_for(idem_key),
                )
            )
        )
        assert len(records) == 0
