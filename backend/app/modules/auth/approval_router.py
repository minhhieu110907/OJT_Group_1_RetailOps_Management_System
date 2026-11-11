"""ADMIN-only HTTP boundary for Staff approval decisions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.approval_service import StaffApprovalService
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import ApprovalStatus, User
from app.modules.auth.schemas import ApprovalPage, ApprovalRead, RejectRequest

router = APIRouter(prefix="/staff-approvals", tags=["staff-approvals"])


def get_staff_approval_service() -> StaffApprovalService:
    return StaffApprovalService()


@router.get("", response_model=ApprovalPage)
def list_staff_approvals(
    session: Annotated[Session, Depends(get_db_session)],
    _admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffApprovalService, Depends(get_staff_approval_service)],
    status: Annotated[ApprovalStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ApprovalPage:
    return service.list(
        session,
        status=status.value if status is not None else None,
        page=page,
        page_size=page_size,
    )


@router.post("/{id}/approve", response_model=ApprovalRead)
def approve_staff(
    id: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_db_session)],
    admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffApprovalService, Depends(get_staff_approval_service)],
) -> ApprovalRead:
    return service.decide(
        session,
        actor_id=admin.id,
        approval_id=id,
        decision=ApprovalStatus.APPROVED,
        reason=None,
    )


@router.post("/{id}/reject", response_model=ApprovalRead)
def reject_staff(
    id: Annotated[int, Path(ge=1)],
    payload: RejectRequest,
    session: Annotated[Session, Depends(get_db_session)],
    admin: Annotated[User, Depends(require_active_admin)],
    service: Annotated[StaffApprovalService, Depends(get_staff_approval_service)],
) -> ApprovalRead:
    return service.decide(
        session,
        actor_id=admin.id,
        approval_id=id,
        decision=ApprovalStatus.REJECTED,
        reason=payload.reason,
    )
