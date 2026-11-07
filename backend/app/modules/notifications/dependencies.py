"""FastAPI dependencies for Admin notification endpoints and request-level UoW."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService


def get_notification_service() -> NotificationService:
    """Construct a stateless NotificationService with its SQLAlchemy repository."""
    return NotificationService(repository=NotificationRepository())


def require_active_admin(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> CurrentPrincipal:
    """Enforce that the authenticated ACTIVE principal has the ADMIN role."""
    if principal.user.role != "ADMIN":
        raise AppException(
            code="FORBIDDEN",
            message="Admin privileges are required",
            status_code=403,
        )
    return principal


def get_notification_uow_session(
    session: Annotated[Session, Depends(get_db_session)],
) -> Generator[Session]:
    """Request-scoped Unit of Work that commits on success for write HTTP endpoints."""
    yield session
    session.commit()
