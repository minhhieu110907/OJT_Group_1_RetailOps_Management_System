"""MySQL integration tests for login, rotation, replay, and revocation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    AccountPendingError,
    AccountRejectedError,
    InvalidCredentialsError,
    SessionInvalidError,
)
from app.modules.auth.models import AuthSession, RefreshToken, User
from app.modules.auth.security import PasswordHasher, digest_refresh_token
from app.modules.auth.service import AuthService

pytestmark = pytest.mark.integration
EMAIL_PREFIX = "t3c9a33_"
ORIGIN = "http://127.0.0.1:5173"


def auth_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def auth_service() -> AuthService:
    return AuthService(auth_settings(), password_hasher=PasswordHasher(work_factor=4))


@pytest.fixture(autouse=True)
def clean_auth_flow_rows(migrated_integration_engine: Engine) -> None:
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not user_ids:
            return
        session_ids = list(
            session.scalars(
                select(AuthSession.id).where(AuthSession.user_id.in_(user_ids))
            )
        )
        if session_ids:
            session.execute(
                delete(RefreshToken).where(RefreshToken.session_id.in_(session_ids))
            )
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))


def add_user(session: Session, status: str, suffix: str) -> User:
    now = datetime(2026, 11, 7, 8, 0)
    user = User(
        email_normalized=f"{EMAIL_PREFIX}{suffix}@example.com",
        password_hash=PasswordHasher(work_factor=4).hash("valid-password"),
        role="STAFF",
        status=status,
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def test_login_only_accepts_active_user(migrated_integration_engine: Engine) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        active = add_user(session, "ACTIVE", "active")
        add_user(session, "PENDING_APPROVAL", "pending")
        add_user(session, "REJECTED", "rejected")

        result = service.login(session, active.email_normalized, "valid-password")
        assert result.response.user.id == active.id
        assert result.response.expires_in == 900
        assert (
            session.scalar(
                select(RefreshToken).where(
                    RefreshToken.token_digest
                    == digest_refresh_token(result.refresh_token)
                )
            ).generation
            == 0
        )

        for email, password in (
            (f"{EMAIL_PREFIX}pending@example.com", "wrong-password"),
            (f"{EMAIL_PREFIX}rejected@example.com", "wrong-password"),
            (f"{EMAIL_PREFIX}active@example.com", "wrong-password"),
            (f"{EMAIL_PREFIX}unknown@example.com", "valid-password"),
        ):
            with pytest.raises(InvalidCredentialsError):
                service.login(session, email, password)

        with pytest.raises(AccountPendingError):
            service.login(
                session,
                f"{EMAIL_PREFIX}pending@example.com",
                "valid-password",
            )
        with pytest.raises(AccountRejectedError):
            service.login(
                session,
                f"{EMAIL_PREFIX}rejected@example.com",
                "valid-password",
            )

        assert (
            session.scalar(select(AuthSession).where(AuthSession.user_id != active.id))
            is None
        )


def test_refresh_replay_commits_revocation_and_invalidates_new_token(
    migrated_integration_engine: Engine,
) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "replay")
        user_id = user.id
        login = service.login(session, user.email_normalized, "valid-password")
        rotated = service.refresh(
            session,
            login.refresh_token,
            login.csrf_token,
            login.csrf_token,
            ORIGIN,
        )
        with pytest.raises(SessionInvalidError):
            service.refresh(
                session,
                login.refresh_token,
                login.csrf_token,
                login.csrf_token,
                ORIGIN,
            )

    with Session(migrated_integration_engine) as verification:
        auth_session = verification.scalar(
            select(AuthSession).where(AuthSession.user_id == user_id)
        )
        assert auth_session.revoked_at is not None
        with pytest.raises(SessionInvalidError):
            service.refresh(
                verification,
                rotated.refresh_token,
                rotated.csrf_token,
                rotated.csrf_token,
                ORIGIN,
            )
        with pytest.raises(SessionInvalidError):
            service.live_user(verification, rotated.response.access_token)


def test_unknown_refresh_does_not_revoke_another_session(
    migrated_integration_engine: Engine,
) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "unknown")
        login = service.login(session, user.email_normalized, "valid-password")
        with pytest.raises(SessionInvalidError):
            service.refresh(
                session,
                "unknown-token",
                login.csrf_token,
                login.csrf_token,
                ORIGIN,
            )
        auth_session = session.scalar(
            select(AuthSession).where(AuthSession.user_id == user.id)
        )
        assert auth_session.revoked_at is None


def test_logout_revokes_access_token(migrated_integration_engine: Engine) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "logout")
        login = service.login(session, user.email_normalized, "valid-password")
        service.logout(
            session,
            login.refresh_token,
            login.csrf_token,
            login.csrf_token,
            ORIGIN,
        )
        service.logout(
            session,
            login.refresh_token,
            login.csrf_token,
            login.csrf_token,
            ORIGIN,
        )
        with pytest.raises(SessionInvalidError):
            service.live_user(session, login.response.access_token)


def test_csrf_cold_start_binds_to_live_refresh_session(
    migrated_integration_engine: Engine,
) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "csrf_cold_start")
        login = service.login(session, user.email_normalized, "valid-password")
        session_id = service.csrf_binding(session, None, login.refresh_token)
        assert session_id is not None
        token = service.csrf.issue(session_id)
        service.csrf.verify_pair(
            header_token=token,
            cookie_token=token,
            expected_session_id=session_id,
        )
        assert service.csrf_binding(session, None, "unknown-token") is None


def test_csrf_expired_bearer_falls_back_to_live_refresh_cookie(
    migrated_integration_engine: Engine,
) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "csrf_expired_bearer")
        login = service.login(session, user.email_normalized, "valid-password")
        live_session = session.scalar(
            select(AuthSession).where(AuthSession.user_id == user.id)
        )
        now = datetime.now(UTC)
        expired_access = jwt.encode(
            {
                "iss": service.settings.jwt_issuer,
                "aud": service.settings.jwt_audience,
                "sub": str(user.id),
                "sid": str(uuid4()),
                "iat": now - timedelta(minutes=30),
                "nbf": now - timedelta(minutes=30),
                "exp": now - timedelta(minutes=15),
                "jti": str(uuid4()),
            },
            service.settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )

        binding = service.csrf_binding(session, expired_access, login.refresh_token)

        assert binding is not None
        assert binding.bytes == live_session.id


def test_concurrent_refresh_rotates_once_then_revokes_session(
    migrated_integration_engine: Engine,
) -> None:
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        user = add_user(session, "ACTIVE", "race")
        user_id = user.id
        login = service.login(session, user.email_normalized, "valid-password")

    def rotate() -> str:
        with Session(migrated_integration_engine) as worker_session:
            try:
                service.refresh(
                    worker_session,
                    login.refresh_token,
                    login.csrf_token,
                    login.csrf_token,
                    ORIGIN,
                )
            except SessionInvalidError:
                return "replay"
            return "rotated"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: rotate(), range(2)))

    assert sorted(outcomes) == ["replay", "rotated"]
    with Session(migrated_integration_engine) as verification:
        auth_session = verification.scalar(
            select(AuthSession).where(AuthSession.user_id == user_id)
        )
        generations = list(
            verification.scalars(
                select(RefreshToken.generation)
                .where(RefreshToken.session_id == auth_session.id)
                .order_by(RefreshToken.generation)
            )
        )
        assert generations == [0, 1]
        assert auth_session.revoked_at is not None
