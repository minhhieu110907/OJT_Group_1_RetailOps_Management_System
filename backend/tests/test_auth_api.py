"""HTTP boundary tests for cookies, Origin, CSRF, and cold start."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.schemas import AuthenticatedUser, TokenResponse
from app.modules.auth.service import AuthResult, AuthService

ORIGIN = "http://127.0.0.1:5173"


def auth_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def override_db() -> object:
    yield object()


class FakeLoginService:
    def login(self, _session: object, _email: str, _password: str) -> AuthResult:
        return AuthResult(
            response=TokenResponse(
                access_token="access-token",
                expires_in=900,
                user=AuthenticatedUser(
                    id=1,
                    email_normalized="active@example.com",
                    role="STAFF",
                    status="ACTIVE",
                ),
            ),
            refresh_token="refresh-token",
            csrf_token="csrf-token",
            session_expires_at=datetime.now(UTC) + timedelta(hours=8),
        )


@pytest.mark.anyio
async def test_login_sets_scoped_httponly_refresh_and_csrf_proof() -> None:
    settings = auth_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = FakeLoginService
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "active@example.com", "password": "valid-password"},
        )

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    refresh_cookie = next(item for item in cookies if "retailops_refresh=" in item)
    csrf_cookie = next(item for item in cookies if "retailops_csrf=" in item)
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/v1/auth" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert response.headers["x-csrf-token"] == "csrf-token"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_csrf_cold_start_does_not_require_session() -> None:
    settings = auth_settings()
    service = AuthService(settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/auth/csrf")

    assert response.status_code == 200
    token = response.json()["csrf_token"]
    service.csrf.verify_pair(
        header_token=token,
        cookie_token=token,
        expected_session_id=None,
    )
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_refresh_rejects_missing_origin_before_database_work() -> None:
    settings = auth_settings()
    service = AuthService(settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    session_id = uuid4()
    csrf_token = service.csrf.issue(session_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        client.cookies.set(settings.refresh_cookie_name, "unknown")
        client.cookies.set(settings.csrf_cookie_name, csrf_token)
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REJECTED"
