"""HTTP boundary for the RetailOps AI Assistant endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.exceptions import DependencyUnavailableError, RateLimitedError
from app.db.session import get_session_factory
from app.infrastructure.dependencies import get_rate_limiter
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.modules.ai.concurrency import RedisAIConcurrencyGuard
from app.modules.ai.dependencies import get_bound_tool_request
from app.modules.ai.gemini_provider import (
    GeminiProvider,
    GeminiProviderError,
    LLMProvider,
)
from app.modules.ai.orchestrator import AIOrchestrator, SessionFactory
from app.modules.ai.schemas import AIAskResponse, AIQueryRequest
from app.modules.ai.tool_executor import BoundToolRequest
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_concurrency_guard(request: Request) -> RedisAIConcurrencyGuard:
    guard = getattr(request.app.state, "ai_concurrency_guard", None)
    if not isinstance(guard, RedisAIConcurrencyGuard):
        raise DependencyUnavailableError()
    return guard


def get_ai_session_factory() -> SessionFactory:
    return get_session_factory()


def get_ai_provider(settings: Settings) -> LLMProvider:
    if settings.gemini_api_key is None:
        raise GeminiProviderError(
            "Chưa cấu hình RETAILOPS_GEMINI_API_KEY cho dịch vụ AI."
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
        timeout_seconds=settings.gemini_timeout_seconds,
    )


def get_ai_orchestrator(
    settings: Annotated[Settings, Depends(get_settings)],
    session_factory: Annotated[SessionFactory, Depends(get_ai_session_factory)],
) -> AIOrchestrator:
    return AIOrchestrator(
        session_factory=session_factory,
        provider_factory=lambda: get_ai_provider(settings),
        gemini_timeout_seconds=settings.gemini_timeout_seconds,
    )


async def enforce_ai_rate_limit(
    admin_user: Annotated[User, Depends(require_active_admin)],
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Enforce 10 AI reqs/min per authenticated ADMIN; fail closed on Redis error."""
    try:
        result = await limiter.check(
            policy="ai-query-user",
            identity=str(admin_user.id),
            limit=settings.ai_rate_limit,
            window_seconds=settings.ai_rate_window_seconds,
        )
    except (RedisError, OSError, TimeoutError) as error:
        raise DependencyUnavailableError() from error
    if not result.allowed:
        raise RateLimitedError(result.retry_after)


async def enforce_ai_concurrency(
    admin_user: Annotated[User, Depends(require_active_admin)],
    guard: Annotated[RedisAIConcurrencyGuard, Depends(get_ai_concurrency_guard)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[None]:
    """Enforce 1 in-flight AI request/admin + global cap, releasing in finally."""
    lease = await guard.acquire(
        user_id=admin_user.id,
        max_concurrent=settings.ai_max_concurrent_requests,
        ttl_seconds=settings.ai_concurrency_lock_ttl_seconds,
    )
    try:
        yield
    finally:
        await guard.release(lease)


@router.post(
    "/query",
    response_model=AIAskResponse,
    status_code=status.HTTP_200_OK,
)
async def query_ai_assistant(
    payload: AIQueryRequest,
    _admin: Annotated[User, Depends(require_active_admin)],
    _rate_limit: Annotated[None, Depends(enforce_ai_rate_limit)],
    _concurrency: Annotated[None, Depends(enforce_ai_concurrency)],
    bound: Annotated[BoundToolRequest, Depends(get_bound_tool_request)],
    orchestrator: Annotated[AIOrchestrator, Depends(get_ai_orchestrator)],
) -> AIAskResponse:
    """Answer an ADMIN operational question via hybrid routing + Gemini + Executor."""
    return await orchestrator.handle_query(message=payload.message, bound=bound)
