"""SQLAlchemy queries for authentication use cases."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import AuthSession, RefreshToken, User


class AuthRepository:
    def find_user_by_email(self, session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email_normalized == email))

    def add_session(
        self, session: Session, auth_session: AuthSession, refresh: RefreshToken
    ) -> None:
        session.add_all((auth_session, refresh))

    def find_refresh(self, session: Session, digest: bytes) -> RefreshToken | None:
        return session.scalar(
            select(RefreshToken).where(RefreshToken.token_digest == digest)
        )

    def lock_refresh(self, session: Session, digest: bytes) -> RefreshToken | None:
        return session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_digest == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def lock_session(self, session: Session, session_id: bytes) -> AuthSession | None:
        return session.scalar(
            select(AuthSession).where(AuthSession.id == session_id).with_for_update()
        )

    def find_live_principal(
        self, session: Session, session_id: bytes, user_id: int, now: datetime
    ) -> User | None:
        return session.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                User.status == "ACTIVE",
            )
        )

    def find_live_session_by_refresh(
        self, session: Session, digest: bytes, now: datetime
    ) -> AuthSession | None:
        return session.scalar(
            select(AuthSession)
            .join(RefreshToken, RefreshToken.session_id == AuthSession.id)
            .join(User, User.id == AuthSession.user_id)
            .where(
                RefreshToken.token_digest == digest,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                User.status == "ACTIVE",
            )
        )
