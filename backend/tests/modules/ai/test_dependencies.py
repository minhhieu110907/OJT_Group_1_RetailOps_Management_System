"""Verify the AI binding is wired to the live Auth dependency."""

import asyncio
from inspect import signature
from types import SimpleNamespace
from typing import Annotated, get_args
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.params import Depends

from app.core.config import Settings, get_settings
from app.infrastructure.rate_limit import RateLimitResult, RedisFixedWindowRateLimiter
from app.modules.ai.dependencies import get_bound_tool_request
from app.modules.ai.tool_executor import BoundToolRequest
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    authenticate_current_principal,
    get_current_principal,
)
from app.modules.auth.models import UserRole, UserStatus


def test_http_factory_depends_on_live_principal_and_is_request_scoped():
    parameter = signature(get_bound_tool_request).parameters["principal"]
    assert any(
        isinstance(item, Depends) and item.dependency is get_current_principal
        for item in get_args(parameter.annotation)
    )
    principal = CurrentPrincipal(
        user=SimpleNamespace(id=7, role=UserRole.ADMIN, status=UserStatus.ACTIVE),
        session_id=uuid4(),
    )
    settings = Settings(
        _env_file=None,
        db_host="127.0.0.1",
        db_name="unit_test_only",
        db_user="unit_test_user",
        db_password="not-a-real-password",
    )
    first = get_bound_tool_request(principal, settings)
    second = get_bound_tool_request(principal, settings)
    assert first.context.actor_id == 7
    assert first.context.request_id != second.context.request_id
    assert first.budget is not second.budget


def test_real_asgi_request_binds_authenticated_principal_not_spoofed_body():
    app = FastAPI()
    principal = CurrentPrincipal(
        user=SimpleNamespace(id=7, role=UserRole.ADMIN, status=UserStatus.ACTIVE),
        session_id=uuid4(),
    )
    settings = Settings(
        _env_file=None,
        db_host="127.0.0.1",
        db_name="unit_test_only",
        db_user="unit_test_user",
        db_password="not-a-real-password",
    )

    async def authenticated_principal():
        return principal

    async def configured_settings():
        return settings

    class AllowedLimiter(RedisFixedWindowRateLimiter):
        async def check(self, **_kwargs):
            return RateLimitResult(allowed=True, count=1, retry_after=60)

    app.state.rate_limiter = AllowedLimiter(None, "ai-test")
    app.dependency_overrides[authenticate_current_principal] = authenticated_principal
    app.dependency_overrides[get_settings] = configured_settings

    @app.post("/ai-binding")
    async def binding(
        bound: Annotated[BoundToolRequest, Depends(get_bound_tool_request)],
    ):
        return {
            "actor_id": bound.context.actor_id,
            "request_id": bound.context.request_id,
        }

    async def send_requests():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            first = await client.post("/ai-binding", json={"actor_id": 999})
            second = await client.post("/ai-binding", json={"actor_id": 999})
        return first, second

    first, second = asyncio.run(send_requests())
    assert first.status_code == second.status_code == 200
    assert first.json()["actor_id"] == second.json()["actor_id"] == 7
    assert first.json()["request_id"] != second.json()["request_id"]
