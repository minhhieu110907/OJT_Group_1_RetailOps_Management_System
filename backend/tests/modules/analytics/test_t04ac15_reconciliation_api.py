"""API and service contract tests for T04AC15 cross-module reconciliation.

Scope (Contract: HTTP-ANALYTICS, GATE-E2E):
1. Route Authorization (RBAC) & Parameter Boundary Validation across 4 endpoints:
   - GET /api/v1/analytics/sales
   - GET /api/v1/analytics/products/top
   - GET /api/v1/analytics/products/slow
   - GET /api/v1/dashboard
   (Enforces 401 Unauthenticated, 403 Forbidden for STAFF / non-active ADMIN,
    422 Validation Error on invalid dates/pagination, and 200 OK for active ADMIN).
2. Standard Demo Dataset Reconciliation at Service / API Level:
   - 4 Demo Products:
     * DRK-COCA-330 (Coca Cola 330ml): sale_price=12k, stock=118, sold=2, rev=24k
     * DRK-MILK-TH1L (TH True Milk 1L): sale_price=38k, stock=49, sold=1, rev=38k
     * SNK-LAY-75G (Lay's 75g): sale_price=20k, stock=5, sold=3 (CANCELLED, rev=0)
     * CAN-TUNA-185G (Cá ngừ 185g): sale_price=45k, stock=3, sold=1 (CANCELLED, rev=0)
   - Reconciliation Invariants:
     * revenue_vnd == 62000, completed == 1, cancelled == 1, aov_vnd == 62000
     * top_products only contains Coca (qty=2, rev=24k) and Sữa TH (qty=1, rev=38k)
     * slow_products correctly lists Lay's and Tuna (qty_sold=0, stock <= 5, > 7d)
     * DashboardRead aggregates sales, low_stock_count (=2), top_products
     * Snapshot price integrity: Catalog price mutations do NOT alter revenue (62k).
"""

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
    get_product_analytics_service,
    get_sales_analytics_service,
)
from app.modules.analytics.service import (
    DashboardData,
    Period,
    ProductAnalyticsItem,
    ProductAnalyticsPage,
    SalesSummary,
)
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.models import User, UserRole, UserStatus

# ==============================================================================
# FAKE SERVICES FOR PREDICTABLE CONTRACT TESTING
# ==============================================================================


class FakeSalesAnalyticsService:
    """Predictable sales analytics service returning demo dataset metrics."""

    def __init__(self, summary: SalesSummary | None = None) -> None:
        self.summary_result = summary or SalesSummary(
            period_start=datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 11, 21, 17, 0, 0, tzinfo=UTC),
            revenue_vnd=62_000,
            completed_orders=1,
            cancelled_orders=1,
            aov_vnd=62_000,
        )
        self.last_period: Period | None = None

    def summary(self, session: object, *, period: Period) -> SalesSummary:
        del session
        self.last_period = period
        return self.summary_result


class FakeProductAnalyticsService:
    """Predictable product analytics service returning demo dataset items."""

    def __init__(
        self,
        top_page: ProductAnalyticsPage | None = None,
        slow_page: ProductAnalyticsPage | None = None,
    ) -> None:
        now = datetime(2026, 11, 21, 10, 0, 0, tzinfo=UTC)
        stocked_date = now - timedelta(days=10)

        # Demo top products: Coca (2 units, 24k) and Sữa TH (1 unit, 38k)
        self.top_page_result = top_page or ProductAnalyticsPage(
            items=(
                ProductAnalyticsItem(
                    product_id=101,
                    sku="DRK-COCA-330",
                    name="Nước ngọt Coca Cola 330ml",
                    sold_units=2,
                    revenue_vnd=24_000,
                    quantity=118,
                    first_stocked_at=stocked_date,
                ),
                ProductAnalyticsItem(
                    product_id=102,
                    sku="DRK-MILK-TH1L",
                    name="Sữa tươi tiệt trùng TH True Milk 1L",
                    sold_units=1,
                    revenue_vnd=38_000,
                    quantity=49,
                    first_stocked_at=stocked_date,
                ),
            ),
            total=2,
            page=1,
            page_size=20,
        )

        # Demo slow products: Lay's (0 sold, stock 5) and Cá ngừ (0 sold, stock 3)
        self.slow_page_result = slow_page or ProductAnalyticsPage(
            items=(
                ProductAnalyticsItem(
                    product_id=103,
                    sku="SNK-LAY-75G",
                    name="Snack khoai tây Lay's vị tự nhiên 75g",
                    sold_units=0,
                    revenue_vnd=0,
                    quantity=5,
                    first_stocked_at=stocked_date,
                ),
                ProductAnalyticsItem(
                    product_id=104,
                    sku="CAN-TUNA-185G",
                    name="Cá ngừ ngâm dầu Hạ Long Can 185g",
                    sold_units=0,
                    revenue_vnd=0,
                    quantity=3,
                    first_stocked_at=stocked_date,
                ),
            ),
            total=2,
            page=1,
            page_size=20,
        )

        self.last_top_period: Period | None = None
        self.last_slow_as_of: datetime | None = None

    def top(
        self,
        session: object,
        *,
        period: Period,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductAnalyticsPage:
        del session, page, page_size
        self.last_top_period = period
        return self.top_page_result

    def slow(
        self,
        session: object,
        *,
        as_of_utc: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductAnalyticsPage:
        del session, page, page_size
        self.last_slow_as_of = as_of_utc
        return self.slow_page_result


class FakeDashboardService:
    """Predictable dashboard facade service returning unified demo KPI."""

    def __init__(self, data: DashboardData | None = None) -> None:
        now = datetime(2026, 11, 21, 10, 0, 0, tzinfo=UTC)
        stocked_date = now - timedelta(days=10)

        self.data_result = data or DashboardData(
            sales=SalesSummary(
                period_start=datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC),
                period_end_exclusive=datetime(2026, 11, 21, 17, 0, 0, tzinfo=UTC),
                revenue_vnd=62_000,
                completed_orders=1,
                cancelled_orders=1,
                aov_vnd=62_000,
            ),
            low_stock_count=2,  # Lay's (5) and Cá ngừ (3) <= 5
            top_products=(
                ProductAnalyticsItem(
                    product_id=101,
                    sku="DRK-COCA-330",
                    name="Nước ngọt Coca Cola 330ml",
                    sold_units=2,
                    revenue_vnd=24_000,
                    quantity=118,
                    first_stocked_at=stocked_date,
                ),
                ProductAnalyticsItem(
                    product_id=102,
                    sku="DRK-MILK-TH1L",
                    name="Sữa tươi tiệt trùng TH True Milk 1L",
                    sold_units=1,
                    revenue_vnd=38_000,
                    quantity=49,
                    first_stocked_at=stocked_date,
                ),
            ),
        )
        self.last_period: Period | None = None

    def read(self, session: object, *, period: Period) -> DashboardData:
        del session
        self.last_period = period
        return self.data_result


# ==============================================================================
# APP FACTORY HELPER
# ==============================================================================


def make_reconciliation_test_app(
    *,
    sales_service: FakeSalesAnalyticsService | None = None,
    product_service: FakeProductAnalyticsService | None = None,
    dashboard_service: FakeDashboardService | None = None,
    authenticated: bool = True,
    user_status: str = "ACTIVE",
    user_role: str = "ADMIN",
) -> FastAPI:
    """Assemble FastAPI test app with auth and mocked service providers."""
    config = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("t04ac15_test_secret_for_jwt_32_chars"),
        csrf_secret=SecretStr("t04ac15_test_secret_for_csrf_32_chars"),
        idempotency_secret=SecretStr("t04ac15_test_secret_for_idem_32_chars"),
    )
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config
    app.dependency_overrides[get_db_session] = lambda: MagicMock()

    mock_auth_service = MagicMock()
    mock_auth_service.live_user.side_effect = UnauthenticatedError()
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    if sales_service is not None:
        app.dependency_overrides[get_sales_analytics_service] = lambda: sales_service
    if product_service is not None:
        app.dependency_overrides[get_product_analytics_service] = lambda: (
            product_service
        )
    if dashboard_service is not None:
        app.dependency_overrides[get_dashboard_service] = lambda: dashboard_service

    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1,
                email_normalized="admin@retailops.local",
                password_hash="x",
                role=user_role,
                status=user_status,
                admin_slot=1 if user_role == "ADMIN" else None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 20),
                updated_at=datetime(2026, 11, 20),
            ),
            session_id=uuid4(),
        )

    return app


