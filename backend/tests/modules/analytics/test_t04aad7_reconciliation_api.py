"""Unit and API contract tests for T04AAD7 cross-module reconciliation.

Scope:
1. Unified RBAC Matrix across Product, Order, Analytics, and Dashboard endpoints.
2. Parameter validation & boundary conditions (pagination & date boundaries).
3. Contract & fake adapter verification for T04A947 (ProductAnalyticsService port).

Note: Does NOT require MySQL database (runs in memory via FastAPI test client).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthenticatedError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.analytics.router import (
    get_dashboard_service,
    get_sales_analytics_service,
)
from app.modules.analytics.service import (
    DashboardData,
    Period,
    ProductAnalyticsItem,
    SalesSummary,
)
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.models import User
from app.modules.products.models import CatalogStatus
from app.modules.products.router import get_product_service
from app.modules.products.schemas import ProductListResponse, ProductRead
from app.modules.sales.router import (
    get_order_read_service,
)
from app.modules.sales.schemas import (
    OrderLineRead,
    OrderPage,
    OrderRead,
)


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class LowStockItem:
    product_id: int
    sku: str
    name: str
    quantity: int
    threshold: int


class FakeProductService:
    """Predictable product service stub."""

    def list_products(self, session: object, **kwargs: object) -> ProductListResponse:
        del session, kwargs
        return ProductListResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
        )

    def get_product(
        self, session: object, product_id: int, **kwargs: object
    ) -> ProductRead:
        del session, kwargs
        return ProductRead(
            id=product_id,
            category_id=1,
            sku="SKU-TEST-001",
            name="Sản phẩm kiểm thử",
            sale_price_vnd=50_000,
            status=CatalogStatus.ACTIVE,
            quantity=10,
            stock_version=1,
            created_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
            updated_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
        )


class FakeOrderReadService:
    """Predictable order read service stub."""

    def list(self, session: object, **kwargs: object) -> OrderPage:
        del session, kwargs
        return OrderPage(items=[], total=0, page=1, page_size=20)

    def get(self, session: object, order_id: int, **kwargs: object) -> OrderRead:
        del session, kwargs
        return OrderRead(
            id=order_id,
            status="COMPLETED",
            total_vnd=100_000,
            created_by=1,
            sold_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
            cancelled_by=None,
            cancelled_at=None,
            cancel_reason=None,
            items=(
                OrderLineRead(
                    product_id=1,
                    sku_snapshot="SKU-TEST-001",
                    product_name_snapshot="Sản phẩm test",
                    quantity=2,
                    unit_price_vnd=50_000,
                    line_total_vnd=100_000,
                ),
            ),
        )


class FakeSalesAnalyticsService:
    """Predictable sales analytics service stub."""

    def summary(
        self, session: object, *, period: Period, **kwargs: object
    ) -> SalesSummary:
        del session, kwargs
        return SalesSummary(
            period_start=period.start_utc,
            period_end_exclusive=period.end_utc_exclusive,
            revenue_vnd=500_000,
            completed_orders=5,
            cancelled_orders=1,
            aov_vnd=100_000,
        )


class FakeDashboardService:
    """Predictable dashboard service stub."""

    def read(
        self, session: object, *, period: Period, **kwargs: object
    ) -> DashboardData:
        del session, kwargs
        return DashboardData(
            sales=SalesSummary(
                period_start=period.start_utc,
                period_end_exclusive=period.end_utc_exclusive,
                revenue_vnd=500_000,
                completed_orders=5,
                cancelled_orders=1,
                aov_vnd=100_000,
            ),
            low_stock_count=2,
            top_products=(
                ProductAnalyticsItem(
                    product_id=1,
                    sku="SKU-TEST-001",
                    name="Sản phẩm test",
                    sold_units=10,
                    revenue_vnd=500_000,
                    quantity=8,
                    first_stocked_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
                ),
            ),
        )


def make_test_app(
    *,
    authenticated: bool = True,
    user_role: str = "ADMIN",
    user_status: str = "ACTIVE",
) -> FastAPI:
    """Build a FastAPI test application with injected stubs and auth principal."""
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

    # Override module services
    app.dependency_overrides[get_product_service] = FakeProductService
    app.dependency_overrides[get_order_read_service] = FakeOrderReadService
    app.dependency_overrides[get_sales_analytics_service] = FakeSalesAnalyticsService
    app.dependency_overrides[get_dashboard_service] = FakeDashboardService

    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1 if user_role == "ADMIN" else 2,
                email_normalized=f"{user_role.lower()}@example.com",
                password_hash="fake_hash",
                role=user_role,
                status=user_status,
                admin_slot=1 if user_role == "ADMIN" else None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 14, tzinfo=UTC),
                updated_at=datetime(2026, 11, 14, tzinfo=UTC),
            ),
            session_id=uuid4(),
        )
    return app


# ==============================================================================
# 1. RBAC Matrix Tests
# ==============================================================================


@pytest.mark.anyio
async def test_rbac_unauthenticated_requests_return_401() -> None:
    """Verify that unauthenticated requests to any of the 4 endpoints return 401."""
    app = make_test_app(authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Product list
        resp_prod = await client.get("/api/v1/products")
        assert resp_prod.status_code == 401

        # Order list
        resp_ord = await client.get("/api/v1/orders")
        assert resp_ord.status_code == 401

        # Sales analytics
        resp_sales = await client.get("/api/v1/analytics/sales")
        assert resp_sales.status_code == 401

        # Dashboard
        resp_dash = await client.get("/api/v1/dashboard")
        assert resp_dash.status_code == 401


@pytest.mark.anyio
async def test_rbac_active_staff_permissions() -> None:
    """Verify ACTIVE STAFF can view products & orders, but is denied analytics."""
    app = make_test_app(authenticated=True, user_role="STAFF", user_status="ACTIVE")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Products: STAFF permitted
        resp_prod = await client.get("/api/v1/products")
        assert resp_prod.status_code == 200

        # 2. Orders: STAFF permitted
        resp_ord = await client.get("/api/v1/orders")
        assert resp_ord.status_code == 200

        # 3. Analytics Sales: STAFF forbidden (ADMIN only)
        resp_sales = await client.get("/api/v1/analytics/sales")
        assert resp_sales.status_code == 403

        # 4. Dashboard: STAFF forbidden (ADMIN only)
        resp_dash = await client.get("/api/v1/dashboard")
        assert resp_dash.status_code == 403


@pytest.mark.anyio
async def test_rbac_active_admin_permissions() -> None:
    """Verify that ACTIVE ADMIN is permitted across all 4 endpoints."""
    app = make_test_app(authenticated=True, user_role="ADMIN", user_status="ACTIVE")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp_prod = await client.get("/api/v1/products")
        assert resp_prod.status_code == 200

        resp_ord = await client.get("/api/v1/orders")
        assert resp_ord.status_code == 200

        resp_sales = await client.get("/api/v1/analytics/sales")
        assert resp_sales.status_code == 200

        resp_dash = await client.get("/api/v1/dashboard")
        assert resp_dash.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "SUSPENDED"])
async def test_rbac_inactive_users_return_403(status: str) -> None:
    """Verify that users without ACTIVE status receive 403 on all endpoints."""
    app = make_test_app(authenticated=True, user_role="ADMIN", user_status=status)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp_prod = await client.get("/api/v1/products")
        assert resp_prod.status_code == 403

        resp_ord = await client.get("/api/v1/orders")
        assert resp_ord.status_code == 403

        resp_sales = await client.get("/api/v1/analytics/sales")
        assert resp_sales.status_code == 403

        resp_dash = await client.get("/api/v1/dashboard")
        assert resp_dash.status_code == 403


# ==============================================================================
# 2. Validation & Parameter Boundary Tests
# ==============================================================================


@pytest.mark.anyio
async def test_pagination_boundaries_validation() -> None:
    """Verify that page < 1, page_size < 1, or page_size > 100 return 422."""
    app = make_test_app(authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Products: page < 1
        r1 = await client.get("/api/v1/products?page=0")
        assert r1.status_code == 422

        # Products: page_size > 100
        r2 = await client.get("/api/v1/products?page_size=101")
        assert r2.status_code == 422

        # Orders: page < 1
        r3 = await client.get("/api/v1/orders?page=0")
        assert r3.status_code == 422

        # Orders: page_size > 100
        r4 = await client.get("/api/v1/orders?page_size=101")
        assert r4.status_code == 422


@pytest.mark.anyio
async def test_analytics_and_dashboard_date_validation_boundaries() -> None:
    """Verify from > to and interval > 366 days return 422 on analytics."""
    app = make_test_app(authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. from > to on /analytics/sales
        r_sales_inv = await client.get(
            "/api/v1/analytics/sales?from=2026-11-20&to=2026-11-10"
        )
        assert r_sales_inv.status_code == 422

        # 2. from > to on /dashboard
        r_dash_inv = await client.get("/api/v1/dashboard?from=2026-11-20&to=2026-11-10")
        assert r_dash_inv.status_code == 422

        # 3. Interval exceeds 366 days on /analytics/sales
        r_sales_exceed = await client.get(
            "/api/v1/analytics/sales?from=2024-01-01&to=2025-02-01"
        )
        assert r_sales_exceed.status_code == 422

        # 4. Supports legacy from_date / to_date aliases
        r_sales_legacy = await client.get(
            "/api/v1/analytics/sales?from_date=2026-11-10&to_date=2026-11-12"
        )
        assert r_sales_legacy.status_code == 200

        r_dash_legacy = await client.get(
            "/api/v1/dashboard?from_date=2026-11-10&to_date=2026-11-12"
        )
        assert r_dash_legacy.status_code == 200


# ==============================================================================
# 3. T04A947 Contract / Fake Adapter Verification (ProductAnalyticsService)
# ==============================================================================


class StandaloneProductAnalyticsAdapter:
    """Reference implementation of ProductAnalyticsService for CF-2.2 / CF-2.3.

    Port signature specified in contracts/python/retailops_extended_ports.pyi:
    - top(session, *, period, page, page_size) -> Page[ProductAnalyticsItem]
    - slow(session, *, as_of_utc, page, page_size) -> Page[ProductAnalyticsItem]
    - low_stock(session, *, page, page_size) -> Page[LowStockItem]
    """

    def __init__(
        self,
        orders_data: Sequence[dict[str, object]],
        products_data: Sequence[dict[str, object]],
    ) -> None:
        self.orders = list(orders_data)
        self.products = list(products_data)

    def top(
        self,
        session: object,
        *,
        period: Period,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[ProductAnalyticsItem]:
        """Aggregate top products: only COMPLETED orders in target period count."""
        del session
        # 1. Filter completed orders in period
        valid_orders = [
            o
            for o in self.orders
            if o["status"] == "COMPLETED"
            and period.start_utc <= o["sold_at"] < period.end_utc_exclusive
        ]

        # 2. Aggregate sold_units and revenue by product_id
        product_agg: dict[int, dict[str, int]] = {}
        for o in valid_orders:
            for item in o.get("items", []):
                pid = item["product_id"]
                if pid not in product_agg:
                    product_agg[pid] = {"sold_units": 0, "revenue_vnd": 0}
                product_agg[pid]["sold_units"] += item["quantity"]
                product_agg[pid]["revenue_vnd"] += item["line_total_vnd"]

        # 3. Map to Product info and sort: sold_units DESC, revenue DESC, id ASC
        products_by_id = {p["id"]: p for p in self.products}
        items: list[ProductAnalyticsItem] = []
        for pid, stats in product_agg.items():
            prod = products_by_id.get(pid, {})
            items.append(
                ProductAnalyticsItem(
                    product_id=pid,
                    sku=prod.get("sku", f"SKU-{pid}"),
                    name=prod.get("name", f"Product {pid}"),
                    sold_units=stats["sold_units"],
                    revenue_vnd=stats["revenue_vnd"],
                    quantity=prod.get("quantity"),
                    first_stocked_at=prod.get("first_stocked_at"),
                )
            )

        items.sort(
            key=lambda x: (-x.sold_units, -x.revenue_vnd, x.product_id),
        )

        # 4. Pagination
        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]
        return Page(
            items=tuple(paged_items),
            total=total,
            page=page,
            page_size=page_size,
        )

    def slow(
        self,
        session: object,
        *,
        as_of_utc: datetime,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[ProductAnalyticsItem]:
        """Aggregate slow products: ACTIVE, qty > 0, first_stocked > 7d, sold <= 2."""
        del session
        thirty_days_ago = as_of_utc - timedelta(days=30)
        seven_days_ago = as_of_utc - timedelta(days=7)

        # Calculate 30-day sold units for completed orders
        thirty_day_sales: dict[int, int] = {}
        for o in self.orders:
            if (
                o["status"] == "COMPLETED"
                and thirty_days_ago <= o["sold_at"] <= as_of_utc
            ):
                for item in o.get("items", []):
                    pid = item["product_id"]
                    thirty_day_sales[pid] = (
                        thirty_day_sales.get(pid, 0) + item["quantity"]
                    )

        slow_items: list[ProductAnalyticsItem] = []
        for p in self.products:
            # Must be ACTIVE, quantity > 0, first_stocked_at > 7 days ago
            if p.get("status") != "ACTIVE":
                continue
            if (p.get("quantity") or 0) <= 0:
                continue
            first_stocked = p.get("first_stocked_at")
            if not first_stocked or first_stocked > seven_days_ago:
                continue

            sold_units = thirty_day_sales.get(p["id"], 0)
            if sold_units <= 2:
                slow_items.append(
                    ProductAnalyticsItem(
                        product_id=p["id"],
                        sku=p["sku"],
                        name=p["name"],
                        sold_units=sold_units,
                        revenue_vnd=0,
                        quantity=p.get("quantity"),
                        first_stocked_at=first_stocked,
                    )
                )

        slow_items.sort(
            key=lambda x: (x.sold_units, x.first_stocked_at or datetime.min)
        )
        total = len(slow_items)
        offset = (page - 1) * page_size
        paged_items = slow_items[offset : offset + page_size]
        return Page(
            items=tuple(paged_items),
            total=total,
            page=page,
            page_size=page_size,
        )

    def low_stock(
        self,
        session: object,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[LowStockItem]:
        """Aggregate low stock: ACTIVE and quantity <= 5."""
        del session
        low_items = [
            LowStockItem(
                product_id=p["id"],
                sku=p["sku"],
                name=p["name"],
                quantity=p["quantity"],
                threshold=5,
            )
            for p in self.products
            if p.get("status") == "ACTIVE" and (p.get("quantity") or 0) <= 5
        ]
        low_items.sort(key=lambda x: (x.quantity, x.product_id))
        total = len(low_items)
        offset = (page - 1) * page_size
        return Page(
            items=tuple(low_items[offset : offset + page_size]),
            total=total,
            page=page,
            page_size=page_size,
        )


def test_t04a947_contract_adapter_logic() -> None:
    """Verify that StandaloneProductAnalyticsAdapter implements business rules."""
    now_utc = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)
    period = Period(
        start_utc=datetime(2026, 11, 19, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC),
    )

    products = [
        {
            "id": 1,
            "sku": "SKU-01",
            "name": "Nước ngọt",
            "status": "ACTIVE",
            "quantity": 10,
            "first_stocked_at": now_utc - timedelta(days=20),
        },
        {
            "id": 2,
            "sku": "SKU-02",
            "name": "Bánh quy",
            "status": "ACTIVE",
            "quantity": 4,  # low stock <= 5
            "first_stocked_at": now_utc - timedelta(days=15),
        },
        {
            "id": 3,
            "sku": "SKU-03",
            "name": "Trà sữa",
            "status": "ACTIVE",
            "quantity": 2,  # low stock <= 5 and slow moving
            "first_stocked_at": now_utc - timedelta(days=10),
        },
        {
            "id": 4,
            "sku": "SKU-04",
            "name": "Kẹo mút mới về",
            "status": "ACTIVE",
            "quantity": 50,
            "first_stocked_at": now_utc - timedelta(days=3),  # <= 7 days old!
        },
        {
            "id": 5,
            "sku": "SKU-05",
            "name": "Hàng ngừng bán",
            "status": "INACTIVE",
            "quantity": 1,
            "first_stocked_at": now_utc - timedelta(days=40),
        },
    ]

    orders = [
        # Order 1: Completed in period
        {
            "id": 101,
            "status": "COMPLETED",
            "sold_at": datetime(2026, 11, 20, 5, 0, 0, tzinfo=UTC),
            "items": [
                {
                    "product_id": 1,
                    "quantity": 5,
                    "unit_price_vnd": 10_000,
                    "line_total_vnd": 50_000,
                },
                {
                    "product_id": 2,
                    "quantity": 10,
                    "unit_price_vnd": 20_000,
                    "line_total_vnd": 200_000,
                },
            ],
        },
        # Order 2: CANCELLED (MUST be excluded from top products!)
        {
            "id": 102,
            "status": "CANCELLED",
            "sold_at": datetime(2026, 11, 20, 6, 0, 0, tzinfo=UTC),
            "items": [
                {
                    "product_id": 1,
                    "quantity": 50,
                    "unit_price_vnd": 10_000,
                    "line_total_vnd": 500_000,
                },
            ],
        },
    ]

    adapter = StandaloneProductAnalyticsAdapter(
        orders_data=orders, products_data=products
    )

    # 1. Test top(): Product 2 (sold 10) > Product 1 (sold 5); Cancelled order ignored!
    top_page = adapter.top(None, period=period, page=1, page_size=10)
    assert top_page.total == 2
    assert len(top_page.items) == 2
    assert top_page.items[0].product_id == 2
    assert top_page.items[0].sold_units == 10
    assert top_page.items[1].product_id == 1
    assert top_page.items[1].sold_units == 5  # NOT 55

    # 2. Test slow():
    # Product 3 (stocked 10d ago, sold 0 in 30d, qty 2 > 0) -> slow!
    # Product 4 excluded (stocked only 3d ago)
    # Product 5 excluded (INACTIVE)
    slow_page = adapter.slow(None, as_of_utc=now_utc, page=1, page_size=10)
    slow_ids = [p.product_id for p in slow_page.items]
    assert 3 in slow_ids
    assert 4 not in slow_ids
    assert 5 not in slow_ids

    # 3. Test low_stock():
    # Product 2 (qty 4 <= 5), Product 3 (qty 2 <= 5). Product 5 excluded (INACTIVE).
    low_page = adapter.low_stock(None, page=1, page_size=10)
    assert low_page.total == 2
    low_ids = [item.product_id for item in low_page.items]
    assert set(low_ids) == {2, 3}
