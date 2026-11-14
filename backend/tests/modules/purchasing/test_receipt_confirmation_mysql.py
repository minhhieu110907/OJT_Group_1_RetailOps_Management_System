"""MySQL integration tests for Purchase Receipt confirmation (T04A7DF)."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import anyio
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
    MovementKind,
    Product,
    ProductStatus,
    StockMovement,
)
from app.modules.inventory.repository import InventoryMovementRepository
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.suppliers.models import Supplier, SupplierStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_SKU_PREFIX = "T04A7DF-SKU-"
TEST_CAT_PREFIX = "T04A7DF_CAT_"
TEST_SUP_PREFIX = "T04A7DF_SUP_"
TEST_EMAIL_PREFIX = "t04a7df_rc_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class _TrackedCleanup:
    def __init__(self) -> None:
        self.session_ids: list[bytes] = []
        self.idempotency_digests: list[bytes] = []
        self.receipt_ids: list[int] = []
        self.user_ids: list[int] = []
        self.product_ids: list[int] = []
        self.supplier_ids: list[int] = []
        self.category_ids: list[int] = []
        self.created_admin_id: int | None = None


@pytest.fixture
def tracked_cleanup(
    migrated_integration_engine: Engine,
) -> Generator[_TrackedCleanup]:
    """Clean up only rows created by this test."""
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
            receipt_ids = list(
                session.scalars(
                    select(PurchaseReceiptItem.receipt_id).where(
                        PurchaseReceiptItem.product_id.in_(product_ids)
                    )
                )
            )
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
            if receipt_ids:
                session.execute(
                    delete(PurchaseReceiptItem).where(
                        PurchaseReceiptItem.receipt_id.in_(receipt_ids)
                    )
                )
                session.execute(
                    delete(PurchaseReceipt).where(PurchaseReceipt.id.in_(receipt_ids))
                )
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        if user_ids:
            session.execute(delete(User).where(User.id.in_(user_ids)))

        session.execute(
            delete(Supplier).where(Supplier.name.like(f"{TEST_SUP_PREFIX}%"))
        )
        session.execute(
            delete(Category).where(Category.name.like(f"{TEST_CAT_PREFIX}%"))
        )


def _cleanup_tracked(engine: Engine, tracker: _TrackedCleanup) -> None:
    with Session(engine) as session, session.begin():
        if tracker.idempotency_digests:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.operation
                    == IdempotencyOperation.CONFIRM_RECEIPT.value,
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

        if tracker.receipt_ids:
            session.execute(
                delete(StockMovement).where(
                    StockMovement.receipt_id.in_(tracker.receipt_ids)
                )
            )
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id.in_(tracker.receipt_ids)
                )
            )
            session.execute(
                delete(PurchaseReceipt).where(
                    PurchaseReceipt.id.in_(tracker.receipt_ids)
                )
            )

        if tracker.product_ids:
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

        if tracker.supplier_ids:
            session.execute(
                delete(Supplier).where(Supplier.id.in_(tracker.supplier_ids))
            )

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


class ConfirmReceiptApiContext:
    def __init__(
        self,
        engine: Engine,
        app: Any,
        tracker: _TrackedCleanup,
        admin_id: int,
        admin_headers: dict[str, str],
        staff_id: int,
        staff_headers: dict[str, str],
        supplier_id: int,
        product_ids: list[int],
        receipt_id: int,
    ) -> None:
        self.engine = engine
        self.app = app
        self.tracker = tracker
        self.admin_id = admin_id
        self.admin_headers = admin_headers
        self.staff_id = staff_id
        self.staff_headers = staff_headers
        self.supplier_id = supplier_id
        self.product_ids = product_ids
        self.receipt_id = receipt_id

    def track_key(self, idempotency_key: str) -> str:
        digest = self.key_digest_for(idempotency_key)
        if digest not in self.tracker.idempotency_digests:
            self.tracker.idempotency_digests.append(digest)
        return idempotency_key

    def key_digest_for(self, idempotency_key: str) -> bytes:
        return key_digest(idempotency_key, get_settings().require_idempotency_secret())


def _setup_test_context(
    engine: Engine,
    tracker: _TrackedCleanup,
    *,
    lines: list[tuple[int, int, int]] | None = None,
    receipt_status: str = "DRAFT",
    draft_version: int = 1,
    supplier_status: str = SupplierStatus.ACTIVE.value,
    second_product_status: str = ProductStatus.ACTIVE.value,
) -> ConfirmReceiptApiContext:
    """Seed supplier, 2 products + inventories, and a purchase receipt.

    ``lines`` defaults to [(initial_qty=0, receipt_qty=5, unit_cost=20_000),
    (initial_qty=10, receipt_qty=3, unit_cost=40_000)].
    """
    if lines is None:
        lines = [(0, 5, 20_000), (10, 3, 40_000)]

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
        sup = Supplier(
            name=f"{TEST_SUP_PREFIX}{suffix}",
            contact_phone=f"+8490{uuid4().int % 10_000_000:07d}",
            status=supplier_status,
            created_at=now,
            updated_at=now,
        )
        session.add_all((staff, cat, sup))
        session.flush()

        products: list[Product] = []
        for idx, (init_qty, _rcpt_qty, _cost) in enumerate(lines):
            prod_status = (
                second_product_status if idx == 1 else ProductStatus.ACTIVE.value
            )
            prod = Product(
                sku=f"{TEST_SKU_PREFIX}{suffix}-{idx}",
                name=f"Confirm Test Product {suffix} #{idx}",
                category_id=cat.id,
                status=prod_status,
                sale_price_vnd=50_000,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            products.append(prod)

            inv = Inventory(
                product_id=prod.id,
                quantity=init_qty,
                stock_version=0,
                first_stocked_at=now if init_qty > 0 else None,
                updated_at=now,
            )
            session.add(inv)

        total_vnd = sum(rcpt_qty * cost for _, rcpt_qty, cost in lines)
        is_closed = receipt_status in {"CONFIRMED", "CANCELLED"}
        receipt = PurchaseReceipt(
            supplier_id=sup.id,
            supplier_name_snapshot=sup.name,
            status=receipt_status,
            draft_version=draft_version,
            total_vnd=total_vnd,
            created_by=admin.id,
            closed_by=admin.id if is_closed else None,
            created_at=now,
            updated_at=now,
            closed_at=now if is_closed else None,
        )
        session.add(receipt)
        session.flush()

        for prod, (_init_qty, rcpt_qty, cost) in zip(products, lines, strict=True):
            item = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=prod.id,
                sku_snapshot=prod.sku,
                product_name_snapshot=prod.name,
                quantity=rcpt_qty,
                unit_cost_vnd=cost,
                line_total_vnd=rcpt_qty * cost,
            )
            session.add(item)

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
        supplier_id = sup.id
        category_id = cat.id
        product_ids = [p.id for p in products]
        receipt_id = receipt.id

    tracker.session_ids.extend([admin_sid.bytes, staff_sid.bytes])
    tracker.user_ids.append(staff_id)
    tracker.supplier_ids.append(supplier_id)
    tracker.category_ids.append(category_id)
    tracker.product_ids.extend(product_ids)
    tracker.receipt_ids.append(receipt_id)
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
        async def eval(self, *_args: object, **_kwargs: object) -> object:
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

    return ConfirmReceiptApiContext(
        engine=engine,
        app=app,
        tracker=tracker,
        admin_id=admin_id,
        admin_headers={"Authorization": f"Bearer {admin_token}"},
        staff_id=staff_id,
        staff_headers={"Authorization": f"Bearer {staff_token}"},
        supplier_id=supplier_id,
        product_ids=product_ids,
        receipt_id=receipt_id,
    )


@pytest.mark.anyio
async def test_admin_confirm_draft_receipt_success(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Tests 1-5: Confirm DRAFT -> CONFIRMED, stock & versions & movements updated."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key("rc-confirm-success-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == ctx.receipt_id
        assert data["status"] == "CONFIRMED"
        assert data["draft_version"] == 2
        assert data["closed_by"] == ctx.admin_id
        assert data["closed_at"] is not None
        assert data["total_vnd"] == 5 * 20_000 + 3 * 40_000
        assert len(data["items"]) == 2

        # Confirmed receipt is immutable: cannot PATCH or CANCEL
        patch_resp = await client.patch(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}",
            headers=ctx.admin_headers,
            json={"expected_draft_version": 2, "supplier_id": ctx.supplier_id},
        )
        assert patch_resp.status_code == 409

        cancel_resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/cancel",
            headers=ctx.admin_headers,
            json={"expected_draft_version": 2},
        )
        assert cancel_resp.status_code == 409

    with Session(ctx.engine) as session:
        p0, p1 = ctx.product_ids
        inv0 = session.scalar(select(Inventory).where(Inventory.product_id == p0))
        inv1 = session.scalar(select(Inventory).where(Inventory.product_id == p1))
        assert inv0 is not None and inv1 is not None
        assert inv0.quantity == 5
        assert inv0.stock_version == 1
        assert inv0.first_stocked_at is not None  # set from None -> positive
        assert inv1.quantity == 13
        assert inv1.stock_version == 1

        movements = list(
            session.scalars(
                select(StockMovement)
                .where(StockMovement.receipt_id == ctx.receipt_id)
                .order_by(StockMovement.product_id.asc())
            )
        )
        assert len(movements) == 2
        assert movements[0].product_id == p0
        assert movements[0].kind == MovementKind.PURCHASE_CONFIRM.value
        assert movements[0].quantity_before == 0
        assert movements[0].quantity_after == 5
        assert movements[0].delta == 5
        assert movements[0].stock_version_after == 1

        assert movements[1].product_id == p1
        assert movements[1].kind == MovementKind.PURCHASE_CONFIRM.value
        assert movements[1].quantity_before == 10
        assert movements[1].quantity_after == 13
        assert movements[1].delta == 3
        assert movements[1].stock_version_after == 1


@pytest.mark.anyio
async def test_confirm_rbac_staff_and_unauthenticated(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Tests 6-7: STAFF -> 403 FORBIDDEN, Unauthenticated -> 401 UNAUTHENTICATED."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key("rc-confirm-rbac-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        anon_resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={"Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert anon_resp.status_code == 401
        assert anon_resp.json()["code"] == "UNAUTHENTICATED"

        staff_resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.staff_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert staff_resp.status_code == 403
        assert staff_resp.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_confirm_nonexistent_receipt_returns_404(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 8: Nonexistent receipt_id -> 404 RESOURCE_NOT_FOUND."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key("rc-confirm-404-0001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/purchase-receipts/99999999/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
@pytest.mark.parametrize("status_name", ["CONFIRMED", "CANCELLED"])
async def test_confirm_already_closed_receipt_rejected(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
    status_name: str,
) -> None:
    """Tests 9-10: Receipt already CONFIRMED or CANCELLED -> 409 INVALID_STATE."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        receipt_status=status_name,
        draft_version=2,
    )
    idem_key = ctx.track_key(f"rc-closed-{status_name.lower()}-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 2},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_STATE"


@pytest.mark.anyio
async def test_confirm_stale_version_returns_409(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 11: Stale expected_draft_version -> 409 RECEIPT_VERSION_CONFLICT."""
    ctx = _setup_test_context(
        migrated_integration_engine, tracked_cleanup, draft_version=3
    )
    idem_key = ctx.track_key("rc-confirm-stale-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 2},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "RECEIPT_VERSION_CONFLICT"


@pytest.mark.anyio
async def test_confirm_inactive_supplier_rejected(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 12: INACTIVE supplier -> 409 INVALID_STATE, no inventory change."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        supplier_status=SupplierStatus.INACTIVE.value,
    )
    idem_key = ctx.track_key("rc-confirm-sup-inactive-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_STATE"

    with Session(ctx.engine) as session:
        receipt = session.get(PurchaseReceipt, ctx.receipt_id)
        assert receipt is not None and receipt.status == "DRAFT"
        inv0 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[0])
        )
        assert inv0 is not None and inv0.quantity == 0


@pytest.mark.anyio
async def test_confirm_inactive_product_rejected(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 13: INACTIVE product -> 409 INVALID_STATE, no inventory change."""
    ctx = _setup_test_context(
        migrated_integration_engine,
        tracked_cleanup,
        second_product_status=ProductStatus.INACTIVE.value,
    )
    idem_key = ctx.track_key("rc-confirm-prod-inactive-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "INVALID_STATE"

    with Session(ctx.engine) as session:
        receipt = session.get(PurchaseReceipt, ctx.receipt_id)
        assert receipt is not None and receipt.status == "DRAFT"
        inv0 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[0])
        )
        assert inv0 is not None and inv0.quantity == 0


@pytest.mark.anyio
async def test_confirm_idempotency_replay_and_conflict(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Tests 14-15: Retry replays 200 without double stock; different payload -> 409."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key("rc-confirm-idem-001")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert first.status_code == 200

        replay = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert replay.status_code == 200
        assert replay.json() == first.json()

        conflict = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 2},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    with Session(ctx.engine) as session:
        inv0 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[0])
        )
        assert inv0 is not None and inv0.quantity == 5
        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.receipt_id == ctx.receipt_id)
            )
        )
        assert len(movements) == 2

        idem_rec = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation
                == IdempotencyOperation.CONFIRM_RECEIPT.value,
                IdempotencyRecord.key_digest == ctx.key_digest_for(idem_key),
            )
        )
        assert idem_rec is not None
        assert idem_rec.completed_at is not None
        assert idem_rec.expires_at is not None
        assert idem_rec.expires_at - idem_rec.completed_at == timedelta(hours=24)


