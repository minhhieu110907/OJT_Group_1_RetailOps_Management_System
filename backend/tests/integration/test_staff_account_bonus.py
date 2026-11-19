"""MySQL 8 integration checks for Staff lock and authenticated password change."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import sleep

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    DomainValidationError,
    InvalidCredentialsError,
    SessionInvalidError,
)
from app.modules.auth.account_service import SelfProfileService, StaffAccountService
from app.modules.auth.models import (
    AuthSession,
    PasswordResetToken,
    RefreshToken,
    StaffAccountEvent,
    User,
)
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import AuthService

pytestmark = pytest.mark.integration
EMAIL_PREFIX = "bonus_staff_"
ORIGIN = "http://127.0.0.1:5173"
OLD_PASSWORD = "old-password-2026"
NEW_PASSWORD = "new-password-2026"


def _auth_service() -> AuthService:
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )
    return AuthService(settings, password_hasher=PasswordHasher(work_factor=4))


@pytest.fixture(autouse=True)
def cleanup_bonus_rows(migrated_integration_engine: Engine):
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not ids:
            return
        session.execute(
            delete(StaffAccountEvent).where(
                (StaffAccountEvent.target_user_id.in_(ids))
                | (StaffAccountEvent.actor_id.in_(ids))
            )
        )
        sessions = list(
            session.scalars(
                select(AuthSession.id).where(AuthSession.user_id.in_(ids))
            )
        )
        if sessions:
            session.execute(
                delete(RefreshToken).where(RefreshToken.session_id.in_(sessions))
            )
        session.execute(
            delete(AuthSession).where(AuthSession.user_id.in_(ids))
        )
        session.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id.in_(ids))
        )
        session.execute(delete(User).where(User.id.in_(ids)))


def _accounts(session: Session, suffix: str) -> tuple[User, User]:
    now = datetime.now(UTC).replace(tzinfo=None)
    admin = session.scalar(select(User).where(User.admin_slot == 1))
    if admin is None:
        admin = User(
            email_normalized=f"{EMAIL_PREFIX}admin@example.com",
            password_hash=PasswordHasher(work_factor=4).hash(OLD_PASSWORD),
            full_name="Bonus Admin",
            role="ADMIN",
            status="ACTIVE",
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        session.flush()
    staff = User(
        email_normalized=f"{EMAIL_PREFIX}{suffix}@example.com",
        password_hash=PasswordHasher(work_factor=4).hash(OLD_PASSWORD),
        full_name="Bonus Staff",
        role="STAFF",
        status="ACTIVE",
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(staff)
    session.commit()
    return admin, staff


def test_lock_revoke_unlock_does_not_revive_old_session(
    migrated_integration_engine: Engine,
) -> None:
    engine = migrated_integration_engine
    service = _auth_service()
    accounts = StaffAccountService()
    with Session(engine) as session:
        admin, staff = _accounts(session, "lock")
        login = service.login(session, staff.email_normalized, OLD_PASSWORD)
        assert service.live_user(session, login.response.access_token)[0].id == staff.id
        locked = accounts.transition(
            session, actor_id=admin.id, target_user_id=staff.id, action="LOCK"
        )
        assert locked.status == "LOCKED"
        with pytest.raises(SessionInvalidError):
            service.live_user(session, login.response.access_token)
        with pytest.raises(SessionInvalidError):
            service.refresh(
                session,
                login.refresh_token,
                login.csrf_token,
                login.csrf_token,
                ORIGIN,
            )
        with pytest.raises(InvalidCredentialsError):
            service.login(session, staff.email_normalized, OLD_PASSWORD)

        unlocked = accounts.transition(
            session, actor_id=admin.id, target_user_id=staff.id, action="UNLOCK"
        )
        assert unlocked.status == "ACTIVE"
        with pytest.raises(SessionInvalidError):
            service.live_user(session, login.response.access_token)
        new_login = service.login(session, staff.email_normalized, OLD_PASSWORD)
        assert service.live_user(session, new_login.response.access_token)[0].id == staff.id
        assert len(
            list(
                session.scalars(
                    select(StaffAccountEvent).where(
                        StaffAccountEvent.target_user_id == staff.id
                    )
                )
            )
        ) == 2


def test_change_password_keeps_only_current_session(
    migrated_integration_engine: Engine,
) -> None:
    service = _auth_service()
    with Session(migrated_integration_engine) as session:
        _, staff = _accounts(session, "change")
        active = service.login(session, staff.email_normalized, OLD_PASSWORD)
        other = service.login(session, staff.email_normalized, OLD_PASSWORD)
        with pytest.raises(DomainValidationError):
            service.change_password(
                session,
                actor_id=staff.id,
                session_id=active.response.user.id,  # type: ignore[arg-type]
                current_password="incorrect-password",
                new_password=NEW_PASSWORD,
                refresh_token=active.refresh_token,
                csrf_header=active.csrf_token,
                csrf_cookie=active.csrf_token,
                origin=ORIGIN,
            )
        # Supply the actual server-side session UUID from the bearer JWT.
        _, current_session_id = service.live_user(session, active.response.access_token)
        result = service.change_password(
            session,
            actor_id=staff.id,
            session_id=current_session_id,
            current_password=OLD_PASSWORD,
            new_password=NEW_PASSWORD,
            refresh_token=active.refresh_token,
            csrf_header=active.csrf_token,
            csrf_cookie=active.csrf_token,
            origin=ORIGIN,
        )
        assert result.refresh_token != active.refresh_token
        assert service.live_user(session, result.response.access_token)[0].id == staff.id
        with pytest.raises(SessionInvalidError):
            service.live_user(session, other.response.access_token)
        with pytest.raises(InvalidCredentialsError):
            service.login(session, staff.email_normalized, OLD_PASSWORD)
        assert service.login(session, staff.email_normalized, NEW_PASSWORD)


def test_login_serializes_with_account_row_lock(
    migrated_integration_engine: Engine,
) -> None:
    engine = migrated_integration_engine
    service = _auth_service()
    with Session(engine) as session:
        _, staff = _accounts(session, "race")
        target_email = staff.email_normalized
        target_id = staff.id

    def simultaneous_login() -> str:
        with Session(engine) as worker:
            try:
                service.login(worker, target_email, OLD_PASSWORD)
                return "ISSUED"
            except InvalidCredentialsError:
                return "DENIED"

    with Session(engine) as locker:
        user = locker.scalar(
            select(User).where(User.id == target_id).with_for_update()
        )
        assert user is not None
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(simultaneous_login)
            sleep(0.12)
            user.status = "LOCKED"
            locker.commit()
            assert future.result(timeout=10) == "DENIED"

    with Session(engine) as verify:
        assert verify.scalar(
            select(AuthSession.id).where(AuthSession.user_id == target_id)
        ) is None
