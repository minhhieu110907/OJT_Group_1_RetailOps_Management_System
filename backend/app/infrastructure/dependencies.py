"""FastAPI dependencies for shared infrastructure policies."""

from typing import Annotated

from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.exceptions import DependencyUnavailableError, RateLimitedError
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter


def get_rate_limiter(request: Request) -> RedisFixedWindowRateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if not isinstance(limiter, RedisFixedWindowRateLimiter):
        raise DependencyUnavailableError()
    return limiter


async def enforce_registration_rate_limit(
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Fail closed before registration business work when identity/Redis fails."""
    client = request.client
    if client is None or not client.host:
        raise DependencyUnavailableError()
    try:
        result = await limiter.check(
            policy="staff-registration",
            identity=client.host,
            limit=settings.register_rate_limit,
            window_seconds=settings.register_rate_window_seconds,
        )
    except (RedisError, OSError, TimeoutError) as error:
        raise DependencyUnavailableError() from error
    if not result.allowed:
        raise RateLimitedError(result.retry_after)
