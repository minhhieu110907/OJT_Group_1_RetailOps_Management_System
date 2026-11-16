"""HTTP, RBAC, and validation tests for T04A947 Product Analytics endpoints."""

from datetime import UTC, datetime
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
from app.modules.analytics.router import get_product_analytics_service
from app.modules.analytics.service import (
    ProductAnalyticsItem,
    ProductAnalyticsPage,
    resolve_days_period,
)
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.models import User


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
        app.dependency_overrides[get_product_analytics_service] = lambda: service

    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1,
                email_normalized="admin@example.com",
                password_hash="x",
                role=user_role,
                status=user_status,
                admin_slot=1 if user_role == "ADMIN" else None,
                last_reapplied_at=None,
                created_at=datetime(2026, 11, 16),
                updated_at=datetime(2026, 11, 16),
            ),
            session_id=uuid4(),
        )

    return app


def _sample_page() -> ProductAnalyticsPage:
    return ProductAnalyticsPage(
        items=(
            ProductAnalyticsItem(
                product_id=10,
                sku="SKU-010",
                name="Sample Item",
                sold_units=5,
                revenue_vnd=150000,
                quantity=12,
                first_stocked_at=datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC),
            ),
        ),
        total=1,
        page=1,
        page_size=20,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/analytics/products/top",
        "/api/v1/analytics/products/slow",
    ],
)
async def test_product_analytics_rbac_and_auth(path: str) -> None:
    """Unauthenticated -> 401; STAFF -> 403; ADMIN -> 200."""
    fake_service = MagicMock()
    fake_service.top.return_value = _sample_page()
    fake_service.slow.return_value = _sample_page()

    # 1. No token -> 401
    unauth_app = make_test_app(fake_service, authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=unauth_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(path)
        assert resp.status_code == 401

        # Invalid bearer token -> 401
        resp_bad = await client.get(
            path, headers={"Authorization": "Bearer invalid.jwt.token"}
        )
        assert resp_bad.status_code == 401

    # 2. STAFF -> 403
    staff_app = make_test_app(fake_service, authenticated=True, user_role="STAFF")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=staff_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(path)
        assert resp.status_code == 403

    # 3. ADMIN -> 200
    admin_app = make_test_app(fake_service, authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=admin_app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1


@pytest.mark.anyio
async def test_top_products_validation_422() -> None:
    """Invalid page, page_size, or days return 422."""
    fake_service = MagicMock()
    app = make_test_app(fake_service, authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        for query in [
            "?page=0",
            "?page_size=0",
            "?page_size=101",
            "?days=0",
            "?days=367",
        ]:
            resp = await client.get(f"/api/v1/analytics/products/top{query}")
            assert resp.status_code == 422, (
                f"Expected 422 for {query}, got {resp.status_code}"
            )


@pytest.mark.anyio
async def test_slow_validation_422() -> None:
    """Invalid page or page_size on slow return 422."""
    fake_service = MagicMock()
    app = make_test_app(fake_service, authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        for query in ["?page=0", "?page_size=0", "?page_size=101"]:
            resp = await client.get(f"/api/v1/analytics/products/slow{query}")
            assert resp.status_code == 422


@pytest.mark.anyio
async def test_unapproved_analytics_low_stock_route_not_exposed() -> None:
    """Unapproved /analytics/products/low-stock route must not be exposed (404)."""
    fake_service = MagicMock()
    app = make_test_app(fake_service, authenticated=True, user_role="ADMIN")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/analytics/products/low-stock")
        assert resp.status_code == 404


def test_resolve_days_period_vn_boundaries() -> None:
    """resolve_days_period(7) spans 7 VN business days ending at tomorrow 00:00 VN."""
    fixed_now = datetime(2026, 11, 16, 10, 0, 0, tzinfo=UTC)  # 17:00 VN on 2026-11-16
    period = resolve_days_period(7, now_fn=lambda: fixed_now)
    # 7 days: Nov 10 00:00 VN (Nov 9 17:00 UTC) .. Nov 17 00:00 VN (Nov 16 17:00 UTC)
    assert period.start_utc == datetime(2026, 11, 9, 17, 0, 0, tzinfo=UTC)
    assert period.end_utc_exclusive == datetime(2026, 11, 16, 17, 0, 0, tzinfo=UTC)
