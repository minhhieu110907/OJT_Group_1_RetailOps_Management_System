"""Service layer for STAFF self-service password reset (T04AA1C)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError, UnauthenticatedError
from app.modules.auth.models import (
    AuthSession,
    PasswordResetToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.reset_email import PasswordResetEmailPort
from app.modules.auth.security import (
    InvalidEmailError,
    InvalidPasswordError,
    PasswordHasher,
    generate_reset_token,
    hash_reset_token,
    normalize_email,
)

GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "Nếu email hợp lệ, hướng dẫn đặt lại mật khẩu đã được gửi."
)
GENERIC_RESET_SUCCESS_MESSAGE = "Đặt lại mật khẩu thành công. Vui lòng đăng nhập lại."
GENERIC_RESET_TOKEN_ERROR = "Token đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."


@dataclass(frozen=True)
class ResetPublicAck:
    """Public acknowledgement matching contracts/python/retailops_extended_ports.pyi."""

    message: str


class AuthResetService:
    """Manage one-time STAFF password reset tokens and session revocation."""

    def __init__(
        self,
        *,
        email_port: PasswordResetEmailPort,
        reset_base_url: str,
        token_ttl_seconds: int = 900,
        password_hasher: PasswordHasher | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._email_port = email_port
        self._reset_base_url = reset_base_url.rstrip("/")
        self._token_ttl_seconds = token_ttl_seconds
        self._hasher = password_hasher or PasswordHasher()
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now_utc_aware(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now.astimezone(UTC)

    def request_reset(self, session: Session, *, email: str) -> ResetPublicAck:
        """Issue a one-time reset token for ACTIVE STAFF without leaking state."""
        try:
            normalized_email = normalize_email(email)
        except InvalidEmailError as err:
            raise DomainValidationError("Định dạng email không hợp lệ.") from err

        user = session.scalar(
            select(User)
            .where(User.email_normalized == normalized_email)
            .with_for_update()
        )
        if (
            user is None
            or str(user.role) != UserRole.STAFF.value
            or str(user.status) != UserStatus.ACTIVE.value
        ):
            # Perform dummy token hashing to keep work closer to the active-staff path
            # without creating DB records or dispatching any email.
            hash_reset_token(generate_reset_token())
            return ResetPublicAck(message=GENERIC_FORGOT_PASSWORD_MESSAGE)

        now_aware = self._now_utc_aware()
        now_naive = now_aware.replace(tzinfo=None)
        expires_aware = now_aware + timedelta(seconds=self._token_ttl_seconds)
        expires_naive = expires_aware.replace(tzinfo=None)

        # Invalidate any previously issued active tokens for this user.
        session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now_naive)
        )

        raw_token = generate_reset_token()
        token_hash = hash_reset_token(raw_token)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_naive,
                used_at=None,
                created_at=now_naive,
            )
        )

        query_suffix = urlencode({"token": raw_token})
        reset_link = f"{self._reset_base_url}?{query_suffix}"
        self._email_port.send_reset_email(
            session,
            user_id=user.id,
            recipient_email=user.email_normalized,
            reset_link=reset_link,
            expires_at_utc=expires_aware,
        )
        session.commit()
        return ResetPublicAck(message=GENERIC_FORGOT_PASSWORD_MESSAGE)

    def consume_reset(
        self,
        session: Session,
        *,
        token: str,
        new_password: str,
    ) -> ResetPublicAck:
        """Atomically consume a valid reset token, update password, revoke sessions."""
        clean_token = token.strip()
        if not clean_token:
            raise UnauthenticatedError()

        # Validate password policy before consuming token so invalid password
        # leaves a valid token unconsumed.
        try:
            new_hash = self._hasher.hash(new_password)
        except InvalidPasswordError as err:
            raise DomainValidationError(
                "Mật khẩu mới không đáp ứng chính sách độ dài/định dạng."
            ) from err

        now_aware = self._now_utc_aware()
        now_naive = now_aware.replace(tzinfo=None)
        token_hash = hash_reset_token(clean_token)

        # Discover token owner without mutation, then acquire the canonical
        # User lock BEFORE consuming the token or touching AuthSession rows.
        # A second conditional update below remains the one-time replay guard.
        user_id = session.scalar(
            select(PasswordResetToken.user_id).where(
                PasswordResetToken.token_hash == token_hash
            )
        )
        if user_id is None:
            session.rollback()
            raise UnauthenticatedError()

        user = session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            user is None
            or str(user.role) != UserRole.STAFF.value
            or str(user.status) != UserStatus.ACTIVE.value
        ):
            session.rollback()
            raise UnauthenticatedError()

        consume_result = session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now_naive,
            )
            .values(used_at=now_naive)
        )
        if consume_result.rowcount != 1:
            session.rollback()
            raise UnauthenticatedError()

        user.password_hash = new_hash
        user.updated_at = now_naive

        # Revoke all active sessions (blocks access JWTs and refresh tokens).
        session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now_naive)
        )

        session.commit()
        return ResetPublicAck(message=GENERIC_RESET_SUCCESS_MESSAGE)
