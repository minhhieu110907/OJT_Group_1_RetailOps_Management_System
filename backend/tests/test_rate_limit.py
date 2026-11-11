"""Unit and API tests for Redis registration rate limiting."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from redis.exceptions import ConnectionError
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.exceptions import DependencyUnavailableError
from app.db.session import get_db_session
from app.infrastructure.dependencies import (
    enforce_registration_rate_limit,
    get_rate_limiter,
)
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.schemas import RegisterResponse
from app.modules.auth.service import REGISTER_ACCEPTED_MESSAGE


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


class CountingRegisterService:
    def __init__(self) -> None:
        self.calls = 0

    def register(self, *_args: object) -> RegisterResponse:
        self.calls += 1
        return RegisterResponse(message=REGISTER_ACCEPTED_MESSAGE)


def override_db() -> object:
    yield object()


@pytest.mark.anyio
async def test_fixed_window_allows_limit_and_returns_atomic_ttl() -> None:
    redis = FakeRedis([[1, 60], [5, 23], [6, 22]])
    limiter = RedisFixedWindowRateLimiter(redis, "retailops:test")  # type: ignore[arg-type]

    first = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60
    )
    fifth = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60
    )
    sixth = await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60
    )

    assert first.allowed is True
    assert fifth.allowed is True
    assert sixth.allowed is False
    assert sixth.retry_after == 22
    assert all(call[1] == 1 for call in redis.calls)


@pytest.mark.anyio
async def test_bucket_key_is_anchored_to_first_request_not_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requests straddling a minute boundary must share one bucket and full TTL."""
    redis = FakeRedis([[1, 60], [2, 59]])
    limiter = RedisFixedWindowRateLimiter(redis, "retailops:test")  # type: ignore[arg-type]

    # 0.1s before a minute boundary (1_800_000_000 is divisible by 60).
    monkeypatch.setattr("time.time", lambda: 1_799_999_999.9)
    await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60
    )
    # 0.1s after the same boundary.
    monkeypatch.setattr("time.time", lambda: 1_800_000_000.1)
    await limiter.check(
        policy="register", identity="203.0.113.1", limit=5, window_seconds=60
    )

    first_key, second_key = redis.calls[0][2], redis.calls[1][2]
    assert first_key == second_key
    assert str(first_key).startswith("retailops:test:register:")
    assert all(call[3] == 60 for call in redis.calls)


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
