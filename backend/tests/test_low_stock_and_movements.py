"""Integration and contract tests for Low-Stock alerts and Stock-Movement history."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category, CategoryStatus
from app.modules.inventory.repository import InventoryQueryRepository
from app.modules.inventory.router import get_inventory_service
from app.modules.inventory.service import InventoryQueryService
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
    now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
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


def _build_sqlite_session() -> Session:
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

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS inventory_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    actor_id INTEGER NOT NULL,
                    reason VARCHAR(500) NOT NULL,
                    quantity_before INTEGER NOT NULL,
                    counted_quantity INTEGER NOT NULL,
                    version_before INTEGER NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    actor_id INTEGER NOT NULL,
                    kind VARCHAR(16) NOT NULL,
                    receipt_id INTEGER,
                    order_id INTEGER,
                    adjustment_id INTEGER,
                    sku_snapshot VARCHAR(64) NOT NULL,
                    quantity_before INTEGER NOT NULL,
                    quantity_after INTEGER NOT NULL,
                    stock_version_after INTEGER NOT NULL,
                    occurred_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.commit()

    session = Session(engine)
    now = datetime(2026, 11, 11, 8, 0, 0)

    category = Category(
        id=1,
        name="Đồ uống",
        status=CategoryStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add(category)

    # Setup 6 Products for low-stock testing:
    # P1: ACTIVE, qty=3 (low stock)
    # P2: ACTIVE, qty=0 (low stock, zero)
    # P3: ACTIVE, qty=5 (low stock, exact boundary P0=5)
    # P4: ACTIVE, qty=6 (sufficient stock, excluded)
    # P5: INACTIVE, qty=2 (inactive, MUST be excluded even if qty <= 5)
    # P6: ACTIVE, qty=0 (tie breaker with P2 on qty=0)
    products_setup = [
        (1, "SKU-001", "Cà phê Sữa", CatalogStatus.ACTIVE.value, 3),
        (2, "SKU-002", "Trà Xanh", CatalogStatus.ACTIVE.value, 0),
        (3, "SKU-003", "Trà Đào", CatalogStatus.ACTIVE.value, 5),
        (4, "SKU-004", "Nước Suối", CatalogStatus.ACTIVE.value, 6),
        (5, "SKU-005", "Trà Ô Long", CatalogStatus.INACTIVE.value, 2),
        (6, "SKU-006", "Cà phê Đen", CatalogStatus.ACTIVE.value, 0),
    ]

    for p_id, sku, name, st, qty in products_setup:
        p = Product(
            id=p_id,
            category_id=1,
            sku=sku,
            name=name,
            status=st,
            sale_price_vnd=30_000,
            created_at=now,
            updated_at=now,
        )
        inv = Inventory(
            product_id=p_id,
            quantity=qty,
            stock_version=1,
            first_stocked_at=now,
            updated_at=now,
        )
        session.add_all([p, inv])

    session.commit()
    return session


@pytest.fixture
def db_session() -> Session:
    return _build_sqlite_session()


@pytest.fixture
def app(db_session: Session) -> object:
    settings = make_test_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: db_session
    return application


# ---------------------------------------------------------------------------
# Low-Stock API Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_low_stock_filters_active_and_threshold_and_sorting(app: object) -> None:
    """Test low-stock returns active products <= 5 sorted by qty ASC, id ASC."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory/low-stock")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 4
    assert body["page"] == 1
    assert body["page_size"] == 20

    items = body["items"]
    assert len(items) == 4

    # Verify order: qty=0 (id=2, id=6), qty=3 (id=1), qty=5 (id=3)
    assert items[0]["product_id"] == 2
    assert items[0]["quantity"] == 0
    assert items[0]["threshold"] == 5

    assert items[1]["product_id"] == 6
    assert items[1]["quantity"] == 0

    assert items[2]["product_id"] == 1
    assert items[2]["quantity"] == 3

    assert items[3]["product_id"] == 3
    assert items[3]["quantity"] == 5

    # Verify P4 (qty=6) and P5 (inactive, qty=2) are excluded
    product_ids = [item["product_id"] for item in items]
    assert 4 not in product_ids
    assert 5 not in product_ids

    # Verify no cost or sale price leaked
    for item in items:
        assert "cost_price" not in item
        assert "sale_price_vnd" not in item
        assert "unit_cost_vnd" not in item


