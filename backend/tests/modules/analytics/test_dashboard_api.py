"""HTTP and API contract tests for GET /api/v1/dashboard."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthenticatedError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.analytics.router import (
    dashboard_router,
    get_dashboard_service,
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
from app.modules.auth.models import User, UserRole, UserStatus


def make_test_app(
    service: object | None = None,
    *,
    authenticated: bool = True,
    user_status: str = "ACTIVE",
    user_role: str = "ADMIN",
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

    if service is not None:
        app.dependency_overrides[get_dashboard_service] = lambda: service
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


class FakeDashboardService:
    """Fake service returning predictable dashboard data for API testing."""

    def __init__(self, data: DashboardData | None = None) -> None:
        self.data_result = data or DashboardData(
            sales=SalesSummary(
                period_start=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
                period_end_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
                revenue_vnd=250_000,
                completed_orders=2,
                cancelled_orders=1,
                aov_vnd=125_000,
            ),
            low_stock_count=3,
            top_products=(
                ProductAnalyticsItem(
                    product_id=1,
                    sku="SKU-COFFEE-01",
                    name="Cà phê đen đá",
                    sold_units=10,
                    revenue_vnd=150_000,
                    quantity=8,
                    first_stocked_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC),
                ),
                ProductAnalyticsItem(
                    product_id=2,
                    sku="SKU-TEA-02",
                    name="Trà lài đác thơm",
                    sold_units=5,
                    revenue_vnd=100_000,
                    quantity=4,
                    first_stocked_at=datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC),
                ),
            ),
        )
        self.last_period: Period | None = None

    def read(self, session: object, *, period: Period) -> DashboardData:
        self.last_period = period
        return self.data_result


def test_generated_openapi_matches_frozen_contract() -> None:
    """Validate runtime dashboard OpenAPI matches contracts/openapi.yaml."""
    app = FastAPI()
    app.include_router(dashboard_router)
    runtime_openapi = app.openapi()

    openapi_path = (Path(__file__).parents[4] / "contracts" / "openapi.yaml").resolve()
    frozen = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))

    assert "/dashboard" in runtime_openapi["paths"]
    assert "get" in runtime_openapi["paths"]["/dashboard"]
    get_dashboard_op = runtime_openapi["paths"]["/dashboard"]["get"]

    # Check 200 response schema
    assert "200" in get_dashboard_op["responses"]
    schema_ref = get_dashboard_op["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert "DashboardRead" in schema_ref

    # Check query params on /dashboard
    runtime_param_names = {p["name"] for p in get_dashboard_op["parameters"]}
    assert {"from", "to"}.issubset(runtime_param_names)

    # Compare with frozen contract schema properties
    frozen_dashboard_props = frozen["components"]["schemas"]["DashboardRead"][
        "properties"
    ]
    expected_fields = set(frozen_dashboard_props.keys())
    assert expected_fields == {
        "sales",
        "low_stock_count",
        "top_products",
    }

    # Top products items schema properties
    frozen_item_props = frozen["components"]["schemas"]["ProductAnalyticsItem"][
        "properties"
    ]
    expected_item_fields = set(frozen_item_props.keys())
    assert {
        "product_id",
        "sku",
        "name",
        "sold_units",
        "revenue_vnd",
    }.issubset(expected_item_fields)


@pytest.mark.anyio
async def test_dashboard_unauthenticated_returns_401() -> None:
    """Missing bearer token returns 401 Unauthorized."""
    app = make_test_app(FakeDashboardService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_dashboard_invalid_token_returns_401() -> None:
    """Malformed or invalid bearer token returns 401 Unauthorized."""
    app = make_test_app(FakeDashboardService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/dashboard",
            headers={"Authorization": "Bearer bad_token_123"},
        )
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_dashboard_active_staff_returns_403() -> None:
    """STAFF role cannot access dashboard (ADMIN only) -> 403 Forbidden."""
    app = make_test_app(
        FakeDashboardService(),
        authenticated=True,
        user_role=UserRole.STAFF,
        user_status=UserStatus.ACTIVE,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_dashboard_pending_admin_returns_403() -> None:
    """ADMIN account in PENDING_APPROVAL status returns 403 Forbidden."""
    app = make_test_app(
        FakeDashboardService(),
        authenticated=True,
        user_role=UserRole.ADMIN,
        user_status=UserStatus.PENDING_APPROVAL,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_dashboard_rejected_admin_returns_403() -> None:
    """ADMIN account in REJECTED status returns 403 Forbidden."""
    app = make_test_app(
        FakeDashboardService(),
        authenticated=True,
        user_role=UserRole.ADMIN,
        user_status=UserStatus.REJECTED,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_dashboard_success_200_matches_contract() -> None:
    """Active ADMIN receives 200 matching DashboardRead schema."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard?from=2026-11-18&to=2026-11-18")

    assert res.status_code == 200
    body = res.json()
    assert body == {
        "sales": {
            "period_start": "2026-11-17T17:00:00Z",
            "period_end_exclusive": "2026-11-18T17:00:00Z",
            "revenue_vnd": 250_000,
            "completed_orders": 2,
            "cancelled_orders": 1,
            "aov_vnd": 125_000,
        },
        "low_stock_count": 3,
        "top_products": [
            {
                "product_id": 1,
                "sku": "SKU-COFFEE-01",
                "name": "Cà phê đen đá",
                "sold_units": 10,
                "revenue_vnd": 150_000,
                "quantity": 8,
                "first_stocked_at": "2026-11-01T10:00:00Z",
            },
            {
                "product_id": 2,
                "sku": "SKU-TEA-02",
                "name": "Trà lài đác thơm",
                "sold_units": 5,
                "revenue_vnd": 100_000,
                "quantity": 4,
                "first_stocked_at": "2026-11-05T08:00:00Z",
            },
        ],
    }


@pytest.mark.anyio
async def test_dashboard_default_params_success_200() -> None:
    """Omitting from and to parameters resolves default today period."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard")

    assert res.status_code == 200
    assert fake_service.last_period is not None


@pytest.mark.anyio
async def test_dashboard_legacy_query_params_supported() -> None:
    """Passing from_date and to_date fallback query params works seamlessly."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/dashboard?from_date=2026-11-18&to_date=2026-11-18"
        )

    assert res.status_code == 200
    assert fake_service.last_period is not None
    assert fake_service.last_period.start_utc == datetime(
        2026, 11, 17, 17, 0, 0, tzinfo=UTC
    )
    assert fake_service.last_period.end_utc_exclusive == datetime(
        2026, 11, 18, 17, 0, 0, tzinfo=UTC
    )


@pytest.mark.anyio
async def test_dashboard_validation_from_greater_than_to_422() -> None:
    """from > to returns 422 VALIDATION_ERROR."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard?from=2026-11-20&to=2026-11-10")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_dashboard_validation_date_max_422() -> None:
    """to=9999-12-31 returns 422 without server error."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard?to=9999-12-31")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_dashboard_invalid_date_format_422() -> None:
    """Malformed date string returns 422."""
    fake_service = FakeDashboardService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/dashboard?from=invalid-date")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