@pytest.mark.anyio
async def test_confirm_concurrent_requests_single_winner(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
) -> None:
    """Test 16: Two concurrent confirm requests -> 1 wins (200), 1 409, no duplicate."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    key_a = ctx.track_key("rc-confirm-conc-001a")
    key_b = ctx.track_key("rc-confirm-conc-002b")

    results: list[tuple[int, dict[str, Any]]] = []

    async def _send(key: str) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=ctx.app), base_url="http://test"
        ) as c:
            r = await c.post(
                f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
                headers={**ctx.admin_headers, "Idempotency-Key": key},
                json={"expected_draft_version": 1},
            )
            results.append((r.status_code, r.json()))

    async with anyio.create_task_group() as tg:
        tg.start_soon(_send, key_a)
        tg.start_soon(_send, key_b)

    assert sorted(s for s, _ in results) == [200, 409]
    conflicts = [body for s, body in results if s == 409]
    assert conflicts[0]["code"] == "RECEIPT_VERSION_CONFLICT"

    with Session(ctx.engine) as session:
        inv0 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[0])
        )
        inv1 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[1])
        )
        assert inv0 is not None and inv0.quantity == 5
        assert inv1 is not None and inv1.quantity == 13
        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.receipt_id == ctx.receipt_id)
            )
        )
        assert len(movements) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure_stage",
    ["inventory_update", "stock_movement", "commit_idempotency"],
)
async def test_confirm_rollback_on_mid_transaction_failure(
    migrated_integration_engine: Engine,
    tracked_cleanup: _TrackedCleanup,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    """Tests 17-20: Failure at inventory, movement, or commit rolls back everything."""
    ctx = _setup_test_context(migrated_integration_engine, tracked_cleanup)
    idem_key = ctx.track_key(f"rc-confirm-rb-{failure_stage}")

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError(f"Simulated failure at {failure_stage}")

    if failure_stage == "inventory_update":
        monkeypatch.setattr(
            InventoryMovementRepository, "guarded_update_balance", _boom
        )
    elif failure_stage == "stock_movement":
        monkeypatch.setattr(InventoryMovementRepository, "add_movement", _boom)
    else:
        monkeypatch.setattr("app.modules.purchasing.router.commit_session", _boom)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ctx.app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            f"/api/v1/purchase-receipts/{ctx.receipt_id}/confirm",
            headers={**ctx.admin_headers, "Idempotency-Key": idem_key},
            json={"expected_draft_version": 1},
        )
        assert resp.status_code == 500

    with Session(ctx.engine) as session:
        receipt = session.get(PurchaseReceipt, ctx.receipt_id)
        assert receipt is not None
        assert receipt.status == "DRAFT"
        assert receipt.draft_version == 1
        assert receipt.closed_by is None
        assert receipt.closed_at is None

        inv0 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[0])
        )
        inv1 = session.scalar(
            select(Inventory).where(Inventory.product_id == ctx.product_ids[1])
        )
        assert inv0 is not None and inv0.quantity == 0 and inv0.stock_version == 0
        assert inv1 is not None and inv1.quantity == 10 and inv1.stock_version == 0

        movements = list(
            session.scalars(
                select(StockMovement).where(StockMovement.receipt_id == ctx.receipt_id)
            )
        )
        assert len(movements) == 0

        records = list(
            session.scalars(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.operation
                    == IdempotencyOperation.CONFIRM_RECEIPT.value,
                    IdempotencyRecord.key_digest == ctx.key_digest_for(idem_key),
                )
            )
        )
        assert len(records) == 0
