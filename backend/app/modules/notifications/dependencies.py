"""FastAPI dependencies for Admin notification endpoints."""

from typing import Annotated

from fastapi import Depends

from app.core.exceptions import AppException
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import UserRole
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService


def get_notification_service() -> NotificationService:

    return NotificationService(repository=NotificationRepository())


def require_active_admin(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> CurrentPrincipal:

    if principal.user.role != UserRole.ADMIN:
        raise AppException(
            code="FORBIDDEN",
            message="Admin privileges are required",
            status_code=403,
        )
    return principal
