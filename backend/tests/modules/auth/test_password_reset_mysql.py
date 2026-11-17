"""MySQL integration tests for T04AA1C STAFF password reset & outbox."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthenticatedError
from app.modules.auth.models import (
    AuthSession,
    PasswordResetToken,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.reset_email import (
    FakeInMemoryPasswordResetEmailAdapter,
    OutboxPasswordResetEmailAdapter,
)
from app.modules.auth.reset_service import AuthResetService
from app.modules.auth.security import PasswordHasher, hash_reset_token
from app.modules.outbox.models import OutboxEvent
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class PasswordResetRunContext:
    """Run-scoped ownership tracker for isolated MySQL cleanup."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.run_id = uuid4().hex[:8]
        self.user_ids: list[int] = []

    def create_staff(self, session: Session, *, password: str = "OldPass!123") -> User:
        now = datetime.now(UTC).replace(tzinfo=None)
        user = User(
            email_normalized=f"t04aa1c_{self.run_id}_{uuid4().hex[:6]}@example.com",
            password_hash=PasswordHasher(work_factor=4).hash(password),
            role=UserRole.STAFF.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        self.user_ids.append(user.id)
        return user

    def cleanup(self) -> None:
        if not self.user_ids:
            return
        with Session(self.engine) as session, session.begin():
            sess_ids = list(
                session.scalars(
                    select(AuthSession.id).where(AuthSession.user_id.in_(self.user_ids))
                )
            )
            if sess_ids:
                session.execute(
                    delete(RefreshToken).where(RefreshToken.session_id.in_(sess_ids))
                )
                session.execute(delete(AuthSession).where(AuthSession.id.in_(sess_ids)))
            session.execute(
                delete(PasswordResetToken).where(
                    PasswordResetToken.user_id.in_(self.user_ids)
                )
            )
            session.execute(
                delete(OutboxEvent).where(
                    OutboxEvent.subject_user_id.in_(self.user_ids)
                )
            )
            session.execute(delete(User).where(User.id.in_(self.user_ids)))
        self.user_ids.clear()


def test_password_reset_full_lifecycle_and_outbox_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    ctx = PasswordResetRunContext(migrated_integration_engine)
    hasher = PasswordHasher(work_factor=4)
    try:
        with Session(migrated_integration_engine) as session:
            staff = ctx.create_staff(session, password="OldPass!123")
            now_naive = datetime.now(UTC).replace(tzinfo=None)
            sess_id = uuid4().bytes
            session.add(
                AuthSession(
                    id=sess_id,
                    user_id=staff.id,
                    created_at=now_naive,
                    expires_at=now_naive + timedelta(hours=8),
                    revoked_at=None,
                )
            )
            session.commit()

        # Issue reset via Outbox adapter
        outbox_adapter = OutboxPasswordResetEmailAdapter(secret_key="k" * 32)
        outbox_service = AuthResetService(
            email_port=outbox_adapter,
            reset_base_url="https://app.retailops.example/reset-password",
            password_hasher=hasher,
        )
        with Session(migrated_integration_engine) as session:
            outbox_service.request_reset(session, email=staff.email_normalized)

        with Session(migrated_integration_engine) as session:
            ev = session.scalar(
                select(OutboxEvent).where(OutboxEvent.subject_user_id == staff.id)
            )
            assert ev is not None
            assert ev.event_type == "PASSWORD_RESET"
            assert ev.secret_ciphertext is not None

        # Issue another reset via in-memory adapter to obtain raw token and test consume
        mem_adapter = FakeInMemoryPasswordResetEmailAdapter()
        mem_service = AuthResetService(
            email_port=mem_adapter,
            reset_base_url="https://app.retailops.example/reset-password",
            password_hasher=hasher,
        )
        with Session(migrated_integration_engine) as session:
            mem_service.request_reset(session, email=staff.email_normalized)

        raw_token = mem_adapter.sent_emails[0].reset_link.split("token=", 1)[1]
        with Session(migrated_integration_engine) as session:
            mem_service.consume_reset(
                session, token=raw_token, new_password="NewPass!456"
            )

        with Session(migrated_integration_engine) as session:
            updated_user = session.get(User, staff.id)
            assert updated_user is not None
            assert hasher.verify("NewPass!456", updated_user.password_hash)
            revoked_sess = session.get(AuthSession, sess_id)
            assert revoked_sess is not None and revoked_sess.revoked_at is not None

        # Replay fails
        with (
            Session(migrated_integration_engine) as session,
            pytest.raises(UnauthenticatedError),
        ):
            mem_service.consume_reset(
                session, token=raw_token, new_password="ReplayPass!789"
            )
    finally:
        ctx.cleanup()


def test_concurrent_reset_consume_single_winner_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Two concurrent threads racing with the same reset token: exactly 1 succeeds."""
    ctx = PasswordResetRunContext(migrated_integration_engine)
    hasher = PasswordHasher(work_factor=4)
    mem_adapter = FakeInMemoryPasswordResetEmailAdapter()
    service = AuthResetService(
        email_port=mem_adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        password_hasher=hasher,
    )
    try:
        with Session(migrated_integration_engine) as session:
            staff = ctx.create_staff(session, password="OldPass!123")
            session.commit()
            service.request_reset(session, email=staff.email_normalized)

        raw_token = mem_adapter.sent_emails[0].reset_link.split("token=", 1)[1]
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def _worker(new_pw: str) -> None:
            barrier.wait(timeout=10)
            with Session(migrated_integration_engine) as s:
                try:
                    service.consume_reset(s, token=raw_token, new_password=new_pw)
                    res = f"OK:{new_pw}"
                except UnauthenticatedError:
                    res = "REJECTED"
                with lock:
                    outcomes.append(res)

        t1 = threading.Thread(target=_worker, args=("RacePassOne!1",))
        t2 = threading.Thread(target=_worker, args=("RacePassTwo!2",))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert sorted(outcomes) in (
            ["OK:RacePassOne!1", "REJECTED"],
            ["OK:RacePassTwo!2", "REJECTED"],
        )
    finally:
        ctx.cleanup()


def test_reset_rollback_leaves_token_unused_on_mid_tx_failure(
    migrated_integration_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If an error occurs before commit, PasswordResetToken.used_at remains NULL."""
    ctx = PasswordResetRunContext(migrated_integration_engine)
    mem_adapter = FakeInMemoryPasswordResetEmailAdapter()
    service = AuthResetService(
        email_port=mem_adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        password_hasher=PasswordHasher(work_factor=4),
    )
    try:
        with Session(migrated_integration_engine) as session:
            staff = ctx.create_staff(session, password="OldPass!123")
            session.commit()
            service.request_reset(session, email=staff.email_normalized)

        raw_token = mem_adapter.sent_emails[0].reset_link.split("token=", 1)[1]
        tok_hash = hash_reset_token(raw_token)

        with Session(migrated_integration_engine) as session:

            def _boom():
                raise RuntimeError("Simulated commit failure")

            monkeypatch.setattr(session, "commit", _boom)
            with pytest.raises(RuntimeError, match="Simulated commit failure"):
                service.consume_reset(
                    session, token=raw_token, new_password="NewPass!456"
                )
            session.rollback()

        with Session(migrated_integration_engine) as session:
            tok = session.scalar(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == tok_hash
                )
            )
            assert tok is not None
            assert tok.used_at is None
    finally:
        ctx.cleanup()
