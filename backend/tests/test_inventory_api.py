"""Unit and API integration tests for Inventory query endpoints, RBAC, and filters."""

from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category, CategoryStatus
from app.modules.products.models import CatalogStatus, Inventory, Product

ORIGIN = "http://127.0.0.1:5173"


def make_test_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def make_principal(role: UserRole, is_active: bool = True) -> CurrentPrincipal:
    now = datetime(2026, 11, 11, 10, 0)
    user = User(
        id=1 if role == UserRole.ADMIN else 2,
        email_normalized=f"{role.value.lower()}@example.com",
        password_hash="hashed",
        role=role.value,
        status=(
            UserStatus.ACTIVE.value if is_active else UserStatus.PENDING_APPROVAL.value
        ),
        admin_slot=1 if role == UserRole.ADMIN else None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    return CurrentPrincipal(user=user, session_id=uuid4())


def _build_sqlite_inventory_session() -> Session:
    """Build an in-memory SQLite session with inventory test data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_conn: object, _record: object) -> None:
        conn = dbapi_conn  # type: ignore[assignment]
        conn.create_collation(  # type: ignore[attr-defined]
            "ascii_bin", lambda a, b: (a > b) - (a < b)
        )

    Category.__table__.create(engine)
    Product.__table__.create(engine)
    Inventory.__table__.create(engine)

    session = Session(engine)
    now = datetime(2026, 11, 11, 8, 0, 0)

    cat_drink = Category(
        id=1,
        name="Đồ uống",
        status=CategoryStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    cat_snack = Category(
        id=2,
        name="Bánh kẹo",
        status=CategoryStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add_all([cat_drink, cat_snack])

    t1 = datetime(2026, 11, 11, 9, 0, 0)
    t2 = datetime(2026, 11, 11, 9, 5, 0)

    # 4 Products:
    # P1: cat 1, ACTIVE, qty=25, stock_version=2, first_stocked_at=t1
    # P2: cat 1, ACTIVE, qty=0, stock_version=0, first_stocked_at=None
    # P3: cat 2, ACTIVE, qty=10, stock_version=1, first_stocked_at=t2
    # P4: cat 2, INACTIVE, qty=0, stock_version=0, first_stocked_at=None
    products_data = [
        (
            1,
            1,
            "SKU-P1",
            "Cà phê Robusta",
            CatalogStatus.ACTIVE.value,
            45_000,
            25,
            2,
            t1,
        ),
        (
            2,
            1,
            "SKU-P2",
            "Cà phê Arabica",
            CatalogStatus.ACTIVE.value,
            65_000,
            0,
            0,
            None,
        ),
        (3, 2, "SKU-P3", "Bánh quy bơ", CatalogStatus.ACTIVE.value, 30_000, 10, 1, t2),
        (
            4,
            2,
            "SKU-P4",
            "Kẹo dẻo ngừng bán",
            CatalogStatus.INACTIVE.value,
            15_000,
            0,
            0,
            None,
        ),
    ]

    for p_id, cat_id, sku, name, st, sale_p, qty, stock_v, first_st in products_data:
        p = Product(
            id=p_id,
            category_id=cat_id,
            sku=sku,
            name=name,
            status=st,
            sale_price_vnd=sale_p,
            created_at=now,
            updated_at=now,
        )
        inv = Inventory(
            product_id=p_id,
            quantity=qty,
            stock_version=stock_v,
            first_stocked_at=first_st,
            updated_at=now,
        )
        session.add_all([p, inv])

    session.commit()
    return session


@pytest.fixture
def db_session() -> Session:
    return _build_sqlite_inventory_session()


@pytest.fixture
def app(db_session: Session) -> object:
    settings = make_test_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: db_session
    return application


@pytest.mark.anyio
async def test_list_inventory_default_pagination(app: object) -> None:
    """Test GET /api/v1/inventory returns all records ordered by product_id ASC."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 4

    # Verify order by product.id ASC
    ids = [item["product_id"] for item in body["items"]]
    assert ids == [1, 2, 3, 4]


@pytest.mark.anyio
async def test_list_inventory_pagination_limit_offset(app: object) -> None:
    """Test pagination bounds: page_size=2, page=2."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory?page=2&page_size=2")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 4
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    assert [item["product_id"] for item in body["items"]] == [3, 4]


@pytest.mark.anyio
async def test_list_inventory_filter_category(app: object) -> None:
    """Test filtering by category_id."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory?category_id=1")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert all(item["category_id"] == 1 for item in body["items"])
    assert [item["product_id"] for item in body["items"]] == [1, 2]


