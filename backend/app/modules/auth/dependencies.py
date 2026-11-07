"""FastAPI dependencies for live MySQL-backed authentication."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthenticatedError
from app.db.session import get_db_session
from app.modules.auth.models import User, UserRole
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


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentPrincipal:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise UnauthenticatedError()
    user, session_id = service.live_user(session, credentials.credentials)
    return CurrentPrincipal(user=user, session_id=session_id)


def require_admin(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> CurrentPrincipal:
    """Require an authenticated ACTIVE user with the ADMIN role."""
    if principal.user.role != UserRole.ADMIN:
        raise ForbiddenError()
    return principal

