"""Staff approval application service and transaction owner."""

from datetime import UTC

from sqlalchemy.orm import Session

from app.core.exceptions import (
    DomainValidationError,
    ForbiddenError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.core.pagination import Page
from app.modules.auth.approval_repository import StaffApprovalRepository
from app.modules.auth.models import ApprovalStatus, UserRole, UserStatus
from app.modules.auth.schemas import ApprovalListItemRead, ApprovalRead
from app.modules.auth.service import utc_now_naive
from app.modules.outbox.writer import OutboxWriter


class StaffApprovalService:
    """List and atomically decide Staff approval requests."""

    def __init__(
        self,
        repository: StaffApprovalRepository | None = None,
        outbox_writer: OutboxWriter | None = None,
    ) -> None:
        self.repository = repository or StaffApprovalRepository()
        self.outbox_writer = outbox_writer or OutboxWriter()

    def list(
        self,
        session: Session,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ) -> Page[ApprovalListItemRead]:
        items, total = self.repository.list_page(
            session, status=status, page=page, page_size=page_size
        )
        return Page(
            items=tuple(
                ApprovalListItemRead(
                    **ApprovalRead.model_validate(approval).model_dump(),
                    email=email,
                )
                for approval, email in items
            ),
            total=total,
            page=page,
            page_size=page_size,
        )

    def decide(
        self,
        session: Session,
        *,
        actor_id: int,
        approval_id: int,
        decision: str,
        reason: str | None,
    ) -> ApprovalRead:
        try:
            actor = self.repository.find_actor(session, actor_id)
            if (
                actor is None
                or actor.role != UserRole.ADMIN
                or actor.status != UserStatus.ACTIVE
            ):
                raise ForbiddenError()
            if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
                raise DomainValidationError("Quyết định duyệt không hợp lệ.")
            if decision == ApprovalStatus.REJECTED:
                reason = reason.strip() if reason is not None else ""
                if not 1 <= len(reason) <= 500:
                    raise DomainValidationError(
                        "Lý do từ chối phải có độ dài từ 1 đến 500 ký tự."
                    )
            if decision == ApprovalStatus.APPROVED and reason is not None:
                raise DomainValidationError("Duyệt Staff không nhận lý do từ chối.")

            approval = self.repository.lock_approval(session, approval_id)
            if approval is None:
                raise ResourceNotFoundError("Không tìm thấy yêu cầu duyệt Staff.")
            user = self.repository.lock_user(session, approval.user_id)
            if user is None:
                raise InvalidStateError()
            if (
                approval.status != ApprovalStatus.PENDING
                or user.role != UserRole.STAFF
                or user.status != UserStatus.PENDING_APPROVAL
                or approval.user_id != user.id
            ):
                raise InvalidStateError()

            now = utc_now_naive()
            approval.status = decision
            approval.decided_by = actor_id
            approval.decided_at = now
            approval.decision_reason = reason
            user.status = (
                UserStatus.ACTIVE
                if decision == ApprovalStatus.APPROVED
                else UserStatus.REJECTED
            )
            user.updated_at = now
            self.outbox_writer.append(
                session,
                subject_user_id=user.id,
                event_type=(
                    "STAFF_APPROVED"
                    if decision == ApprovalStatus.APPROVED
                    else "STAFF_REJECTED"
                ),
                payload={
                    "schema_version": 1,
                    "approval_request_id": approval.id,
                    "actor_id": actor_id,
                },
                available_at_utc=now.replace(tzinfo=UTC),
            )
            response = ApprovalRead.model_validate(approval)
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise
