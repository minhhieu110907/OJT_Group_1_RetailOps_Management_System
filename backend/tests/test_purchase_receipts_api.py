"""API tests for Purchase Receipt endpoints, RBAC, and error contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.suppliers.models import Supplier, SupplierStatus
from sqlalchemy import BigInteger, event
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.compiler import compiles

ORIGIN = "http://127.0.0.1:5173"


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


def test_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def make_principal(role: UserRole) -> CurrentPrincipal:
    now = datetime(2026, 11, 7, 10, 0)
    user = User(
        id=1 if role == UserRole.ADMIN else 2,
        email_normalized=f"{role.value.lower()}@example.com",
        password_hash="hashed",
        role=role.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=1 if role == UserRole.ADMIN else None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    return CurrentPrincipal(user=user, session_id=uuid4())


def build_test_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Supplier.__table__,
            Product.__table__,
            Inventory.__table__,
            PurchaseReceipt.__table__,
            PurchaseReceiptItem.__table__,
        ],
    )
    with Session(engine) as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        admin_user = User(
            id=1,
            email_normalized="admin@example.com",
            password_hash="hashed",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        staff_user = User(
            id=2,
            email_normalized="staff@example.com",
            password_hash="hashed",
            role=UserRole.STAFF.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        category = Category(
            id=1,
            name="Đồ gia dụng",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        supplier = Supplier(
            id=1,
            name="Nhà cung cấp Hòa Phát",
            contact_email="hoaphat@example.com",
            contact_phone="0901234567",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        prod1 = Product(
            id=1,
            category_id=1,
            sku="SKU-CHAO-01",
            name="Chảo chống dính 26cm",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=150_000,
            created_at=now,
            updated_at=now,
        )
        prod2 = Product(
            id=2,
            category_id=1,
            sku="SKU-NOI-01",
            name="Nồi inox 20cm",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=200_000,
            created_at=now,
            updated_at=now,
        )
        session.add_all([admin_user, staff_user, category, supplier, prod1, prod2])
        session.commit()
    return engine


def build_app(role: UserRole | None, engine):
    app = create_app(test_settings())
    app.dependency_overrides[get_settings] = test_settings

    def _get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = _get_db

    if role is not None:
        principal = make_principal(role)
        app.dependency_overrides[get_current_principal] = lambda: principal

    return app


@pytest.mark.anyio
async def test_purchase_receipts_unauthenticated_returns_401():
    engine = build_test_db()
    app = build_app(None, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 1, "unit_cost_vnd": 10000}
                ],
            },
        )
        assert r1.status_code == 401

        r2 = await client.patch(
            "/api/v1/purchase-receipts/1",
            json={"expected_draft_version": 1},
        )
        assert r2.status_code == 401

        r3 = await client.get("/api/v1/purchase-receipts/1")
        assert r3.status_code == 401


@pytest.mark.anyio
async def test_purchase_receipts_by_staff_returns_403():
    engine = build_test_db()
    app = build_app(UserRole.STAFF, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 1, "unit_cost_vnd": 10000}
                ],
            },
        )
        assert r1.status_code == 403

        r2 = await client.patch(
            "/api/v1/purchase-receipts/1",
            json={"expected_draft_version": 1},
        )
        assert r2.status_code == 403

        r3 = await client.get("/api/v1/purchase-receipts/1")
        assert r3.status_code == 403


@pytest.mark.anyio
async def test_create_purchase_receipt_by_admin_success_201():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 3, "unit_cost_vnd": 50000},
                    {"product_id": 2, "quantity": 2, "unit_cost_vnd": 80000},
                    {"product_id": 1, "quantity": 2, "unit_cost_vnd": 50000},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "DRAFT"
        assert data["draft_version"] == 1
        assert data["supplier_id"] == 1
        assert len(data["items"]) == 2

        # 3 + 2 = 5 for prod 1
        it1 = next(it for it in data["items"] if it["product_id"] == 1)
        assert it1["quantity"] == 5
        assert it1["unit_cost_vnd"] == 50000
        assert it1["line_total_vnd"] == 250000

        it2 = next(it for it in data["items"] if it["product_id"] == 2)
        assert it2["quantity"] == 2
        assert it2["unit_cost_vnd"] == 80000
        assert it2["line_total_vnd"] == 160000

        assert data["total_vnd"] == 410000


@pytest.mark.anyio
async def test_create_purchase_receipt_cost_conflict_returns_409():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 3, "unit_cost_vnd": 50000},
                    {"product_id": 1, "quantity": 2, "unit_cost_vnd": 60000},
                ],
            },
        )
        assert resp.status_code == 409
        err = resp.json()
        assert err["code"] == "RECEIPT_ITEM_COST_CONFLICT"


@pytest.mark.anyio
async def test_create_purchase_receipt_extra_fields_returns_422():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "extra_field": "unauthorized",
                "items": [
                    {"product_id": 1, "quantity": 1, "unit_cost_vnd": 50000}
                ],
            },
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_purchase_receipt_empty_items_returns_422():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [],
            },
        )
        assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_purchase_receipt_by_admin_success_200():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 1, "unit_cost_vnd": 50000}
                ],
            },
        )
        assert create_resp.status_code == 201
        receipt_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/purchase-receipts/{receipt_id}",
            json={
                "expected_draft_version": 1,
                "items": [
                    {"product_id": 2, "quantity": 3, "unit_cost_vnd": 90000}
                ],
            },
        )
        assert update_resp.status_code == 200
        updated_data = update_resp.json()
        assert updated_data["draft_version"] == 2
        assert updated_data["total_vnd"] == 270000
        assert len(updated_data["items"]) == 1
        assert updated_data["items"][0]["product_id"] == 2


@pytest.mark.anyio
async def test_update_purchase_receipt_stale_version_returns_409():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 1, "unit_cost_vnd": 50000}
                ],
            },
        )
        receipt_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/v1/purchase-receipts/{receipt_id}",
            json={
                "expected_draft_version": 99,
            },
        )
        assert update_resp.status_code == 409
        err = update_resp.json()
        assert err["code"] == "RECEIPT_VERSION_CONFLICT"


@pytest.mark.anyio
async def test_get_purchase_receipt_by_admin_200():
    engine = build_test_db()
    app = build_app(UserRole.ADMIN, engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/v1/purchase-receipts",
            json={
                "supplier_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 2, "unit_cost_vnd": 30000}
                ],
            },
        )
        receipt_id = create_resp.json()["id"]

        get_resp = await client.get(f"/api/v1/purchase-receipts/{receipt_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == receipt_id
