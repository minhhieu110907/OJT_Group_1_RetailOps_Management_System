"""MySQL constraint tests for the Auth database foundation."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.auth.security import normalize_email

pytestmark = pytest.mark.integration

EMAIL_PREFIX = "t3c9a19_"


@pytest.fixture(autouse=True)
def clean_owned_auth_rows(
    migrated_integration_engine: Engine,
) -> None:
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
        session.execute(
            delete(StaffApprovalRequest).where(
                (StaffApprovalRequest.user_id.in_(user_ids))
                | (StaffApprovalRequest.decided_by.in_(user_ids))
            )
        )
        session.execute(delete(User).where(User.id.in_(user_ids)))


def add_staff(session: Session, email: str) -> User:
    now = datetime(2026, 11, 6, 8, 0)
    user = User(
        email_normalized=normalize_email(email),
        password_hash="test-only-hash",
        role="STAFF",
        status="PENDING_APPROVAL",
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    return user


def test_email_normalization_is_unique_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    with Session(migrated_integration_engine) as session:
        add_staff(session, "T3C9A19_CASE@EXAMPLE.COM")
        session.commit()

        with pytest.raises(IntegrityError):
            add_staff(session, " t3c9a19_case@example.com ")
            session.commit()


def test_user_role_status_and_single_admin_constraints(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        session.add(
            User(
                email_normalized="t3c9a19_invalid@example.com",
                password_hash="test-only-hash",
                role="OWNER",
                status="ACTIVE",
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()

        session.add_all(
            [
                User(
                    email_normalized="t3c9a19_admin1@example.com",
                    password_hash="test-only-hash",
                    role="ADMIN",
                    status="ACTIVE",
                    admin_slot=1,
                    last_reapplied_at=None,
                    created_at=now,
                    updated_at=now,
                ),
                User(
                    email_normalized="t3c9a19_admin2@example.com",
                    password_hash="test-only-hash",
                    role="ADMIN",
                    status="ACTIVE",
                    admin_slot=1,
                    last_reapplied_at=None,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        with pytest.raises(DBAPIError):
            session.commit()


def test_staff_approval_constraints_and_foreign_keys(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        staff = add_staff(session, "t3c9a19_approval@example.com")
        session.add(
            StaffApprovalRequest(
                user_id=staff.id,
                attempt_no=1,
                status="PENDING",
                requested_at=now,
                decided_by=None,
                decided_at=None,
                decision_reason=None,
            )
        )
        session.commit()

        session.add(
            StaffApprovalRequest(
                user_id=staff.id,
                attempt_no=0,
                status="PENDING",
                requested_at=now,
                decided_by=None,
                decided_at=None,
                decision_reason=None,
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()

        session.add(
            StaffApprovalRequest(
                user_id=staff.id,
                attempt_no=2,
                status="APPROVED",
                requested_at=now,
                decided_by=None,
                decided_at=None,
                decision_reason=None,
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()


def test_session_expiry_and_refresh_token_constraints(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        staff = add_staff(session, "t3c9a19_session@example.com")
        session_id = uuid4().bytes
        session.add(
            AuthSession(
                id=session_id,
                user_id=staff.id,
                created_at=now,
                expires_at=now + timedelta(hours=8),
                revoked_at=None,
            )
        )
        session.add(
            RefreshToken(
                token_digest=b"a" * 32,
                session_id=session_id,
                generation=0,
                issued_at=now,
                consumed_at=None,
            )
        )
        session.commit()

        session.add(
            RefreshToken(
                token_digest=b"b" * 32,
                session_id=session_id,
                generation=0,
                issued_at=now,
                consumed_at=None,
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()

        session.add(
            AuthSession(
                id=uuid4().bytes,
                user_id=staff.id,
                created_at=now,
                expires_at=now + timedelta(hours=8, microseconds=1),
                revoked_at=None,
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()

        session.add(
            RefreshToken(
                token_digest=b"c" * 32,
                session_id=session_id,
                generation=-1,
                issued_at=now,
                consumed_at=now - timedelta(seconds=1),
            )
        )
        with pytest.raises(DBAPIError):
            session.commit()


def test_auth_foreign_keys_reject_orphans(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        session.add(
            AuthSession(
                id=uuid4().bytes,
                user_id=9_999_999_999,
                created_at=now,
                expires_at=now + timedelta(hours=1),
                revoked_at=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
