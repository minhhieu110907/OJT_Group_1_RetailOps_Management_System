"""ADMIN Staff account management and authenticated self-profile endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.account_service import SelfProfileService, StaffAccountService
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_active_admin,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ProfileRead,
    ProfileUpdateRequest,
    StaffAccountPage,
    StaffAccountRead,
)

admin_router = APIRouter(prefix="/admin/staff", tags=["staff-accounts"])
profile_router = APIRouter(prefix="/users", tags=["self-profile"])


def get_staff_account_service() -> StaffAccountService:
    return StaffAccountService()


@admin_router.get("", response_model=StaffAccountPage)
def list_staff_accounts(
    session: Annotated[Session, Depends(get_db_session)],
    _admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffAccountService, Depends(get_staff_account_service)],
    status: Annotated[Literal["ACTIVE", "LOCKED"] | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> StaffAccountPage:
    return service.list_staff(
        session,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


@admin_router.post("/{user_id}/lock", response_model=StaffAccountRead)
def lock_staff_account(
    user_id: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_db_session)],
    admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffAccountService, Depends(get_staff_account_service)],
    response: Response,
) -> StaffAccountRead:
    response.headers["Cache-Control"] = "no-store"
    return service.transition(
        session, actor_id=admin.id, target_user_id=user_id, action="LOCK"
    )


@admin_router.post("/{user_id}/unlock", response_model=StaffAccountRead)
def unlock_staff_account(
    user_id: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_db_session)],
    admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffAccountService, Depends(get_staff_account_service)],
    response: Response,
) -> StaffAccountRead:
    response.headers["Cache-Control"] = "no-store"
    return service.transition(
        session, actor_id=admin.id, target_user_id=user_id, action="UNLOCK"
    )


@profile_router.get("/me", response_model=ProfileRead)
def get_my_profile(
    session: Annotated[Session, Depends(get_db_session)],
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    response: Response,
) -> ProfileRead:
    response.headers["Cache-Control"] = "no-store"
    return SelfProfileService.get_profile(session, actor_id=principal.user.id)


@profile_router.patch("/me", response_model=ProfileRead)
def patch_my_profile(
    payload: ProfileUpdateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    response: Response,
) -> ProfileRead:
    response.headers["Cache-Control"] = "no-store"
    return SelfProfileService.update_profile(
        session,
        actor_id=principal.user.id,
        session_id=principal.session_id.bytes,
        full_name=payload.full_name,
    )