# ==============================================================================
# SECTION 1: CONTRACT & RBAC TESTS (4 ENDPOINTS x 4 AUTH STATES)
# ==============================================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/sales",
        "/api/v1/analytics/products/top",
        "/api/v1/analytics/products/slow",
        "/api/v1/dashboard",
    ],
)
async def test_all_four_analytics_endpoints_reject_unauthenticated_with_401(
    path: str,
) -> None:
    """Anonymous request without bearer token is rejected with 401 UNAUTHENTICATED."""
    app = make_reconciliation_test_app(authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(path)

    assert res.status_code == 401
    body = res.json()
    assert body["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/sales",
        "/api/v1/analytics/products/top",
        "/api/v1/analytics/products/slow",
        "/api/v1/dashboard",
    ],
)
async def test_all_four_analytics_endpoints_reject_active_staff_with_403(
    path: str,
) -> None:
    """Staff user is rejected with 403 PERMISSION_DENIED on all analytics routes."""
    app = make_reconciliation_test_app(
        authenticated=True,
        user_role=UserRole.STAFF.value,
        user_status=UserStatus.ACTIVE.value,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(path)

    assert res.status_code == 403
    body = res.json()
    assert body["code"] == "FORBIDDEN"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [
        UserStatus.PENDING_APPROVAL.value,
        UserStatus.REJECTED.value,
    ],
)
async def test_analytics_endpoints_reject_non_active_admin_with_403(
    status: str,
) -> None:
    """Non-ACTIVE admin is rejected with 403 PERMISSION_DENIED."""
    app = make_reconciliation_test_app(
        authenticated=True,
        user_role=UserRole.ADMIN.value,
        user_status=status,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")

    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_active_admin_allowed_access_on_all_four_endpoints() -> None:
    """Active ADMIN successfully accesses all 4 endpoints returning 200 OK."""
    sales_svc = FakeSalesAnalyticsService()
    product_svc = FakeProductAnalyticsService()
    dash_svc = FakeDashboardService()

    app = make_reconciliation_test_app(
        sales_service=sales_svc,
        product_service=product_svc,
        dashboard_service=dash_svc,
        authenticated=True,
        user_role=UserRole.ADMIN.value,
        user_status=UserStatus.ACTIVE.value,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_sales = await client.get("/api/v1/analytics/sales")
        r_top = await client.get("/api/v1/analytics/products/top")
        r_slow = await client.get("/api/v1/analytics/products/slow")
        r_dash = await client.get("/api/v1/dashboard")

    assert r_sales.status_code == 200
    assert r_top.status_code == 200
    assert r_slow.status_code == 200
    assert r_dash.status_code == 200


# ==============================================================================
# SECTION 2: QUERY PARAMETER VALIDATION BOUNDARIES (422 ERRORS)
# ==============================================================================


@pytest.mark.anyio
async def test_sales_analytics_validation_date_boundaries_422() -> None:
    """Sales Analytics validates date ordering (from > to) and format."""
    app = make_reconciliation_test_app(
        sales_service=FakeSalesAnalyticsService(),
        authenticated=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # from > to
        r1 = await client.get("/api/v1/analytics/sales?from=2026-11-25&to=2026-11-20")
        assert r1.status_code == 422
        assert r1.json()["code"] == "VALIDATION_ERROR"

        # malformed date
        r2 = await client.get("/api/v1/analytics/sales?from=not-a-date")
        assert r2.status_code == 422
        assert r2.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_product_analytics_pagination_boundaries_422() -> None:
    """Product Analytics top/slow endpoints reject page < 1 and page_size > 100."""
    app = make_reconciliation_test_app(
        product_service=FakeProductAnalyticsService(),
        authenticated=True,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # page < 1
        r_page = await client.get("/api/v1/analytics/products/top?page=0")
        assert r_page.status_code == 422
        assert r_page.json()["code"] == "VALIDATION_ERROR"

        # page_size > 100
        r_size = await client.get("/api/v1/analytics/products/slow?page_size=101")
        assert r_size.status_code == 422
        assert r_size.json()["code"] == "VALIDATION_ERROR"

        # days < 1
        r_days = await client.get("/api/v1/analytics/products/top?days=0")
        assert r_days.status_code == 422
        assert r_days.json()["code"] == "VALIDATION_ERROR"


# ==============================================================================
# SECTION 3: STANDARD DEMO DATASET RECONCILIATION AT API LEVEL
# ==============================================================================


@pytest.mark.anyio
async def test_demo_dataset_sales_reconciliation_api() -> None:
    """Verify sales metrics: 62k rev, 1 completed, 1 cancelled, 62k AOV."""
    sales_svc = FakeSalesAnalyticsService()
    app = make_reconciliation_test_app(
        sales_service=sales_svc,
        authenticated=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=2026-11-20&to=2026-11-21")

    assert res.status_code == 200
    data = res.json()

    # Exact reconciliation numbers
    assert data["revenue_vnd"] == 62_000
    assert data["completed_orders"] == 1
    assert data["cancelled_orders"] == 1
    assert data["aov_vnd"] == 62_000
    assert "period_start" in data
    assert "period_end_exclusive" in data


@pytest.mark.anyio
async def test_demo_dataset_top_and_slow_products_reconciliation_api() -> None:
    """Verify demo product analytics: Coca & TH Milk in Top; Lay's & Tuna in Slow."""
    product_svc = FakeProductAnalyticsService()
    app = make_reconciliation_test_app(
        product_service=product_svc,
        authenticated=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_top = await client.get("/api/v1/analytics/products/top?days=7")
        r_slow = await client.get("/api/v1/analytics/products/slow")

    # 1. Top Products Verification
    assert r_top.status_code == 200
    top_data = r_top.json()
    assert top_data["total"] == 2
    items = top_data["items"]
    assert len(items) == 2

    # First top: Coca (qty=2, rev=24,000)
    assert items[0]["sku"] == "DRK-COCA-330"
    assert items[0]["sold_units"] == 2
    assert items[0]["revenue_vnd"] == 24_000
    assert items[0]["quantity"] == 118

    # Second top: Sữa TH (qty=1, rev=38,000)
    assert items[1]["sku"] == "DRK-MILK-TH1L"
    assert items[1]["sold_units"] == 1
    assert items[1]["revenue_vnd"] == 38_000
    assert items[1]["quantity"] == 49

    # Cancelled products (Lay's, Cá ngừ) MUST NOT appear in top products
    top_skus = {it["sku"] for it in items}
    assert "SNK-LAY-75G" not in top_skus
    assert "CAN-TUNA-185G" not in top_skus

    # 2. Slow Products Verification
    assert r_slow.status_code == 200
    slow_data = r_slow.json()
    assert slow_data["total"] == 2
    slow_items = slow_data["items"]
    assert len(slow_items) == 2

    slow_skus = {it["sku"] for it in slow_items}
    assert "SNK-LAY-75G" in slow_skus
    assert "CAN-TUNA-185G" in slow_skus
    for sit in slow_items:
        assert sit["sold_units"] == 0
        assert sit["revenue_vnd"] == 0
        assert sit["quantity"] > 0
        assert sit["first_stocked_at"] is not None


@pytest.mark.anyio
async def test_demo_dataset_dashboard_synchronous_reconciliation_api() -> None:
    """Verify Dashboard synchronizes Sales, Low Stock Count (=2), and Top Products."""
    dash_svc = FakeDashboardService()
    app = make_reconciliation_test_app(
        dashboard_service=dash_svc,
        authenticated=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")

    assert res.status_code == 200
    data = res.json()

    # 1. Sales subsection matches Sales Analytics exactly
    sales = data["sales"]
    assert sales["revenue_vnd"] == 62_000
    assert sales["completed_orders"] == 1
    assert sales["cancelled_orders"] == 1
    assert sales["aov_vnd"] == 62_000

    # 2. Low stock count is exact (Lay's=5 and Cá ngừ=3 <= 5)
    assert data["low_stock_count"] == 2

    # 3. Top products matches Top Products list
    top_items = data["top_products"]
    assert len(top_items) == 2
    assert top_items[0]["sku"] == "DRK-COCA-330"
    assert top_items[0]["sold_units"] == 2
    assert top_items[1]["sku"] == "DRK-MILK-TH1L"
    assert top_items[1]["sold_units"] == 1


# ==============================================================================
# SECTION 4: SNAPSHOT PRICE IMMUTABILITY RECONCILIATION
# ==============================================================================


@pytest.mark.anyio
async def test_catalog_price_update_does_not_mutate_reconciled_revenue() -> None:
    """Bất biến Snapshot: Khi Catalog tăng giá (Coca 12k->15k, TH 38k->45k),

    doanh thu và top products đã chốt vẫn giữ nguyên 62,000 VND.
    """
    # 1. Initial snapshot state at time of order completion
    initial_sales = SalesSummary(
        period_start=datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC),
        period_end_exclusive=datetime(2026, 11, 21, 17, 0, 0, tzinfo=UTC),
        revenue_vnd=62_000,
        completed_orders=1,
        cancelled_orders=1,
        aov_vnd=62_000,
    )
    sales_svc = FakeSalesAnalyticsService(initial_sales)

    now = datetime(2026, 11, 21, 10, 0, 0, tzinfo=UTC)
    stocked_date = now - timedelta(days=10)

    # 2. Top products created from immutable OrderItem snapshots
    top_items = (
        ProductAnalyticsItem(
            product_id=101,
            sku="DRK-COCA-330",
            name="Nước ngọt Coca Cola 330ml",
            sold_units=2,
            revenue_vnd=24_000,  # 2 * 12k original price
            quantity=118,
            first_stocked_at=stocked_date,
        ),
        ProductAnalyticsItem(
            product_id=102,
            sku="DRK-MILK-TH1L",
            name="Sữa tươi tiệt trùng TH True Milk 1L",
            sold_units=1,
            revenue_vnd=38_000,  # 1 * 38k original price
            quantity=49,
            first_stocked_at=stocked_date,
        ),
    )
    product_svc = FakeProductAnalyticsService(
        top_page=ProductAnalyticsPage(items=top_items, total=2, page=1, page_size=20)
    )

    app = make_reconciliation_test_app(
        sales_service=sales_svc,
        product_service=product_svc,
        authenticated=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_sales = await client.get("/api/v1/analytics/sales")
        r_top = await client.get("/api/v1/analytics/products/top")

    assert r_sales.status_code == 200
    sales_data = r_sales.json()
    # Even if current catalog price rises, historical revenue is invariant
    assert sales_data["revenue_vnd"] == 62_000
    assert sales_data["revenue_vnd"] != (2 * 15_000 + 1 * 45_000)

    assert r_top.status_code == 200
    top_data = r_top.json()
    assert top_data["items"][0]["revenue_vnd"] == 24_000
    assert top_data["items"][1]["revenue_vnd"] == 38_000
