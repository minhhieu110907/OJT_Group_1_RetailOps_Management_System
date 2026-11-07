"""FastAPI router for Admin in-app notification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.notifications.dependencies import (
    get_notification_service,
    require_active_admin,
)
from app.modules.notifications.schemas import (
    EmptyPatchRequest,
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
)
def list_admin_notifications(
    principal: Annotated[CurrentPrincipal, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    
    return service.list_for_admin(
        session,
        principal.user.id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
)
def get_unread_notification_count(
    principal: Annotated[CurrentPrincipal, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> UnreadCountResponse:
    
    return service.count_unread(session, principal.user.id)


@router.patch(
    "/read-all",
    response_model=MarkAllReadResponse,
    status_code=status.HTTP_200_OK,
)
def mark_all_notifications_read(
    _payload: Annotated[EmptyPatchRequest, Body()],
    principal: Annotated[CurrentPrincipal, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> MarkAllReadResponse:
  
    return service.mark_all_read(session, principal.user.id)


@router.patch(
    "/{id}/read",
    response_model=NotificationRead,
    status_code=status.HTTP_200_OK,
)
def mark_notification_read(
    id: Annotated[int, Path(ge=1)],
    _payload: Annotated[EmptyPatchRequest, Body()],
    principal: Annotated[CurrentPrincipal, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationRead:
    
    return service.mark_read(session, principal.user.id, id)
