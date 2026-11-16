"""HTTP and API contract tests for GET /api/v1/analytics/sales."""

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
    get_sales_analytics_service,
)
from app.modules.analytics.router import (
    router as analytics_router,
)
from app.modules.analytics.service import (
    Period,
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
        app.dependency_overrides[get_sales_analytics_service] = lambda: service
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


class FakeSalesAnalyticsService:
    """Fake service returning predictable sales summary for API testing."""

    def __init__(self, summary: SalesSummary | None = None) -> None:
        self.summary_result = summary or SalesSummary(
            period_start=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
            revenue_vnd=130_000,
            completed_orders=1,
            cancelled_orders=1,
            aov_vnd=130_000,
        )
        self.last_period: Period | None = None

    def summary(self, session: object, *, period: Period) -> SalesSummary:
        self.last_period = period
        return self.summary_result


def test_generated_openapi_matches_frozen_contract() -> None:
    """Validate runtime analytics OpenAPI matches contracts/openapi.yaml."""
    app = FastAPI()
    app.include_router(analytics_router)
    runtime_openapi = app.openapi()

    openapi_path = (Path(__file__).parents[4] / "contracts" / "openapi.yaml").resolve()
    frozen = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))

    assert "/analytics/sales" in runtime_openapi["paths"]
    assert "get" in runtime_openapi["paths"]["/analytics/sales"]
    get_sales_op = runtime_openapi["paths"]["/analytics/sales"]["get"]

    # Check 200 response schema
    assert "200" in get_sales_op["responses"]
    schema_ref = get_sales_op["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert "SalesSummary" in schema_ref

    # Check query params on /analytics/sales
    runtime_param_names = {p["name"] for p in get_sales_op["parameters"]}
    assert {"from", "to"}.issubset(runtime_param_names)

    # Compare with frozen contract schema properties
    frozen_summary_props = frozen["components"]["schemas"]["SalesSummary"]["properties"]
    expected_fields = set(frozen_summary_props.keys())
    assert expected_fields == {
        "period_start",
        "period_end_exclusive",
        "revenue_vnd",
        "completed_orders",
        "cancelled_orders",
        "aov_vnd",
    }


@pytest.mark.anyio
async def test_sales_analytics_unauthenticated_returns_401() -> None:
    """Missing bearer token returns 401 Unauthorized."""
    app = make_test_app(FakeSalesAnalyticsService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_sales_analytics_invalid_token_returns_401() -> None:
    """Malformed or invalid bearer token returns 401 Unauthorized."""
    app = make_test_app(FakeSalesAnalyticsService(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/analytics/sales",
            headers={"Authorization": "Bearer bad_token_123"},
        )
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_sales_analytics_active_staff_returns_403() -> None:
    """STAFF role cannot access analytics (ADMIN only) -> 403 Forbidden."""
    app = make_test_app(
        FakeSalesAnalyticsService(),
        authenticated=True,
        user_role=UserRole.STAFF,
        user_status=UserStatus.ACTIVE,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_sales_analytics_pending_admin_returns_403() -> None:
    """ADMIN account in PENDING_APPROVAL status returns 403 Forbidden."""
    app = make_test_app(
        FakeSalesAnalyticsService(),
        authenticated=True,
        user_role=UserRole.ADMIN,
        user_status=UserStatus.PENDING_APPROVAL,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_sales_analytics_rejected_admin_returns_403() -> None:
    """ADMIN account in REJECTED status returns 403 Forbidden."""
    app = make_test_app(
        FakeSalesAnalyticsService(),
        authenticated=True,
        user_role=UserRole.ADMIN,
        user_status=UserStatus.REJECTED,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_sales_analytics_success_200_matches_example() -> None:
    """Active ADMIN receives 200 matching sales_summary_200.json contract."""
    fake_service = FakeSalesAnalyticsService(
        SalesSummary(
            period_start=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
            revenue_vnd=130_000,
            completed_orders=1,
            cancelled_orders=1,
            aov_vnd=130_000,
        )
    )
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=2026-11-18&to=2026-11-18")

    assert res.status_code == 200
    body = res.json()
    assert body == {
        "period_start": "2026-11-17T17:00:00Z",
        "period_end_exclusive": "2026-11-18T17:00:00Z",
        "revenue_vnd": 130_000,
        "completed_orders": 1,
        "cancelled_orders": 1,
        "aov_vnd": 130_000,
    }


@pytest.mark.anyio
async def test_sales_analytics_default_params_success_200() -> None:
    """Omitting from and to parameters resolves default today period."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales")

    assert res.status_code == 200
    assert fake_service.last_period is not None


@pytest.mark.anyio
async def test_sales_analytics_legacy_query_params_supported() -> None:
    """Passing from_date and to_date fallback query params works seamlessly."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/analytics/sales?from_date=2026-11-18&to_date=2026-11-18"
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
async def test_sales_analytics_validation_from_greater_than_to_422() -> None:
    """from > to returns 422 VALIDATION_ERROR."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=2026-11-20&to=2026-11-10")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_sales_analytics_validation_date_max_422() -> None:
    """to=9999-12-31 returns 422 without server error."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?to=9999-12-31")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_sales_analytics_validation_date_min_underflow_422() -> None:
    """from=0001-01-01&to=0001-01-01 returns 422 VALIDATION_ERROR, not 500."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=0001-01-01&to=0001-01-01")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "vượt giới hạn" in body["message"]


@pytest.mark.anyio
async def test_sales_analytics_validation_exceeds_max_days_422() -> None:
    """Span exceeding 365 days returns 422 VALIDATION_ERROR."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=2024-01-01&to=2025-01-02")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_sales_analytics_month_boundary_success_200() -> None:
    """Range crossing month boundary returns 200 OK."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=2026-01-31&to=2026-02-01")

    assert res.status_code == 200
    assert fake_service.last_period is not None


@pytest.mark.anyio
async def test_sales_analytics_invalid_date_format_422() -> None:
    """Malformed date string returns 422."""
    fake_service = FakeSalesAnalyticsService()
    app = make_test_app(fake_service, authenticated=True, user_role=UserRole.ADMIN)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/analytics/sales?from=invalid-date")

    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