@pytest.mark.anyio
async def test_list_inventory_filter_status(app: object) -> None:
    """Test filtering by status (ACTIVE vs INACTIVE)."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_active = await client.get("/api/v1/inventory?status=ACTIVE")
        res_inactive = await client.get("/api/v1/inventory?status=INACTIVE")

    assert res_active.status_code == 200
    body_active = res_active.json()
    assert body_active["total"] == 3
    assert [item["product_id"] for item in body_active["items"]] == [1, 2, 3]

    assert res_inactive.status_code == 200
    body_inactive = res_inactive.json()
    assert body_inactive["total"] == 1
    assert [item["product_id"] for item in body_inactive["items"]] == [4]


@pytest.mark.anyio
async def test_list_inventory_filter_in_stock(app: object) -> None:
    """Test filtering in_stock=true (qty > 0) vs in_stock=false (qty == 0)."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_in = await client.get("/api/v1/inventory?in_stock=true")
        res_out = await client.get("/api/v1/inventory?in_stock=false")

    assert res_in.status_code == 200
    body_in = res_in.json()
    assert body_in["total"] == 2
    assert [item["product_id"] for item in body_in["items"]] == [1, 3]
    assert all(item["quantity"] > 0 for item in body_in["items"])

    assert res_out.status_code == 200
    body_out = res_out.json()
    assert body_out["total"] == 2
    assert [item["product_id"] for item in body_out["items"]] == [2, 4]
    assert all(item["quantity"] == 0 for item in body_out["items"])


@pytest.mark.anyio
async def test_get_inventory_detail_success(app: object) -> None:
    """Test GET /api/v1/inventory/{product_id} returns accurate inventory record."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory/1")

    assert res.status_code == 200
    data = res.json()
    assert data["product_id"] == 1
    assert data["sku"] == "SKU-P1"
    assert data["name"] == "Cà phê Robusta"
    assert data["category_id"] == 1
    assert data["status"] == "ACTIVE"
    assert data["quantity"] == 25
    assert data["stock_version"] == 2
    assert data["first_stocked_at"] is not None


@pytest.mark.anyio
async def test_get_inventory_detail_404_not_found(app: object) -> None:
    """Test GET /api/v1/inventory/{product_id} with nonexistent ID returns 404."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory/9999")

    assert res.status_code == 404
    body = res.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "query_params",
    [
        "?page=0",
        "?page=-1",
        "?page_size=0",
        "?page_size=101",
        "?category_id=0",
        "?category_id=-2",
        "?status=DELETED",
    ],
)
async def test_list_inventory_validation_errors(app: object, query_params: str) -> None:
    """Test 422 for invalid query parameters on list inventory."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/inventory{query_params}")

    assert res.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_id", ["0", "-1", "abc"])
async def test_get_inventory_invalid_path_param_422(
    app: object, invalid_id: str
) -> None:
    """Test 422 when product_id path parameter is <= 0 or non-integer."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/inventory/{invalid_id}")

    assert res.status_code == 422


@pytest.mark.anyio
async def test_inventory_security_rbac_unauthenticated(app: object) -> None:
    """Test 401 when no token is provided."""
    application = app  # type: ignore[assignment]
    # No principal override -> UnauthenticatedError from get_current_principal

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get("/api/v1/inventory")
        res2 = await client.get("/api/v1/inventory/1")

    assert res1.status_code == 401
    assert res2.status_code == 401


@pytest.mark.anyio
async def test_inventory_security_rbac_inactive_user(app: object) -> None:
    """Test 403 when user is INACTIVE."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF, is_active=False
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory")

    assert res.status_code == 403


@pytest.mark.anyio
async def test_inventory_both_admin_and_staff_allowed(app: object) -> None:
    """Test both active ADMIN and STAFF can read inventory."""
    application = app  # type: ignore[assignment]
    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]

    # Admin
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_admin = await client.get("/api/v1/inventory")
    assert res_admin.status_code == 200

    # Staff
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_staff = await client.get("/api/v1/inventory")
    assert res_staff.status_code == 200


@pytest.mark.anyio
async def test_inventory_never_exposes_price_fields(app: object) -> None:
    """Test security invariant: responses NEVER expose internal price fields."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_list = await client.get("/api/v1/inventory")
        res_detail = await client.get("/api/v1/inventory/1")

    forbidden_fields = {
        "cost_price",
        "cost_price_vnd",
        "unit_cost_vnd",
        "sale_price_vnd",
    }

    list_data = res_list.json()
    for item in list_data["items"]:
        assert not any(field in item for field in forbidden_fields)

    detail_data = res_detail.json()
    assert not any(field in detail_data for field in forbidden_fields)