@pytest.mark.anyio
async def test_low_stock_route_precedence_no_422(app: object) -> None:
    """Verify route precedence: /inventory/low-stock does not match /{product_id}."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory/low-stock")

    assert res.status_code == 200
    assert "items" in res.json()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "query,expected_status",
    [
        ("?page=0", 422),
        ("?page=-1", 422),
        ("?page_size=0", 422),
        ("?page_size=101", 422),
    ],
)
async def test_low_stock_pagination_validation(
    app: object, query: str, expected_status: int
) -> None:
    """Verify validation on invalid pagination parameters."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/inventory/low-stock{query}")

    assert res.status_code == expected_status


@pytest.mark.anyio
async def test_low_stock_fixed_p0_threshold(app: object) -> None:
    """Test fixed P0=5 threshold in OpenAPI contract (threshold param ignored)."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Extra query params like threshold=10 are ignored by route, fixed to 5
        res = await client.get("/api/v1/inventory/low-stock?threshold=10")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 4
    product_ids = [item["product_id"] for item in body["items"]]
    assert 4 not in product_ids  # P4 (qty=6) is excluded
    assert 5 not in product_ids  # P5 (inactive) is excluded

    # Verify each item returns the fixed threshold 5
    for item in body["items"]:
        assert item["threshold"] == 5


@pytest.mark.anyio
async def test_low_stock_pagination_slicing(app: object) -> None:
    """Test pagination slices results correctly."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_p1 = await client.get("/api/v1/inventory/low-stock?page=1&page_size=2")
        res_p2 = await client.get("/api/v1/inventory/low-stock?page=2&page_size=2")

    assert res_p1.status_code == 200
    b1 = res_p1.json()
    assert b1["total"] == 4
    assert len(b1["items"]) == 2
    assert [i["product_id"] for i in b1["items"]] == [2, 6]

    assert res_p2.status_code == 200
    b2 = res_p2.json()
    assert b2["total"] == 4
    assert len(b2["items"]) == 2
    assert [i["product_id"] for i in b2["items"]] == [1, 3]


@pytest.mark.anyio
async def test_low_stock_auth_guards(app: object) -> None:
    """Verify unauthenticated returns 401 and inactive returns 403."""
    application = app  # type: ignore[assignment]

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    # Unauthenticated
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/inventory/low-stock")
    assert res.status_code == 401

    # Inactive
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF, is_active=False
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_inactive = await client.get("/api/v1/inventory/low-stock")
    assert res_inactive.status_code == 403


