"""MySQL integration tests for atomic and concurrent Staff registration."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from pydantic import SecretStr
from pymysql.err import IntegrityError as PyMySQLIntegrityError
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import AuthSession, StaffApprovalRequest, User
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import REGISTER_ACCEPTED_MESSAGE, AuthService
from app.modules.notifications.models import AdminNotification
from app.modules.outbox.models import OutboxEvent

pytestmark = pytest.mark.integration
EMAIL_PREFIX = "t3c9a33_registration_"
ADMIN_EMAIL = f"{EMAIL_PREFIX}admin@example.com"


def auth_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
    )


def auth_service(
    *,
    notification_service: object | None = None,
    outbox_writer: object | None = None,
) -> AuthService:
    return AuthService(
        auth_settings(),
        password_hasher=PasswordHasher(work_factor=4),
        notification_service=notification_service,
        outbox_writer=outbox_writer,
    )


def cleanup_registration_rows(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(User.email_normalized.like(f"{EMAIL_PREFIX}%"))
            )
        )
        if not user_ids:
            return
        approval_ids = list(
            session.scalars(
                select(StaffApprovalRequest.id).where(
                    StaffApprovalRequest.user_id.in_(user_ids)
                )
            )
        )
        if approval_ids:
            session.execute(
                delete(AdminNotification).where(
                    AdminNotification.approval_request_id.in_(approval_ids)
                )
            )
        session.execute(delete(OutboxEvent).where(OutboxEvent.subject_user_id.in_(user_ids)))
        session.execute(
            delete(StaffApprovalRequest).where(
                StaffApprovalRequest.user_id.in_(user_ids)
            )
        )
        session.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))


@pytest.fixture(autouse=True)
def clean_registration_rows(migrated_integration_engine: Engine) -> None:
    cleanup_registration_rows(migrated_integration_engine)
    yield
    cleanup_registration_rows(migrated_integration_engine)


@pytest.fixture
def registration_admin(migrated_integration_engine: Engine) -> int:
    with Session(migrated_integration_engine) as session:
        existing_admin = session.scalar(select(User).where(User.admin_slot == 1))
        if existing_admin is not None:
            return existing_admin.id
        now = datetime(2026, 11, 8, 8, 0)
        admin = User(
            email_normalized=ADMIN_EMAIL,
            password_hash="test-only-hash",
            role="ADMIN",
            status="ACTIVE",
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        session.commit()
        return admin.id


def registration_counts(session: Session, email: str) -> tuple[int, int, int, int, int]:
    user_ids = select(User.id).where(User.email_normalized == email)
    approval_ids = select(StaffApprovalRequest.id).where(
        StaffApprovalRequest.user_id.in_(user_ids)
    )
    return (
        int(
            session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.email_normalized == email)
            )
            or 0
        ),
        int(
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.subject_user_id.in_(user_ids))
            )
            or 0
        ),
        int(
            session.scalar(
                select(func.count())
                .select_from(StaffApprovalRequest)
                .where(StaffApprovalRequest.user_id.in_(user_ids))
            )
            or 0
        ),
        int(
            session.scalar(
                select(func.count())
                .select_from(AdminNotification)
                .where(AdminNotification.approval_request_id.in_(approval_ids))
            )
            or 0
        ),
        int(
            session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id.in_(user_ids))
            )
            or 0
        ),
    )


def test_register_creates_pending_user_approval_and_notification_once(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}success@example.com"
    service = auth_service()
    with Session(migrated_integration_engine) as session:
        first = service.register(session, email.upper(), "valid-password")
        second = service.register(session, email, "different-password")

        user = session.scalar(select(User).where(User.email_normalized == email))
        approval = session.scalar(
            select(StaffApprovalRequest).where(StaffApprovalRequest.user_id == user.id)
        )
        notification = session.scalar(
            select(AdminNotification).where(
                AdminNotification.approval_request_id == approval.id
            )
        )

        assert first.message == second.message == REGISTER_ACCEPTED_MESSAGE
        assert user.role == "STAFF"
        assert user.status == "PENDING_APPROVAL"
        assert user.password_hash != "valid-password"
        assert approval.attempt_no == 1
        assert approval.status == "PENDING"
        assert notification.admin_user_id == registration_admin
        assert registration_counts(session, email) == (1, 1, 1, 1, 0)
        event = session.scalar(
            select(OutboxEvent).where(OutboxEvent.subject_user_id == user.id)
        )
        assert event.event_type == "STAFF_REGISTERED"
        assert event.payload == {
            "schema_version": 1,
            "approval_request_id": approval.id,
        }


@pytest.mark.parametrize("status", ["ACTIVE", "REJECTED"])
def test_existing_non_pending_identity_gets_generic_response_without_new_rows(
    migrated_integration_engine: Engine,
    registration_admin: int,
    status: str,
) -> None:
    email = f"{EMAIL_PREFIX}{status.lower()}@example.com"
    now = datetime(2026, 11, 8, 8, 0)
    with Session(migrated_integration_engine) as session:
        session.add(
            User(
                email_normalized=email,
                password_hash="existing-hash",
                role="STAFF",
                status=status,
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        result = auth_service().register(session, email, "valid-password")

        assert result.message == REGISTER_ACCEPTED_MESSAGE
        assert registration_counts(session, email) == (1, 0, 0, 0, 0)


class FailingNotificationService:
    def create_for_approval(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced notification persistence failure")


class FailingOutboxWriter:
    def append(self, *_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("forced outbox persistence failure")


class OtherDuplicateNotificationService:
    def create_for_approval(self, *_args: object, **_kwargs: object) -> None:
        driver_error = PyMySQLIntegrityError(
            1062,
            "Duplicate entry '1' for key "
            "'admin_notifications.uq_admin_notifications_approval_request_id'",
        )
        raise IntegrityError("INSERT admin_notifications", {}, driver_error)


class ForeignKeyFailureNotificationService:
    def create_for_approval(
        self,
        session: Session,
        admin_user_id: int,
        approval_request_id: int,
    ) -> None:
        del admin_user_id
        session.add(
            AdminNotification(
                admin_user_id=9_999_999_999,
                approval_request_id=approval_request_id,
                created_at=datetime(2026, 11, 9, 8, 0),
                read_at=None,
            )
        )
        session.flush()


def test_notification_failure_rolls_back_entire_registration(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}rollback@example.com"
    service = auth_service(notification_service=FailingNotificationService())
    with Session(migrated_integration_engine) as session:
        with pytest.raises(RuntimeError, match="forced notification"):
            service.register(session, email, "valid-password")
        assert registration_counts(session, email) == (0, 0, 0, 0, 0)


def test_outbox_failure_rolls_back_entire_registration(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}outbox-rollback@example.com"
    service = auth_service(outbox_writer=FailingOutboxWriter())
    with Session(migrated_integration_engine) as session:
        with pytest.raises(RuntimeError, match="forced outbox"):
            service.register(session, email, "valid-password")
        assert registration_counts(session, email) == (0, 0, 0, 0, 0)


def test_other_duplicate_constraint_is_not_treated_as_duplicate_email(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}other-duplicate@example.com"
    service = auth_service(notification_service=OtherDuplicateNotificationService())
    with Session(migrated_integration_engine) as session:
        with pytest.raises(IntegrityError) as captured:
            service.register(session, email, "valid-password")

        assert "uq_admin_notifications_approval_request_id" in str(captured.value)
        assert registration_counts(session, email) == (0, 0, 0, 0, 0)
        assert session.scalar(select(func.count()).select_from(User)) is not None


def test_notification_foreign_key_failure_rolls_back_and_session_recovers(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}foreign-key@example.com"
    service = auth_service(notification_service=ForeignKeyFailureNotificationService())
    with Session(migrated_integration_engine) as session:
        with pytest.raises(IntegrityError) as captured:
            service.register(session, email, "valid-password")

        assert getattr(captured.value.orig, "args", (None,))[0] == 1452
        assert registration_counts(session, email) == (0, 0, 0, 0, 0)
        assert session.scalar(select(func.count()).select_from(User)) is not None


def test_concurrent_registration_creates_single_atomic_result(
    migrated_integration_engine: Engine,
    registration_admin: int,
) -> None:
    email = f"{EMAIL_PREFIX}race@example.com"

    def register() -> str:
        with Session(migrated_integration_engine) as session:
            return auth_service().register(session, email, "valid-password").message

    with ThreadPoolExecutor(max_workers=2) as executor:
        messages = list(executor.map(lambda _index: register(), range(2)))

    assert messages == [REGISTER_ACCEPTED_MESSAGE, REGISTER_ACCEPTED_MESSAGE]
    with Session(migrated_integration_engine) as session:
        assert registration_counts(session, email) == (1, 1, 1, 1, 0)
