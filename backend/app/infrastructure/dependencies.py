"""FastAPI dependencies for shared infrastructure policies."""

from typing import Annotated

from fastapi import Depends, Header, Request
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.exceptions import DependencyUnavailableError, RateLimitedError
from app.infrastructure.rate_limit import RateLimitResult, RedisFixedWindowRateLimiter
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.schemas import LoginRequest
from app.modules.auth.security import normalize_email
from app.modules.auth.service import AuthService


def get_rate_limiter(request: Request) -> RedisFixedWindowRateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if not isinstance(limiter, RedisFixedWindowRateLimiter):
        raise DependencyUnavailableError()
    return limiter


def _client_ip(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        raise DependencyUnavailableError()
    return client.host


async def _check_fail_closed(
    limiter: RedisFixedWindowRateLimiter,
    *,
    policy: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    try:
        return await limiter.check(
            policy=policy,
            identity=identity,
            limit=limit,
            window_seconds=window_seconds,
        )
    except (RedisError, OSError, TimeoutError) as error:
        raise DependencyUnavailableError() from error


async def enforce_registration_rate_limit(
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Fail closed before registration business work when identity/Redis fails."""
    result = await _check_fail_closed(
        limiter,
        policy="staff-registration",
        identity=_client_ip(request),
        limit=settings.register_rate_limit,
        window_seconds=settings.register_rate_window_seconds,
    )
    if not result.allowed:
        raise RateLimitedError(result.retry_after)


async def enforce_login_rate_limit(
    payload: LoginRequest,
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Fail closed while applying independent IP and normalized-account quotas."""
    ip_result = await _check_fail_closed(
        limiter,
        policy="auth-login-ip",
        identity=_client_ip(request),
        limit=settings.login_ip_rate_limit,
        window_seconds=settings.login_ip_rate_window_seconds,
    )
    account_result = await _check_fail_closed(
        limiter,
        policy="auth-login-account",
        identity=normalize_email(str(payload.email)),
        limit=settings.login_account_rate_limit,
        window_seconds=settings.login_account_rate_window_seconds,
    )
    blocked = [result for result in (ip_result, account_result) if not result.allowed]
    if blocked:
        raise RateLimitedError(max(result.retry_after for result in blocked))


async def enforce_refresh_rate_limit(
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Rate limit a trusted signed session, or an unbound attempt by client IP."""
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    session_id = None
    if csrf_header and csrf_cookie:
        try:
            session_id = service.csrf.session_binding(csrf_header)
            service.csrf.verify_pair(
                header_token=csrf_header,
                cookie_token=csrf_cookie,
                expected_session_id=session_id,
            )
        except ValueError:
            session_id = None
    if session_id is None:
        policy = "auth-refresh-unbound-ip"
        identity = _client_ip(request)
    else:
        policy = "auth-refresh-session"
        identity = str(session_id)
    result = await _check_fail_closed(
        limiter,
        policy=policy,
        identity=identity,
        limit=settings.refresh_rate_limit,
        window_seconds=settings.refresh_rate_window_seconds,
    )
    if not result.allowed:
        raise RateLimitedError(result.retry_after)