# ---------------------------------------------------------------------------
# Stock-Movements API Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stock_movements_empty_ledger_returns_empty_page(app: object) -> None:
    """Verify movements endpoint returns empty page when ledger has no rows."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stock-movements")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["page"] == 1
    assert body["page_size"] == 20


@pytest.mark.anyio
async def test_stock_movements_missing_table_fails_closed_without_fake_success(
    app: object, db_session: Session
) -> None:
    """Verify missing table fails closed with 500 error instead of false 200 success."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    # Drop the table to simulate unmigrated dependency or database failure
    db_session.execute(text("DROP TABLE stock_movements"))
    db_session.commit()

    transport = httpx.ASGITransport(
        app=application,
        raise_app_exceptions=False,  # type: ignore[arg-type]
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stock-movements")

    # MUST NOT return 200 with empty items (no silent fallback)
    assert res.status_code == 500
    body = res.json()
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    # MUST NOT leak raw SQL or table names to the client
    assert "stock_movements" not in str(body).lower()
    assert "syntax" not in str(body).lower()


@pytest.mark.anyio
async def test_stock_movements_real_db_queries_and_role_projection(
    app: object, db_session: Session
) -> None:
    """Verify real SQL query without mocks correctly projects STAFF vs ADMIN data."""
    application = app  # type: ignore[assignment]

    # Insert real adjustments and movements into SQLite tables
    now_str = "2026-11-11 10:30:00"
    db_session.execute(
        text(
            """
            INSERT INTO inventory_adjustments (
                id, product_id, actor_id, reason, quantity_before,
                counted_quantity, version_before, created_at
            )
            VALUES (1, 2, 12, 'Hao hụt kiểm kê cuối tháng', 5, 0, 1, :created_at)
            """
        ),
        {"created_at": now_str},
    )
    db_session.execute(
        text(
            """
            INSERT INTO stock_movements (
                id, product_id, actor_id, kind, receipt_id, order_id,
                adjustment_id, sku_snapshot, quantity_before, quantity_after,
                stock_version_after, occurred_at
            )
            VALUES
                (1, 1, 10, 'PURCHASE_CONFIRM', 101, NULL, NULL,
                 'SKU-001', 0, 20, 1, '2026-11-11 08:00:00'),
                (2, 1, 10, 'SALE', NULL, 202, NULL,
                 'SKU-001', 20, 15, 2, '2026-11-11 09:00:00'),
                (3, 2, 12, 'ADJUSTMENT', NULL, NULL, 1,
                 'SKU-002', 5, 0, 2, '2026-11-11 10:30:00')
            """
        )
    )
    db_session.commit()

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]

    # 1. STAFF check: only public fields, no actor_id or adjustment_reason
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_staff = await client.get("/api/v1/stock-movements")

    assert res_staff.status_code == 200
    b_staff = res_staff.json()
    assert b_staff["total"] == 3
    assert len(b_staff["items"]) == 3
    # Check ordering by occurred_at DESC, id DESC -> id 3, 2, 1
    assert [i["id"] for i in b_staff["items"]] == [3, 2, 1]

    for item in b_staff["items"]:
        assert "actor_id" not in item
        assert "adjustment_reason" not in item
        assert "unit_cost_vnd" not in item
        assert "cost_price" not in item
        assert "sale_price_vnd" not in item
        assert item["occurred_at"].endswith("Z")

    # 2. ADMIN check: includes actor_id and adjustment_reason
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_admin = await client.get("/api/v1/stock-movements")

    assert res_admin.status_code == 200
    b_admin = res_admin.json()
    adj_item = b_admin["items"][0]
    assert adj_item["id"] == 3
    assert adj_item["actor_id"] == 12
    assert adj_item["adjustment_reason"] == "Hao hụt kiểm kê cuối tháng"
    assert adj_item["reference_id"] == 1
    assert adj_item["occurred_at"].endswith("Z")

    # 3. Real filter by product_id
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_filt_p = await client.get("/api/v1/stock-movements?product_id=2")
    assert res_filt_p.status_code == 200
    assert res_filt_p.json()["total"] == 1
    assert res_filt_p.json()["items"][0]["product_id"] == 2

    # 4. Real filter by kind
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_filt_k = await client.get("/api/v1/stock-movements?kind=SALE")
    assert res_filt_k.status_code == 200
    assert res_filt_k.json()["total"] == 1
    assert res_filt_k.json()["items"][0]["kind"] == "SALE"


def _sample_movements() -> list[dict[str, Any]]:
    now = datetime(2026, 11, 11, 10, 30, 0)
    return [
        {
            "id": 1,
            "product_id": 1,
            "sku": "SKU-001",
            "kind": "PURCHASE_CONFIRM",
            "quantity_before": 0,
            "quantity_after": 20,
            "stock_version_after": 1,
            "reference_id": 101,
            "occurred_at": now,
            "actor_id": 10,
            "adjustment_reason": None,
        },
        {
            "id": 2,
            "product_id": 1,
            "sku": "SKU-001",
            "kind": "SALE",
            "quantity_before": 20,
            "quantity_after": 15,
            "stock_version_after": 2,
            "reference_id": 202,
            "occurred_at": now,
            "actor_id": 10,
            "adjustment_reason": None,
        },
        {
            "id": 3,
            "product_id": 2,
            "sku": "SKU-002",
            "kind": "ADJUSTMENT",
            "quantity_before": 5,
            "quantity_after": 0,
            "stock_version_after": 2,
            "reference_id": 303,
            "occurred_at": now,
            "actor_id": 12,
            "adjustment_reason": "Hao hụt kiểm kê cuối tháng",
        },
    ]


def _fake_movement_provider(
    session: Session,
    page: int,
    page_size: int,
    product_id: int | None = None,
    kind: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items = _sample_movements()
    if product_id is not None:
        items = [i for i in items if i["product_id"] == product_id]
    if kind is not None:
        items = [i for i in items if i["kind"] == kind]

    total = len(items)
    offset = (page - 1) * page_size
    sliced = items[offset : offset + page_size]
    return sliced, total


@pytest.mark.anyio
async def test_stock_movements_staff_projection_hides_audit_fields(app: object) -> None:
    """Verify STAFF receives StockMovementPage with no actor_id or adjustment_reason."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    repo = InventoryQueryRepository(movement_provider=_fake_movement_provider)
    application.dependency_overrides[get_inventory_service] = lambda: (
        InventoryQueryService(repository=repo)
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stock-movements")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    for item in body["items"]:
        # Staff MUST have standard public movement fields
        assert "id" in item
        assert "product_id" in item
        assert "sku" in item
        assert "kind" in item
        assert "quantity_before" in item
        assert "quantity_after" in item
        assert "stock_version_after" in item
        assert "reference_id" in item
        assert "occurred_at" in item
        assert item["occurred_at"].endswith("Z")

        # Staff MUST NOT have audited actor_id or adjustment_reason
        assert "actor_id" not in item
        assert "adjustment_reason" not in item

        # Staff MUST NOT have cost or sale prices
        assert "unit_cost_vnd" not in item
        assert "cost_price" not in item
        assert "sale_price_vnd" not in item


@pytest.mark.anyio
async def test_stock_movements_admin_projection_includes_audit_fields(
    app: object,
) -> None:
    """Verify ADMIN receives StockMovementAdminPage with actor_id and reason."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    repo = InventoryQueryRepository(movement_provider=_fake_movement_provider)
    application.dependency_overrides[get_inventory_service] = lambda: (
        InventoryQueryService(repository=repo)
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stock-movements")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    adj_item = next(i for i in body["items"] if i["kind"] == "ADJUSTMENT")
    assert adj_item["actor_id"] == 12
    assert adj_item["adjustment_reason"] == "Hao hụt kiểm kê cuối tháng"
    assert adj_item["occurred_at"].endswith("Z")

    # Strictly no cost prices even for admin
    for item in body["items"]:
        assert "unit_cost_vnd" not in item
        assert "cost_price" not in item
        assert "sale_price_vnd" not in item


@pytest.mark.anyio
async def test_stock_movements_query_filters(app: object) -> None:
    """Test filtering by product_id and kind."""
    application = app  # type: ignore[assignment]
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    repo = InventoryQueryRepository(movement_provider=_fake_movement_provider)
    application.dependency_overrides[get_inventory_service] = lambda: (
        InventoryQueryService(repository=repo)
    )

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Filter by product_id
        res_p = await client.get("/api/v1/stock-movements?product_id=2")
        assert res_p.status_code == 200
        assert res_p.json()["total"] == 1
        assert res_p.json()["items"][0]["product_id"] == 2

        # Filter by kind
        res_k = await client.get("/api/v1/stock-movements?kind=SALE")
        assert res_k.status_code == 200
        assert res_k.json()["total"] == 1
        assert res_k.json()["items"][0]["kind"] == "SALE"

        # Invalid kind enum
        res_inv = await client.get("/api/v1/stock-movements?kind=INVALID_KIND")
        assert res_inv.status_code == 422


@pytest.mark.anyio
async def test_stock_movements_auth_guards(app: object) -> None:
    """Verify unauthenticated (401) and inactive (403) access guards."""
    application = app  # type: ignore[assignment]

    transport = httpx.ASGITransport(app=application)  # type: ignore[arg-type]
    # Unauthenticated
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/stock-movements")
    assert res.status_code == 401

    # Inactive
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN, is_active=False
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_inactive = await client.get("/api/v1/stock-movements")
    assert res_inactive.status_code == 403
