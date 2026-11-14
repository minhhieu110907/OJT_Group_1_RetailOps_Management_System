"""FastAPI dependencies for live MySQL-backed authentication."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, RateLimitedError, UnauthenticatedError
from app.db.session import get_db_session
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentPrincipal:
    user: User
    session_id: UUID


def get_auth_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(settings)


def authenticate_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentPrincipal:
    """Authenticate against the synchronous MySQL session in a worker thread."""
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise UnauthenticatedError()
    user, session_id = service.live_user(session, credentials.credentials)
    return CurrentPrincipal(user=user, session_id=session_id)


async def get_current_principal(
    authenticated: Annotated[CurrentPrincipal, Depends(authenticate_current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
) -> CurrentPrincipal:
    """Apply the asynchronous Redis quota after MySQL authentication succeeds."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if not isinstance(limiter, RedisFixedWindowRateLimiter):
        raise RuntimeError("Business rate limiter is not initialized")
    try:
        result = await limiter.check(
            policy="business-user",
            identity=str(authenticated.user.id),
            limit=settings.business_rate_limit,
            window_seconds=settings.business_rate_window_seconds,
        )
    except (RedisError, OSError, TimeoutError):
        return authenticated
    if not result.allowed:
        raise RateLimitedError(result.retry_after)
    return authenticated


def get_current_active_user(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> User:
    """Return the active user from the verified current principal."""
    if principal.user.status != UserStatus.ACTIVE:
        raise ForbiddenError("Tài khoản chưa được kích hoạt hoặc không hợp lệ.")
    return principal.user


def require_active_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Verify that the active caller possesses the ADMIN role."""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Chỉ quản trị viên mới có quyền thực hiện thao tác.")
    return current_user
