"""Staff administration and self-service profile operations (Bonus Sprint 3)."""

from __future__ import annotations

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ForbiddenError,
    InvalidStateError,
    ResourceNotFoundError,
    SessionInvalidError,
)
from app.modules.auth.models import (
    AuthSession,
    StaffAccountEvent,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.schemas import (
    ProfileRead,
    StaffAccountPage,
    StaffAccountRead,
    normalize_full_name,
)
from app.modules.auth.service import utc_now_naive


class StaffAccountService:
    """Own admin status transitions, session revocation and account audit."""

    def list_staff(
        self,
        session: Session,
        *,
        status: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> StaffAccountPage:
        criteria = [User.role == UserRole.STAFF]
        if status is None:
            criteria.append(User.status.in_((UserStatus.ACTIVE, UserStatus.LOCKED)))
        else:
            if status not in (UserStatus.ACTIVE, UserStatus.LOCKED):
                raise InvalidStateError("Bộ lọc trạng thái không hợp lệ.")
            criteria.append(User.status == status)
        if search:
            # Explicit parameter binding; escape LIKE metacharacters.
            term = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            if term:
                pattern = f"%{term}%"
                criteria.append(
                    or_(
                        User.email_normalized.ilike(pattern, escape="\\"),
                        User.full_name.ilike(pattern, escape="\\"),
                    )
                )
        total = int(
            session.scalar(select(func.count(User.id)).where(*criteria)) or 0
        )
        users = session.scalars(
            select(User)
            .where(*criteria)
            .order_by(User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return StaffAccountPage(
            items=[StaffAccountRead.model_validate(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
        )

    def transition(
        self,
        session: Session,
        *,
        actor_id: int,
        target_user_id: int,
        action: str,
    ) -> StaffAccountRead:
        try:
            if action not in ("LOCK", "UNLOCK"):
                raise InvalidStateError()
            actor = session.scalar(select(User).where(User.id == actor_id))
            if (
                actor is None
                or actor.role != UserRole.ADMIN
                or actor.status != UserStatus.ACTIVE
            ):
                raise ForbiddenError()
            # Canonical locking: target User first, then mutate its sessions.
            user = session.scalar(
                select(User)
                .where(User.id == target_user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user is None or user.role != UserRole.STAFF:
                raise ResourceNotFoundError("Không tìm thấy tài khoản Staff.")
            expected = UserStatus.ACTIVE if action == "LOCK" else UserStatus.LOCKED
            if user.status != expected:
                raise InvalidStateError("Trạng thái Staff không cho phép thao tác.")
            now = utc_now_naive()
            user.status = (
                UserStatus.LOCKED if action == "LOCK" else UserStatus.ACTIVE
            )
            user.updated_at = now
            if action == "LOCK":
                session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.user_id == user.id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            session.add(
                StaffAccountEvent(
                    actor_id=actor_id,
                    target_user_id=user.id,
                    action=action,
                    created_at=now,
                )
            )
            response = StaffAccountRead.model_validate(user)
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise


class SelfProfileService:
    """Self-only profile reads/updates using server-resolved identity."""

    @staticmethod
    def get_profile(session: Session, *, actor_id: int) -> ProfileRead:
        user = session.get(User, actor_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise SessionInvalidError()
        return ProfileRead.model_validate(user)

    @staticmethod
    def update_profile(
        session: Session,
        *,
        actor_id: int,
        session_id: bytes,
        full_name: str | None,
    ) -> ProfileRead:
        try:
            normalized = normalize_full_name(full_name)
            user = session.scalar(
                select(User)
                .where(User.id == actor_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user is None or user.status != UserStatus.ACTIVE:
                raise SessionInvalidError()
            now = utc_now_naive()
            live = session.scalar(
                select(AuthSession.id).where(
                    AuthSession.id == session_id,
                    AuthSession.user_id == user.id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            if live is None:
                raise SessionInvalidError()
            user.full_name = normalized
            user.updated_at = now
            response = ProfileRead.model_validate(user)
            session.commit()
            return response
        except Exception:
            session.rollback()
            raise
