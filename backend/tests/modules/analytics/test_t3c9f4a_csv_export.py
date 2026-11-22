"""Test suite for T3C9F4A — [Bonus] CSV Report Export.

Verifies:
1. Core CSV export helper: CWE-1236 Formula Injection sanitization, UTF-8 BOM, limit.
2. Auth & RBAC: 401 unauthenticated, 403 staff, 200 admin for all 3 endpoints.
3. Content & formatting invariants: headers, line items flattening, cost exclusion.
4. Validation & error envelopes: 422 for invalid date ranges or exceeding 5000 records.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Response
from pydantic import SecretStr
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.csv_export import (
    MAX_EXPORT_ROWS,
    check_export_limit,
    generate_csv_response,
    sanitize_csv_cell,
)
from app.core.exceptions import DomainValidationError, UnauthenticatedError
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.analytics.repository import SalesAnalyticsRepository
from app.modules.analytics.router import get_sales_analytics_service
from app.modules.analytics.service import SalesAnalyticsService
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.router import get_inventory_service
from app.modules.inventory.service import InventoryQueryService
from app.modules.products.models import Inventory, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from app.modules.sales.router import get_order_read_service
from app.modules.sales.service import OrderQuery, OrderReadService

VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "INTEGER"


def _make_sqlite_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_collation(dbapi_conn: Any, _conn_record: Any) -> None:
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))
        dbapi_conn.create_function("CHAR_LENGTH", 1, len)

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Product.__table__,
            Inventory.__table__,
            Order.__table__,
            OrderItem.__table__,
        ],
    )
    return Session(bind=engine, autoflush=False, expire_on_commit=False)


# ==============================================================================
# 1. CORE HELPER UNIT TESTS
# ==============================================================================


def test_sanitize_csv_cell_formula_injection() -> None:
    """CWE-1236: Formula trigger characters must be prepended with a single quote."""
    # Direct formula prefixes
    assert sanitize_csv_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_csv_cell("+cmd|'/c calc'!A0") == "'+cmd|'/c calc'!A0"
    assert sanitize_csv_cell("-1+1") == "'-1+1"
    assert sanitize_csv_cell("@evil_site") == "'@evil_site"
    assert sanitize_csv_cell("\tDDE_CALL") == "'\tDDE_CALL"
    assert sanitize_csv_cell("\rMALICIOUS") == "'\rMALICIOUS"

    # Leading whitespace before trigger character
    assert sanitize_csv_cell("   =2+2") == "'   =2+2"
    assert sanitize_csv_cell(" \t -calc") == "' \t -calc"

    # Normal strings without trigger prefixes should remain untouched
    assert sanitize_csv_cell("Sản phẩm số 1") == "Sản phẩm số 1"
    assert sanitize_csv_cell("SKU-12345") == "SKU-12345"
    assert sanitize_csv_cell("admin@example.com") == "admin@example.com"

    # None and numbers
    assert sanitize_csv_cell(None) == ""
    assert sanitize_csv_cell(123) == 123
    assert sanitize_csv_cell(45.67) == 45.67


def test_check_export_limit() -> None:
    """check_export_limit passes <= 5000 and raises DomainValidationError on > 5000."""
    check_export_limit(0)
    check_export_limit(100)
    check_export_limit(MAX_EXPORT_ROWS)

    with pytest.raises(DomainValidationError) as exc_info:
        check_export_limit(5001)
    assert "vượt quá giới hạn xuất tối đa 5000" in exc_info.value.message


def test_generate_csv_response_headers_and_bom() -> None:
    """generate_csv_response outputs UTF-8 BOM, CRLF, and proper HTTP headers."""
    headers = ["Cột 1", "Cột 2"]
    rows = [["=Nguy hiểm", "An toàn"], [100, None]]
    filename = "test_report.csv"

    res = generate_csv_response(headers, rows, filename)
    assert isinstance(res, Response)
    assert res.media_type == "text/csv; charset=utf-8"
    disp = res.headers["Content-Disposition"]
    assert disp == 'attachment; filename="test_report.csv"'
    assert res.headers["Cache-Control"] == "no-store"

    # Check UTF-8 BOM bytes (\xef\xbb\xbf)
    body_bytes = res.body
    assert body_bytes.startswith(b"\xef\xbb\xbf")

    # Decode and check CRLF row lines
    text_content = body_bytes.decode("utf-8")
    assert "\ufeff" in text_content
    lines = text_content.split("\r\n")
    assert lines[0] == "\ufeffCột 1,Cột 2"
    assert lines[1] == "'=Nguy hiểm,An toàn"
    assert lines[2] == "100,"


# ==============================================================================
# 2. TEST APP FIXTURES & RBAC
# ==============================================================================


def make_test_app(
    *,
    authenticated: bool = True,
    user_status: str = "ACTIVE",
    user_role: str = "ADMIN",
    order_service: object | None = None,
    analytics_service: object | None = None,
    inventory_service: object | None = None,
) -> FastAPI:
    config = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("i" * 32),
    )
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_db_session] = lambda: MagicMock()

    mock_auth_service = MagicMock()
    mock_auth_service.live_user.side_effect = UnauthenticatedError()
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    if order_service is not None:
        app.dependency_overrides[get_order_read_service] = lambda: order_service
    if analytics_service is not None:
        app.dependency_overrides[get_sales_analytics_service] = lambda: (
            analytics_service
        )
    if inventory_service is not None:
        app.dependency_overrides[get_inventory_service] = lambda: inventory_service

    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1,
                email_normalized="admin@example.com",
                password_hash="hash",
                role=user_role,
                status=user_status,
                admin_slot=1 if user_role == "ADMIN" else None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 14),
                updated_at=datetime(2026, 11, 14),
            ),
            session_id=uuid4(),
        )
    return app


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/orders/export/csv",
        "/api/v1/analytics/sales/daily/export/csv",
        "/api/v1/inventory/export/csv",
    ],
)
async def test_csv_export_unauthenticated_returns_401(endpoint: str) -> None:
    """All CSV export endpoints return 401 when caller is unauthenticated."""
    app = make_test_app(authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(endpoint)
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/orders/export/csv",
        "/api/v1/analytics/sales/daily/export/csv",
        "/api/v1/inventory/export/csv",
    ],
)
async def test_csv_export_staff_returns_403(endpoint: str) -> None:
    """STAFF role is rejected with 403 Forbidden on all export endpoints."""
    app = make_test_app(
        authenticated=True,
        user_role=UserRole.STAFF,
        user_status=UserStatus.ACTIVE,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(endpoint)
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/orders/export/csv",
        "/api/v1/analytics/sales/daily/export/csv",
        "/api/v1/inventory/export/csv",
    ],
)
async def test_csv_export_inactive_admin_returns_403(endpoint: str) -> None:
    """PENDING_APPROVAL or REJECTED admin accounts return 403 Forbidden."""
    app = make_test_app(
        authenticated=True,
        user_role=UserRole.ADMIN,
        user_status=UserStatus.PENDING_APPROVAL,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(endpoint)
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


# ==============================================================================
# 3. ORDERS CSV EXPORT TESTS
# ==============================================================================


class FakeOrderRepo:
    def __init__(
        self,
        orders: list[Any],
        total: int,
        export_rows_count: int | None = None,
    ) -> None:
        self.orders = orders
        self.total = total
        self.export_rows_count = (
            export_rows_count
            if export_rows_count is not None
            else sum(len(o.items) if getattr(o, "items", None) else 1 for o in orders)
        )
        self.last_filters: dict[str, Any] = {}
        self.list_orders_called = False

    def count_export_rows(
        self,
        session: object,
        *,
        status: str | None = None,
        sold_from_utc: datetime | None = None,
        sold_to_utc_exclusive: datetime | None = None,
        order_id_exact: int | None = None,
        sku_search: str | None = None,
    ) -> int:
        return self.export_rows_count

    def list_orders(
        self,
        session: object,
        *,
        status: str | None = None,
        sold_from_utc: datetime | None = None,
        sold_to_utc_exclusive: datetime | None = None,
        order_id_exact: int | None = None,
        sku_search: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Any], int]:
        self.list_orders_called = True
        self.last_filters = {
            "status": status,
            "sold_from_utc": sold_from_utc,
            "sold_to_utc_exclusive": sold_to_utc_exclusive,
            "order_id_exact": order_id_exact,
            "sku_search": sku_search,
            "offset": offset,
            "limit": limit,
        }
        return self.orders, self.total


class DummyItem:
    def __init__(
        self,
        sku: str,
        name: str,
        quantity: int,
        unit_price: int,
        line_total: int,
    ) -> None:
        self.sku_snapshot = sku
        self.product_name_snapshot = name
        self.quantity = quantity
        self.unit_price_vnd = unit_price
        self.line_total_vnd = line_total


class DummyCreator:
    def __init__(self, full_name: str, role: str = "ADMIN") -> None:
        self.full_name = full_name
        self.role = role


class DummyOrder:
    def __init__(
        self,
        id_: int,
        sold_at: datetime,
        status: str,
        total_vnd: int,
        creator_name: str,
        items: list[DummyItem],
        cancel_reason: str | None = None,
        creator_role: str = "ADMIN",
    ) -> None:
        self.id = id_
        self.sold_at = sold_at
        self.status = status
        self.total_vnd = total_vnd
        self.creator = DummyCreator(creator_name, role=creator_role)
        self.created_by = 1
        self.items = items
        self.cancel_reason = cancel_reason


@pytest.mark.anyio
async def test_orders_csv_export_content_and_flattening() -> None:
    """Orders CSV correctly flattens multi-line items and formats dates."""
    order1 = DummyOrder(
        id_=101,
        sold_at=datetime(2026, 11, 15, 3, 30, 0),  # UTC -> 10:30 VN
        status=OrderStatus.COMPLETED.value,
        total_vnd=300_000,
        creator_name="Admin User",
        creator_role="ADMIN",
        items=[
            DummyItem("SKU-001", "Cà phê Robusta", 2, 100_000, 200_000),
            DummyItem("=SKU-002", "+Trà sữa Oolong", 1, 100_000, 100_000),
        ],
    )
    order2 = DummyOrder(
        id_=102,
        sold_at=datetime(2026, 11, 15, 4, 0, 0),  # UTC -> 11:00 VN
        status=OrderStatus.CANCELLED.value,
        total_vnd=50_000,
        creator_name="Staff User",
        creator_role="STAFF",
        items=[DummyItem("SKU-003", "Bánh mì pate", 1, 50_000, 50_000)],
        cancel_reason="Khách đổi ý",
    )

    fake_repo = FakeOrderRepo([order1, order2], total=2)
    order_service = OrderReadService(repository=fake_repo)  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, order_service=order_service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/export/csv")

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Content-Disposition" in res.headers
    assert res.headers["Cache-Control"] == "no-store"

    content = res.content.decode("utf-8")
    lines = content.strip().split("\r\n")

    # Header check
    assert lines[0] == (
        "\ufeffMã đơn,Ngày bán (VN),Trạng thái,SKU,Tên sản phẩm,Số lượng,"
        "Đơn giá (VNĐ),Thành tiền (VNĐ),Tổng đơn (VNĐ),Người tạo,Lý do hủy"
    )

    # Order 1 Line 1
    exp_l1 = (
        "101,2026-11-15 10:30:00,COMPLETED,SKU-001,Cà phê Robusta,2,"
        "100000,200000,300000,Admin User (Admin),"
    )
    assert exp_l1 in lines[1]

    # Order 1 Line 2 (sanitized formulas)
    exp_l2 = (
        "101,2026-11-15 10:30:00,COMPLETED,'=SKU-002,'+Trà sữa Oolong,1,"
        "100000,100000,300000,Admin User (Admin),"
    )
    assert exp_l2 in lines[2]

    # Order 2 Line 1 (cancelled with reason)
    exp_l3 = (
        "102,2026-11-15 11:00:00,CANCELLED,SKU-003,Bánh mì pate,1,"
        "50000,50000,50000,Staff User,Khách đổi ý"
    )
    assert exp_l3 in lines[3]


@pytest.mark.anyio
async def test_orders_csv_export_exceeding_limit_returns_422() -> None:
    """Orders CSV returns 422 when matching count > 5000."""
    fake_repo = FakeOrderRepo([], total=5001, export_rows_count=5001)
    order_service = OrderReadService(repository=fake_repo)  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, order_service=order_service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/orders/export/csv")

    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"
    assert "5001" in res.json()["message"]


@pytest.mark.anyio
async def test_orders_csv_export_invalid_date_range_returns_422() -> None:
    """Orders CSV returns 422 when from_date > to_date."""
    app = make_test_app(authenticated=True, order_service=OrderReadService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/orders/export/csv?from_date=2026-11-20&to_date=2026-11-10"
        )
    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"


# ==============================================================================
# 4. DAILY SALES ANALYTICS CSV EXPORT TESTS
# ==============================================================================


class FakeAnalyticsRepo:
    def __init__(self, daily_summaries: list[dict[str, Any]]) -> None:
        self.daily_summaries = daily_summaries

    def get_daily_sales_summary(
        self,
        session: object,
        *,
        start_utc: datetime,
        end_utc_exclusive: datetime,
    ) -> list[dict[str, Any]]:
        return self.daily_summaries


@pytest.mark.anyio
async def test_daily_sales_csv_export_grouping_and_cancellation() -> None:
    """Daily sales CSV groups by VN date, excludes cancelled orders from revenue."""
    fake_summaries = [
        {
            "vn_date": "2026-11-15",
            "revenue_vnd": 100_000,
            "completed_orders": 1,
            "cancelled_orders": 1,
        },
        {
            "vn_date": "2026-11-16",
            "revenue_vnd": 200_000,
            "completed_orders": 1,
            "cancelled_orders": 0,
        },
    ]

    fake_repo = FakeAnalyticsRepo(fake_summaries)
    service = SalesAnalyticsService(repository=fake_repo)  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, analytics_service=service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/analytics/sales/daily/export/csv?from=2026-11-15&to=2026-11-16"
        )

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"
    disp = res.headers["Content-Disposition"]
    assert "daily_sales_export_20261115_20261116.csv" in disp

    content = res.content.decode("utf-8")
    lines = content.strip().split("\r\n")

    # Header check
    assert lines[0] == (
        "\ufeffNgày,Doanh thu thuần (VNĐ),Số đơn hoàn tất,Số đơn hủy,"
        "Giá trị trung bình đơn (VNĐ)"
    )

    # Day 1: 2026-11-15 -> rev 100,000, completed 1, cancelled 1, aov 100,000
    assert lines[1] == "2026-11-15,100000,1,1,100000"

    # Day 2: 2026-11-16 -> rev 200,000, completed 1, cancelled 0, aov 200,000
    assert lines[2] == "2026-11-16,200000,1,0,200000"


@pytest.mark.anyio
async def test_daily_sales_csv_export_invalid_range_returns_422() -> None:
    """Daily sales CSV returns 422 if from > to or interval > 365 days."""
    service = SalesAnalyticsService(repository=FakeAnalyticsRepo([]))  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, analytics_service=service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # from > to
        res = await client.get(
            "/api/v1/analytics/sales/daily/export/csv?from=2026-11-20&to=2026-11-10"
        )
        assert res.status_code == 422

        # > 366 days
        res = await client.get(
            "/api/v1/analytics/sales/daily/export/csv?from=2024-01-01&to=2026-01-01"
        )
        assert res.status_code == 422


# ==============================================================================
# 5. INVENTORY CSV EXPORT TESTS
# ==============================================================================


class FakeInventoryRepo:
    def __init__(self, items: list[dict[str, Any]], total: int) -> None:
        self.items = items
        self.total = total
        self.last_query: dict[str, Any] = {}

    def list_inventory_for_export(
        self,
        session: object,
        *,
        category_id: int | None = None,
        status: str | None = None,
        in_stock: bool | None = None,
        low_stock_only: bool = False,
        limit: int = 5001,
    ) -> tuple[list[dict[str, Any]], int]:
        self.last_query = {
            "category_id": category_id,
            "status": status,
            "in_stock": in_stock,
            "low_stock_only": low_stock_only,
            "limit": limit,
        }
        return self.items, self.total


@pytest.mark.anyio
async def test_inventory_csv_export_content_and_cost_exclusion() -> None:
    """Inventory CSV includes category name, list price, and excludes cost price."""
    fake_items = [
        {
            "product_id": 1,
            "sku": "SKU-BEV-001",
            "name": "Trà sữa Ô long",
            "category_name": "Đồ uống",
            "status": "ACTIVE",
            "quantity": 15,
            "sale_price_vnd": 35_000,
            "first_stocked_at": datetime(2026, 10, 1, 2, 0, 0),  # UTC -> 09:00 VN
        },
        {
            "product_id": 2,
            "sku": "=SKU-SNK-002",
            "name": "@Khoai tây lắc phô mai",
            "category_name": "Ăn vặt",
            "status": "ACTIVE",
            "quantity": 3,
            "sale_price_vnd": 25_000,
            "first_stocked_at": None,
        },
    ]

    fake_repo = FakeInventoryRepo(fake_items, total=2)
    service = InventoryQueryService(repository=fake_repo)  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, inventory_service=service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/inventory/export/csv?low_stock_only=true")

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"
    assert "inventory_export_" in res.headers["Content-Disposition"]

    content = res.content.decode("utf-8")
    lines = content.strip().split("\r\n")

    # Header check: MUST NOT contain unit_cost_vnd
    assert lines[0] == (
        "\ufeffMã SP,SKU,Tên sản phẩm,Danh mục,Trạng thái,"
        "Tồn kho hiện tại,Giá bán niêm yết (VNĐ),Ngày nhập đầu tiên (VN)"
    )
    assert "cost" not in lines[0].lower()
    assert "giá vốn" not in lines[0].lower()

    # Row 1
    exp_r1 = "1,SKU-BEV-001,Trà sữa Ô long,Đồ uống,ACTIVE,15,35000,2026-10-01 09:00:00"
    assert exp_r1 in lines[1]
    # Row 2 (sanitized formulas)
    exp_r2 = "2,'=SKU-SNK-002,'@Khoai tây lắc phô mai,Ăn vặt,ACTIVE,3,25000,"
    assert exp_r2 in lines[2]


@pytest.mark.anyio
async def test_inventory_csv_export_exceeding_limit_returns_422() -> None:
    """Inventory CSV returns 422 when total > 5000."""
    fake_repo = FakeInventoryRepo([], total=6000)
    service = InventoryQueryService(repository=fake_repo)  # type: ignore[arg-type]
    app = make_test_app(authenticated=True, inventory_service=service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/inventory/export/csv")

    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"
    assert "6000" in res.json()["message"]


# ==============================================================================
# 6. SQL AGGREGATION & DATA INTEGRITY TESTS (P1 & P2 FIXES)
# ==============================================================================


def test_daily_sales_sql_aggregation_matches_python_computation() -> None:
    """SQL GROUP BY aggregation in repository matches Python manual calculation."""
    session = _make_sqlite_session()
    now_utc = datetime(2026, 11, 14, 0, 0, 0)
    admin = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=now_utc,
        updated_at=now_utc,
    )
    session.add(admin)
    session.flush()

    # Day 1 (VN): 2026-11-15 03:00 UTC -> 10:00 VN
    o1 = Order(
        id=1,
        status=OrderStatus.COMPLETED.value,
        total_vnd=150_000,
        created_by=1,
        sold_at=datetime(2026, 11, 15, 3, 0, 0),
    )
    o2 = Order(
        id=2,
        status=OrderStatus.CANCELLED.value,
        total_vnd=70_000,
        created_by=1,
        sold_at=datetime(2026, 11, 15, 4, 0, 0),
        cancelled_by=1,
        cancelled_at=datetime(2026, 11, 15, 4, 30, 0),
        cancel_reason="Khách hủy",
    )
    # Day 2 (VN): 2026-11-16 02:00 UTC -> 09:00 VN
    o3 = Order(
        id=3,
        status=OrderStatus.COMPLETED.value,
        total_vnd=300_000,
        created_by=1,
        sold_at=datetime(2026, 11, 16, 2, 0, 0),
    )
    o4 = Order(
        id=4,
        status=OrderStatus.COMPLETED.value,
        total_vnd=250_000,
        created_by=1,
        sold_at=datetime(2026, 11, 16, 5, 0, 0),
    )
    session.add_all([o1, o2, o3, o4])
    session.commit()

    repo = SalesAnalyticsRepository()
    results = repo.get_daily_sales_summary(
        session,
        start_utc=datetime(2026, 11, 14, 17, 0, 0),  # 2026-11-15 00:00 VN
        end_utc_exclusive=datetime(2026, 11, 16, 17, 0, 0),  # 2026-11-17 00:00 VN
    )

    # Manual Python summation
    all_seeded = [o1, o2, o3, o4]
    py_day1_completed = [
        o for o in all_seeded if o.sold_at.day == 15 and o.status == "COMPLETED"
    ]
    py_day1_cancelled = [
        o for o in all_seeded if o.sold_at.day == 15 and o.status == "CANCELLED"
    ]
    py_day2_completed = [
        o for o in all_seeded if o.sold_at.day == 16 and o.status == "COMPLETED"
    ]

    assert len(results) == 2

    # Day 15
    res_15 = next(r for r in results if r["vn_date"] == "2026-11-15")
    assert res_15["revenue_vnd"] == sum(o.total_vnd for o in py_day1_completed)
    assert res_15["completed_orders"] == len(py_day1_completed)
    assert res_15["cancelled_orders"] == len(py_day1_cancelled)

    # Day 16
    res_16 = next(r for r in results if r["vn_date"] == "2026-11-16")
    assert res_16["revenue_vnd"] == sum(o.total_vnd for o in py_day2_completed)
    assert res_16["completed_orders"] == len(py_day2_completed)
    assert res_16["cancelled_orders"] == 0
    session.close()


def test_daily_sales_vn_midnight_boundary() -> None:
    """16:59:59 UTC belongs to Day N VN, while 17:00:00 UTC belongs to Day N+1 VN."""
    session = _make_sqlite_session()
    now_utc = datetime(2026, 11, 14, 0, 0, 0)
    admin = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=now_utc,
        updated_at=now_utc,
    )
    session.add(admin)
    session.flush()

    # 16:59:59 UTC on Nov 15 + 7h = 23:59:59 on Nov 15 VN
    order_day_n = Order(
        id=1,
        status=OrderStatus.COMPLETED.value,
        total_vnd=100_000,
        created_by=1,
        sold_at=datetime(2026, 11, 15, 16, 59, 59),
    )
    # 17:00:00 UTC on Nov 15 + 7h = 00:00:00 on Nov 16 VN
    order_day_n_plus_1 = Order(
        id=2,
        status=OrderStatus.COMPLETED.value,
        total_vnd=200_000,
        created_by=1,
        sold_at=datetime(2026, 11, 15, 17, 0, 0),
    )
    session.add_all([order_day_n, order_day_n_plus_1])
    session.commit()

    repo = SalesAnalyticsRepository()
    results = repo.get_daily_sales_summary(
        session,
        start_utc=datetime(2026, 11, 15, 0, 0, 0),
        end_utc_exclusive=datetime(2026, 11, 17, 0, 0, 0),
    )

    day_map = {r["vn_date"]: r for r in results}
    assert "2026-11-15" in day_map
    assert day_map["2026-11-15"]["revenue_vnd"] == 100_000
    assert day_map["2026-11-15"]["completed_orders"] == 1

    assert "2026-11-16" in day_map
    assert day_map["2026-11-16"]["revenue_vnd"] == 200_000
    assert day_map["2026-11-16"]["completed_orders"] == 1
    session.close()


@pytest.mark.anyio
async def test_daily_sales_zero_order_days_populated() -> None:
    """Days without any orders are populated with zeros in the CSV export."""
    from datetime import date

    # Only Nov 12 has sales
    fake_summaries = [
        {
            "vn_date": "2026-11-12",
            "revenue_vnd": 500_000,
            "completed_orders": 2,
            "cancelled_orders": 1,
        }
    ]
    fake_repo = FakeAnalyticsRepo(fake_summaries)
    service = SalesAnalyticsService(repository=fake_repo)  # type: ignore[arg-type]

    response = service.export_daily_sales_csv(
        session=MagicMock(),
        from_date=date(2026, 11, 10),
        to_date=date(2026, 11, 14),
    )

    content = response.body.decode("utf-8")
    lines = content.strip().split("\r\n")

    # Header + 5 days = 6 lines
    assert len(lines) == 6
    assert lines[1] == "2026-11-10,0,0,0,0"
    assert lines[2] == "2026-11-11,0,0,0,0"
    assert lines[3] == "2026-11-12,500000,2,1,250000"
    assert lines[4] == "2026-11-13,0,0,0,0"
    assert lines[5] == "2026-11-14,0,0,0,0"


@pytest.mark.anyio
async def test_orders_csv_count_export_rows_limit() -> None:
    """Pre-count check allows <= 5000 and blocks > 5000 without loading orders."""
    # Case 1: 5000 rows (e.g. 500 orders x 10 items) -> allowed
    fake_repo_5000 = FakeOrderRepo([], total=500, export_rows_count=5000)
    service_5000 = OrderReadService(repository=fake_repo_5000)  # type: ignore[arg-type]

    filters = OrderQuery()
    res = service_5000.export_csv(session=MagicMock(), filters=filters)
    assert res.status_code == 200
    assert fake_repo_5000.list_orders_called is True

    # Case 2: 5001 rows (500 orders x 11 items = 5500 rows) -> rejected before fetch
    fake_repo_5001 = FakeOrderRepo([], total=500, export_rows_count=5001)
    service_5001 = OrderReadService(repository=fake_repo_5001)  # type: ignore[arg-type]

    with pytest.raises(DomainValidationError) as exc_info:
        service_5001.export_csv(session=MagicMock(), filters=filters)

    assert "vượt quá giới hạn xuất tối đa 5000" in exc_info.value.message
    # Critical memory-safety assertion: list_orders MUST NOT have been called!
    assert fake_repo_5001.list_orders_called is False
