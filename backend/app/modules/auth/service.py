"""Authentication application service and transaction boundaries."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    CsrfRejectedError,
    InvalidCredentialsError,
    SessionInvalidError,
)
from app.modules.auth.models import AuthSession, RefreshToken, User, UserStatus
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import AuthenticatedUser, TokenResponse
from app.modules.auth.security import (
    CsrfService,
    InvalidEmailError,
    JwtService,
    PasswordHasher,
    digest_refresh_token,
    generate_refresh_token,
    normalize_email,
)

DUMMY_BCRYPT_HASH = "$2b$12$62o5pXd4lx/yYM9iMtKFKu/oWXJ7GXA1cAhnAs7tQxsjUE4JnvMnG"


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class AuthResult:
    response: TokenResponse
    refresh_token: str
    csrf_token: str
    session_expires_at: datetime


class AuthService:
    """Coordinate Auth use cases while owning every commit/rollback decision."""

    def __init__(
        self,
        settings: Settings,
        repository: AuthRepository | None = None,
        password_hasher: PasswordHasher | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or AuthRepository()
        self.password_hasher = password_hasher or PasswordHasher()
        self.jwt = JwtService(settings)
        self.csrf = CsrfService(settings)

    def login(self, session: Session, email: str, password: str) -> AuthResult:
        try:
            normalized = normalize_email(email)
        except InvalidEmailError as error:
            self.password_hasher.verify(password, DUMMY_BCRYPT_HASH)
            raise InvalidCredentialsError() from error
        user = self.repository.find_user_by_email(session, normalized)
        password_hash = user.password_hash if user is not None else DUMMY_BCRYPT_HASH
        password_matches = self.password_hasher.verify(password, password_hash)
        if user is None or not password_matches or user.status != UserStatus.ACTIVE:
            session.rollback()
            raise InvalidCredentialsError()

        now = utc_now_naive()
        expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        session_id = uuid4()
        refresh_token = generate_refresh_token()
        auth_session = AuthSession(
            id=session_id.bytes,
            user_id=user.id,
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
        refresh = RefreshToken(
            token_digest=digest_refresh_token(refresh_token),
            session_id=session_id.bytes,
            generation=0,
            issued_at=now,
            consumed_at=None,
        )
        self.repository.add_session(session, auth_session, refresh)
        session.commit()
        return self._auth_result(user, session_id, expires_at, refresh_token, now)

    def refresh(
        self,
        session: Session,
        refresh_token: str | None,
        csrf_header: str | None,
        csrf_cookie: str | None,
        origin: str | None,
    ) -> AuthResult:
        self._validate_origin(origin)
        if not refresh_token:
            raise SessionInvalidError()
        if not csrf_header or not csrf_cookie:
            raise CsrfRejectedError()
        try:
            csrf_session_id = self.csrf.session_binding(csrf_header)
            self.csrf.verify_pair(
                header_token=csrf_header,
                cookie_token=csrf_cookie,
                expected_session_id=csrf_session_id,
            )
        except ValueError as error:
            raise CsrfRejectedError() from error
        if csrf_session_id is None:
            raise CsrfRejectedError()
        digest = self._safe_digest(refresh_token)
        record = self.repository.find_refresh(session, digest)
        if record is None:
            session.rollback()
            raise SessionInvalidError()
        session_id = UUID(bytes=record.session_id)
        if session_id != csrf_session_id:
            raise CsrfRejectedError()

        auth_session = self.repository.lock_session(session, record.session_id)
        record = self.repository.lock_refresh(session, digest)
        now = utc_now_naive()
        if auth_session is None or record is None:
            session.rollback()
            raise SessionInvalidError()
        if record.consumed_at is not None:
            if auth_session.revoked_at is None:
                auth_session.revoked_at = now
            session.commit()
            raise SessionInvalidError()
        if (
            auth_session.revoked_at is not None
            or auth_session.expires_at <= now
            or auth_session.user.status != UserStatus.ACTIVE
        ):
            session.rollback()
            raise SessionInvalidError()

        record.consumed_at = now
        next_token = generate_refresh_token()
        session.add(
            RefreshToken(
                token_digest=digest_refresh_token(next_token),
                session_id=auth_session.id,
                generation=record.generation + 1,
                issued_at=now,
                consumed_at=None,
            )
        )
        session.commit()
        return self._auth_result(
            auth_session.user,
            session_id,
            auth_session.expires_at,
            next_token,
            now,
        )

    def logout(
        self,
        session: Session,
        refresh_token: str | None,
        csrf_header: str | None,
        csrf_cookie: str | None,
        origin: str | None,
    ) -> None:
        self._validate_origin(origin)
        if not csrf_header or not csrf_cookie:
            raise CsrfRejectedError()
        try:
            csrf_session_id = self.csrf.session_binding(csrf_header)
            self.csrf.verify_pair(
                header_token=csrf_header,
                cookie_token=csrf_cookie,
                expected_session_id=csrf_session_id,
            )
        except ValueError as error:
            raise CsrfRejectedError() from error
        if csrf_session_id is None or not refresh_token:
            return
        digest = self._safe_digest(refresh_token)
        record = self.repository.find_refresh(session, digest)
        if record is None or record.session_id != csrf_session_id.bytes:
            session.rollback()
            return
        auth_session = self.repository.lock_session(session, record.session_id)
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = utc_now_naive()
        session.commit()

    def live_user(self, session: Session, access_token: str) -> tuple[User, UUID]:
        try:
            claims = self.jwt.decode(access_token)
        except ValueError as error:
            raise SessionInvalidError() from error
        user = self.repository.find_live_principal(
            session,
            claims.session_id.bytes,
            claims.user_id,
            utc_now_naive(),
        )
        if user is None:
            raise SessionInvalidError()
        return user, claims.session_id

    def csrf_binding(
        self,
        session: Session,
        access_token: str | None,
        refresh_token: str | None,
    ) -> UUID | None:
        """Resolve a live session for read-only CSRF bootstrap when possible."""
        if access_token:
            try:
                _, session_id = self.live_user(session, access_token)
                return session_id
            except SessionInvalidError:
                # An expired/stale bearer is not authentication evidence. A live
                # refresh cookie may still bind a read-only bootstrap proof.
                pass
        if not refresh_token:
            return None
        try:
            digest = digest_refresh_token(refresh_token)
        except (UnicodeEncodeError, ValueError):
            return None
        auth_session = self.repository.find_live_session_by_refresh(
            session, digest, utc_now_naive()
        )
        if auth_session is None:
            return None
        return UUID(bytes=auth_session.id)

    def _auth_result(
        self,
        user: User,
        session_id: UUID,
        expires_at: datetime,
        refresh_token: str,
        now: datetime,
    ) -> AuthResult:
        access_token, expires_in = self.jwt.issue(
            user_id=user.id,
            session_id=session_id,
            session_expires_at=expires_at,
            now=now.replace(tzinfo=UTC),
        )
        csrf_token = self.csrf.issue(session_id)
        return AuthResult(
            response=TokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                user=AuthenticatedUser(
                    id=user.id,
                    email_normalized=user.email_normalized,
                    role=user.role,
                    status=user.status,
                ),
            ),
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            session_expires_at=expires_at,
        )

    def _validate_origin(self, origin: str | None) -> None:
        if origin is None or origin not in self.settings.cors_origin_allowlist:
            raise CsrfRejectedError()

    @staticmethod
    def _safe_digest(token: str) -> bytes:
        try:
            return digest_refresh_token(token)
        except (UnicodeEncodeError, ValueError) as error:
            raise SessionInvalidError() from error
