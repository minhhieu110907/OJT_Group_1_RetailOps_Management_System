"""Unit and API tests for Redis registration rate limiting."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import Depends, FastAPI
from pydantic import SecretStr, ValidationError
from redis.exceptions import ConnectionError
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import DependencyUnavailableError, InvalidCredentialsError
from app.db.session import get_db_session
from app.infrastructure.dependencies import (
    enforce_registration_rate_limit,
    get_rate_limiter,
)
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.schemas import AuthenticatedUser, RegisterResponse, TokenResponse
from app.modules.auth.security import CsrfService
from app.modules.auth.service import REGISTER_ACCEPTED_MESSAGE, AuthResult


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "db_host": "unused",
        "db_name": "unused",
        "db_user": "unused",
        "db_password": SecretStr("unused"),
        "jwt_secret": SecretStr("j" * 32),
        "csrf_secret": SecretStr("c" * 32),
    }
    values.update(overrides)
    return Settings(**values)


class FakeRedis:
    def __init__(self, responses: list[list[int]] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[tuple[object, ...]] = []

    async def eval(self, *args: object) -> list[int]:
        self.calls.append(args)
        return self.responses.pop(0)


class UnavailableRedis:
    async def eval(self, *_args: object) -> list[int]:
        raise ConnectionError("test Redis unavailable")


class CountingRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.calls: list[tuple[object, ...]] = []

    async def eval(self, *args: object) -> list[int]:
        self.calls.append(args)
        key = str(args[2])
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], 60]


class CountingRegisterService:
    def __init__(self) -> None:
        self.calls = 0

    def register(self, *_args: object) -> RegisterResponse:
        self.calls += 1
        return RegisterResponse(message=REGISTER_ACCEPTED_MESSAGE)


class RejectingLoginService:
    def __init__(self) -> None:
        self.calls = 0

    def login(self, *_args: object) -> AuthResult:
        self.calls += 1
        raise InvalidCredentialsError()


class CountingRefreshService:
    def __init__(self, configured: Settings, session_id: UUID) -> None:
        self.calls = 0
        self.csrf = CsrfService(configured)
        self.session_id = session_id
        self.csrf_token = self.csrf.issue(session_id)

    def refresh(self, *_args: object) -> AuthResult:
        self.calls += 1
        expires_at = datetime.now(UTC) + timedelta(hours=1)
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
            csrf_token=self.csrf_token,
            session_expires_at=expires_at,
        )


class LivePrincipalService:
    def __init__(self, user_id: int = 7) -> None:
        self.user = SimpleNamespace(id=user_id, status="ACTIVE", role="STAFF")
        self.session_id = uuid4()
        self.calls = 0
        self.thread_ids: list[int] = []

    def live_user(self, *_args: object) -> tuple[object, UUID]:
        self.calls += 1
        self.thread_ids.append(threading.get_ident())
        return self.user, self.session_id


def override_db() -> object:
    yield object()


@pytest.mark.anyio
async def test_fixed_window_allows_limit_and_returns_atomic_ttl() -> None:
    redis = FakeRedis([[1, 60], [5, 23], [6, 22]])
    limiter = RedisFixedWindowRateLimiter(redis, "retailops:test")  # type: ignore[arg-type]

    first = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60, now=0
    )
    fifth = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60, now=1
    )
    sixth = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60, now=2
    )

    assert first.allowed is True
    assert fifth.allowed is True
    assert sixth.allowed is False
    assert sixth.retry_after == 22
    assert all(call[1] == 1 for call in redis.calls)


@pytest.mark.anyio
async def test_fourth_request_is_429_when_policy_configured_for_three() -> None:
    configured = settings(register_rate_limit=3)
    redis = FakeRedis([[1, 60], [2, 59], [3, 58], [4, 57]])
    limiter = RedisFixedWindowRateLimiter(redis, "retailops:test")  # type: ignore[arg-type]
    service = CountingRegisterService()
    application = create_app(configured)
    application.state.rate_limiter = limiter
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("203.0.113.10", 4321)),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"staff-{index}@example.com",
                    "password": "valid-password",
                },
            )
            for index in range(4)
        ]

    assert [response.status_code for response in responses] == [202, 202, 202, 429]
    assert responses[-1].headers["retry-after"] == "57"
    assert responses[-1].json()["code"] == "RATE_LIMITED"
    assert service.calls == 3


@pytest.mark.anyio
async def test_default_registration_policy_allows_five_then_returns_429() -> None:
    configured = settings()
    redis = FakeRedis([[index, 61 - index] for index in range(1, 7)])
    limiter = RedisFixedWindowRateLimiter(redis, "retailops:test")  # type: ignore[arg-type]
    service = CountingRegisterService()
    application = create_app(configured)
    application.state.rate_limiter = limiter
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("203.0.113.20", 4321)),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"default-{index}@example.com",
                    "password": "valid-password",
                },
            )
            for index in range(6)
        ]

    assert [response.status_code for response in responses] == [
        202,
        202,
        202,
        202,
        202,
        429,
    ]
    assert int(responses[-1].headers["retry-after"]) > 0
    assert service.calls == 5


@pytest.mark.anyio
async def test_login_ip_policy_allows_five_then_blocks_sixth() -> None:
    configured = settings()
    redis = CountingRedis()
    service = RejectingLoginService()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("203.0.113.30", 4321)),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"ip-{index}@example.com",
                    "password": "wrong-password",
                },
            )
            for index in range(6)
        ]

    assert [response.status_code for response in responses] == [401] * 5 + [429]
    assert responses[-1].json()["code"] == "RATE_LIMITED"
    assert service.calls == 5
    assert sum("auth-login-ip" in key for key in redis.counts) == 1
    assert sum("auth-login-account" in key for key in redis.counts) == 6


@pytest.mark.anyio
async def test_login_account_policy_normalizes_case_and_blocks_twenty_first() -> None:
    configured = settings(login_ip_rate_limit=100)
    redis = CountingRedis()
    service = RejectingLoginService()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("203.0.113.31", 4321)),
        base_url="http://test",
    ) as client:
        responses = [
            await client.post(
                "/api/v1/auth/login",
                json={
                    "email": (
                        "CaseSensitive@Example.com"
                        if index % 2 == 0
                        else "casesensitive@example.com"
                    ),
                    "password": "wrong-password",
                },
            )
            for index in range(21)
        ]

    assert [response.status_code for response in responses] == [401] * 20 + [429]
    assert service.calls == 20
    account_keys = [key for key in redis.counts if "auth-login-account" in key]
    assert len(account_keys) == 1
    assert redis.counts[account_keys[0]] == 21
    assert "casesensitive" not in account_keys[0].casefold()


@pytest.mark.anyio
async def test_login_spoofed_forwarded_headers_do_not_change_ip_bucket() -> None:
    configured = settings(login_ip_rate_limit=1)
    redis = CountingRedis()
    service = RejectingLoginService()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("198.51.100.30", 4321)),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/v1/auth/login",
            headers={
                "X-Forwarded-For": "1.1.1.1",
                "X-Real-IP": "1.1.1.1",
                "Forwarded": "for=1.1.1.1",
            },
            json={"email": "first@example.com", "password": "wrong-password"},
        )
        second = await client.post(
            "/api/v1/auth/login",
            headers={
                "X-Forwarded-For": "2.2.2.2",
                "X-Real-IP": "2.2.2.2",
                "Forwarded": "for=2.2.2.2",
            },
            json={"email": "second@example.com", "password": "wrong-password"},
        )

    assert first.status_code == 401
    assert second.status_code == 429


@pytest.mark.anyio
async def test_refresh_session_policy_allows_ten_then_blocks_eleventh() -> None:
    configured = settings(cors_origins="http://127.0.0.1:5173")
    session_id = uuid4()
    service = CountingRefreshService(configured, session_id)
    csrf_token = service.csrf_token
    redis = CountingRedis()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        client.cookies.set(configured.refresh_cookie_name, "refresh-token")
        client.cookies.set(configured.csrf_cookie_name, csrf_token)
        responses = [
            await client.post(
                "/api/v1/auth/refresh",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "X-CSRF-Token": csrf_token,
                },
            )
            for _index in range(11)
        ]

    assert [response.status_code for response in responses] == [200] * 10 + [429]
    assert service.calls == 10
    session_keys = [key for key in redis.counts if "auth-refresh-session" in key]
    assert len(session_keys) == 1
    assert str(session_id) not in session_keys[0]


@pytest.mark.anyio
async def test_invalid_refresh_proofs_share_the_client_ip_fallback_quota() -> None:
    configured = settings(
        cors_origins="http://127.0.0.1:5173",
        refresh_rate_limit=1,
    )
    service = CountingRefreshService(configured, uuid4())
    redis = CountingRedis()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=application,
            client=("203.0.113.32", 4321),
        ),
        base_url="http://test",
    ) as client:
        client.cookies.set(
            configured.csrf_cookie_name,
            "attacker-selected-proof-1",
        )
        first = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "X-CSRF-Token": "attacker-selected-proof-1",
            },
        )
        client.cookies.set(
            configured.csrf_cookie_name,
            "attacker-selected-proof-2",
        )
        second = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "X-CSRF-Token": "attacker-selected-proof-2",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert service.calls == 1
    fallback_keys = [key for key in redis.counts if "auth-refresh-unbound-ip" in key]
    assert len(fallback_keys) == 1


def _business_test_app(configured: Settings, redis: object) -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    service = LivePrincipalService()
    application.state.test_live_principal_service = service
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service

    @application.get("/business")
    async def business(
        _principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    ) -> dict[str, bool]:
        return {"ok": True}

    return application


@pytest.mark.anyio
async def test_business_quota_is_per_active_user() -> None:
    configured = settings(business_rate_limit=2)
    application = _business_test_app(configured, CountingRedis())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        responses = [
            await client.get(
                "/business", headers={"Authorization": "Bearer valid-token"}
            )
            for _index in range(3)
        ]

    assert [response.status_code for response in responses] == [200, 200, 429]


@pytest.mark.anyio
async def test_business_mysql_authentication_runs_off_the_event_loop() -> None:
    application = _business_test_app(settings(), CountingRedis())
    event_loop_thread = threading.get_ident()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/business", headers={"Authorization": "Bearer valid-token"}
        )

    service = application.state.test_live_principal_service
    assert response.status_code == 200
    assert service.calls == 1
    assert service.thread_ids == [service.thread_ids[0]]
    assert service.thread_ids[0] != event_loop_thread


@pytest.mark.anyio
async def test_business_redis_outage_fails_open_after_authentication() -> None:
    application = _business_test_app(settings(), UnavailableRedis())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/business", headers={"Authorization": "Bearer valid-token"}
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_limiter", [None, object()], ids=["missing", "wrong-type"]
)
async def test_business_limiter_lifecycle_error_is_not_treated_as_redis_outage(
    invalid_limiter: object | None,
) -> None:
    application = _business_test_app(settings(), CountingRedis())
    if invalid_limiter is None:
        del application.state.rate_limiter
    else:
        application.state.rate_limiter = invalid_limiter
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/business", headers={"Authorization": "Bearer valid-token"}
        )

    service = application.state.test_live_principal_service
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    assert service.calls == 1


@pytest.mark.anyio
async def test_forged_forwarded_headers_do_not_change_direct_client_bucket() -> None:
    configured = settings(register_rate_limit=1)
    redis = FakeRedis([[1, 60], [2, 59]])
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        redis, "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = CountingRegisterService
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=("198.51.100.8", 1234)),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/v1/auth/register",
            headers={"X-Real-IP": "1.1.1.1", "X-Forwarded-For": "1.1.1.1"},
            json={"email": "one@example.com", "password": "valid-password"},
        )
        second = await client.post(
            "/api/v1/auth/register",
            headers={"X-Real-IP": "2.2.2.2", "X-Forwarded-For": "2.2.2.2"},
            json={"email": "two@example.com", "password": "valid-password"},
        )
    assert first.status_code == 202
    assert second.status_code == 429
    assert redis.calls[0][2] == redis.calls[1][2]


@pytest.mark.anyio
async def test_redis_unavailable_fails_closed_before_service() -> None:
    configured = settings()
    service = CountingRegisterService()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "one@example.com", "password": "valid-password"},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert service.calls == 0
    assert "redis" not in response.text.casefold()


@pytest.mark.anyio
async def test_login_redis_unavailable_fails_closed_before_password_check() -> None:
    configured = settings()
    service = RejectingLoginService()
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "staff@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert service.calls == 0
    assert "redis" not in response.text.casefold()


@pytest.mark.anyio
async def test_refresh_redis_unavailable_fails_closed_before_token_rotation() -> None:
    configured = settings(cors_origins="http://127.0.0.1:5173")
    service = CountingRefreshService(configured, uuid4())
    application = create_app(configured)
    application.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )
    application.dependency_overrides[get_settings] = lambda: configured
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        client.cookies.set(configured.csrf_cookie_name, service.csrf_token)
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "X-CSRF-Token": service.csrf_token,
            },
        )

    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert service.calls == 0
    assert "redis" not in response.text.casefold()


@pytest.mark.anyio
async def test_missing_client_identity_fails_closed() -> None:
    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    request = Request(scope)
    with pytest.raises(DependencyUnavailableError):
        await enforce_registration_rate_limit(
            request,
            RedisFixedWindowRateLimiter(FakeRedis(), "retailops:test"),  # type: ignore[arg-type]
            settings(),
        )


def test_rate_limit_configuration_validation() -> None:
    with pytest.raises(ValidationError):
        settings(redis_url=SecretStr("http://redis:6379"))
    with pytest.raises(ValidationError):
        settings(redis_pool_size=0)
    with pytest.raises(ValidationError):
        settings(register_rate_window_seconds=0)
    with pytest.raises(ValidationError):
        settings(login_account_rate_limit=0)
    assert settings().login_ip_rate_limit == 5
    assert settings().login_account_rate_limit == 20
    assert settings().refresh_rate_limit == 10
    assert settings().business_rate_limit == 120


def test_missing_lifespan_rate_limiter_fails_closed() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "app": create_app(settings()),
        }
    )
    with pytest.raises(DependencyUnavailableError):
        get_rate_limiter(request)
