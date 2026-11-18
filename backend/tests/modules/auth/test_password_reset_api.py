"""Unit and HTTP API tests for T04AA1C STAFF password reset & email adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import BigInteger, create_engine, event, select, text
from sqlalchemy.dialects.mysql import BINARY, TINYINT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.infrastructure.dependencies import get_rate_limiter
from app.infrastructure.rate_limit import RateLimitResult, RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.models import (
    AuthSession,
    PasswordResetToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.reset_email import (
    FakeInMemoryPasswordResetEmailAdapter,
    OutboxPasswordResetEmailAdapter,
    build_password_reset_email_adapter,
)
from app.modules.auth.reset_service import (
    GENERIC_FORGOT_PASSWORD_MESSAGE,
    AuthResetService,
)
from app.modules.auth.router import get_auth_reset_service
from app.modules.auth.security import (
    RESET_SECRET_VERSION,
    PasswordHasher,
    decrypt_reset_secret,
    encrypt_reset_secret,
    hash_reset_token,
)
from app.modules.outbox.handler import EmailEventHandler
from app.modules.outbox.models import OutboxEvent


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


@compiles(BINARY, "sqlite")
def _compile_binary_sqlite(_type, _compiler, **_kw) -> str:
    return "BLOB"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


def _make_sqlite_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_collation(dbapi_conn, _conn_record):
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            PasswordResetToken.__table__,
            OutboxEvent.__table__,
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE auth_sessions ("
                "id BLOB NOT NULL PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "expires_at DATETIME NOT NULL, "
                "revoked_at DATETIME, "
                "FOREIGN KEY(user_id) REFERENCES users (id))"
            )
        )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _make_settings(**overrides) -> Settings:
    defaults = {
        "db_host": "unused",
        "db_name": "unused",
        "db_user": "unused",
        "db_password": SecretStr("unused"),
        "jwt_secret": SecretStr("j" * 32),
        "csrf_secret": SecretStr("c" * 32),
        "idempotency_secret": SecretStr("i" * 32),
        "outbox_secret_key": SecretStr("o" * 32),
        "password_reset_email_adapter": "memory",
        "password_reset_base_url": "https://app.retailops.example/reset-password",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _seed_user(
    session: Session,
    *,
    email: str,
    role: UserRole = UserRole.STAFF,
    status: UserStatus = UserStatus.ACTIVE,
    password: str = "OldPass!123",
    admin_slot: int | None = None,
) -> User:
    now = datetime.now(UTC).replace(tzinfo=None)
    user = User(
        email_normalized=email,
        password_hash=PasswordHasher(work_factor=4).hash(password),
        role=role.value,
        status=status.value,
        admin_slot=admin_slot,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def _make_test_app(
    session_factory,
    reset_service: AuthResetService,
    *,
    limiter_allowed: bool = True,
):
    config = _make_settings()
    app = create_app(config)
    app.dependency_overrides[get_settings] = lambda: config

    def _override_session():
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_auth_reset_service] = lambda: reset_service

    mock_limiter = MagicMock(spec=RedisFixedWindowRateLimiter)

    async def _check(**kwargs):
        return RateLimitResult(
            allowed=limiter_allowed,
            count=1 if limiter_allowed else 6,
            retry_after=0 if limiter_allowed else 60,
        )

    mock_limiter.check.side_effect = _check
    app.dependency_overrides[get_rate_limiter] = lambda: mock_limiter
    return app


def test_config_rejects_memory_adapter_in_production() -> None:
    with pytest.raises(ValidationError, match="production"):
        _make_settings(environment="production", password_reset_email_adapter="memory")

    settings = _make_settings(
        environment="production", password_reset_email_adapter="outbox"
    )
    adapter = build_password_reset_email_adapter(settings)
    assert isinstance(adapter, OutboxPasswordResetEmailAdapter)


@pytest.mark.anyio
async def test_forgot_password_non_enumeration_and_host_header_ignored() -> None:
    sf = _make_sqlite_session_factory()
    email_adapter = FakeInMemoryPasswordResetEmailAdapter()
    now_box = [datetime(2026, 11, 18, 10, 0, 0, tzinfo=UTC)]
    service = AuthResetService(
        email_port=email_adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        token_ttl_seconds=900,
        password_hasher=PasswordHasher(work_factor=4),
        clock=lambda: now_box[0],
    )

    with sf() as s:
        staff = _seed_user(s, email="staff@example.com")
        _seed_user(
            s,
            email="admin@example.com",
            role=UserRole.ADMIN,
            admin_slot=1,
        )
        _seed_user(
            s,
            email="pending@example.com",
            role=UserRole.STAFF,
            status=UserStatus.PENDING_APPROVAL,
        )
        _seed_user(
            s,
            email="rejected@example.com",
            role=UserRole.STAFF,
            status=UserStatus.REJECTED,
        )

    app = _make_test_app(sf, service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r_staff = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "staff@example.com"},
            headers={"Host": "evil.attacker.example"},
        )
        r_missing = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        r_admin = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "admin@example.com"},
        )
        r_pending = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "pending@example.com"},
        )
        r_rejected = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "rejected@example.com"},
        )

    for resp in (r_staff, r_missing, r_admin, r_pending, r_rejected):
        assert resp.status_code == 202
        assert resp.json() == {"message": GENERIC_FORGOT_PASSWORD_MESSAGE}

    # Only ACTIVE STAFF receives an email; reset link uses configured base URL
    assert len(email_adapter.sent_emails) == 1
    sent = email_adapter.sent_emails[0]
    assert sent.recipient_email == "staff@example.com"
    assert sent.reset_link.startswith(
        "https://app.retailops.example/reset-password?token="
    )
    assert "evil.attacker.example" not in sent.reset_link

    raw_token = sent.reset_link.split("token=", 1)[1]
    with sf() as s:
        tokens = list(s.scalars(select(PasswordResetToken)))
        assert len(tokens) == 1
        assert tokens[0].user_id == staff.id
        assert tokens[0].token_hash == hash_reset_token(raw_token)
        assert tokens[0].token_hash != raw_token


@pytest.mark.anyio
async def test_reset_password_lifecycle_replay_expiry_revocation_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    sf = _make_sqlite_session_factory()
    email_adapter = FakeInMemoryPasswordResetEmailAdapter()
    now_box = [datetime(2026, 11, 18, 10, 0, 0, tzinfo=UTC)]
    hasher = PasswordHasher(work_factor=4)
    service = AuthResetService(
        email_port=email_adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        token_ttl_seconds=900,
        password_hasher=hasher,
        clock=lambda: now_box[0],
    )

    with sf() as s:
        staff = _seed_user(s, email="staff@example.com", password="OldPass!123")
        active_sess = AuthSession(
            id=b"1" * 16,
            user_id=staff.id,
            created_at=datetime(2026, 11, 18, 9, 0, 0),
            expires_at=datetime(2026, 11, 18, 17, 0, 0),
            revoked_at=None,
        )
        s.add(active_sess)
        s.commit()

    app = _make_test_app(sf, service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Request 1 -> Token 1
        await client.post(
            "/api/v1/auth/forgot-password", json={"email": "staff@example.com"}
        )
        token_1 = email_adapter.sent_emails[0].reset_link.split("token=", 1)[1]

        # Request 2 -> invalidates Token 1, issues Token 2
        now_box[0] = now_box[0] + timedelta(seconds=30)
        await client.post(
            "/api/v1/auth/forgot-password", json={"email": "staff@example.com"}
        )
        token_2 = email_adapter.sent_emails[1].reset_link.split("token=", 1)[1]

        # Old Token 1 is rejected
        r_old = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token_1, "new_password": "NewPass!456"},
        )
        assert r_old.status_code == 401

        # Password policy violation (> 72 bytes) -> 422, token_2 not consumed
        r_bad_pw = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token_2, "new_password": "x" * 73},
        )
        assert r_bad_pw.status_code == 422

        # Valid reset with token_2 succeeds -> 200
        r_ok = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token_2, "new_password": "NewPass!456"},
        )
        assert r_ok.status_code == 200

        # Replay token_2 -> 401, password unchanged
        r_replay = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token_2, "new_password": "AnotherPass!789"},
        )
        assert r_replay.status_code == 401

        # Request 3 then advance past TTL -> 401
        await client.post(
            "/api/v1/auth/forgot-password", json={"email": "staff@example.com"}
        )
        token_3 = email_adapter.sent_emails[2].reset_link.split("token=", 1)[1]
        now_box[0] = now_box[0] + timedelta(seconds=901)
        r_exp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token_3, "new_password": "ExpiredPass!1"},
        )
        assert r_exp.status_code == 401

        # Nonexistent token -> 401
        r_missing_tok = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "nonexistent-token-value", "new_password": "NewPass!999"},
        )
        assert r_missing_tok.status_code == 401

    with sf() as s:
        refreshed_user = s.get(User, staff.id)
        assert refreshed_user is not None
        assert hasher.verify("NewPass!456", refreshed_user.password_hash)
        assert not hasher.verify("OldPass!123", refreshed_user.password_hash)
        assert not hasher.verify("AnotherPass!789", refreshed_user.password_hash)
        sess = s.get(AuthSession, b"1" * 16)
        assert sess is not None and sess.revoked_at is not None

    # Ensure zero token/password/link leakage in logs
    log_text = caplog.text
    assert token_1 not in log_text
    assert token_2 not in log_text
    assert token_3 not in log_text
    assert "NewPass!456" not in log_text
    assert "reset-password?token=" not in log_text


@pytest.mark.anyio
async def test_forgot_and_reset_rate_limiting_429() -> None:
    sf = _make_sqlite_session_factory()
    service = AuthResetService(
        email_port=FakeInMemoryPasswordResetEmailAdapter(),
        reset_base_url="https://app.retailops.example/reset-password",
    )
    app = _make_test_app(sf, service, limiter_allowed=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        r1 = await client.post(
            "/api/v1/auth/forgot-password", json={"email": "staff@example.com"}
        )
        r2 = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "some-token", "new_password": "NewPass!123"},
        )
    assert r1.status_code == 429
    assert r2.status_code == 429


def test_outbox_reset_adapter_encrypts_secret_in_outbox_event() -> None:
    sf = _make_sqlite_session_factory()
    adapter = OutboxPasswordResetEmailAdapter(secret_key="s" * 32)
    service = AuthResetService(
        email_port=adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        token_ttl_seconds=900,
        password_hasher=PasswordHasher(work_factor=4),
    )
    with sf() as s:
        staff = _seed_user(s, email="staff@example.com")
        service.request_reset(s, email="staff@example.com")
        events = list(s.scalars(select(OutboxEvent)))
        assert len(events) == 1
        ev = events[0]
        assert ev.subject_user_id == staff.id
        assert ev.event_type == "PASSWORD_RESET"
        assert ev.payload == {"schema_version": 1}
        assert ev.secret_ciphertext is not None
        assert b"reset-password?token=" not in ev.secret_ciphertext


def test_aes256gcm_encrypt_decrypt_roundtrip_and_tamper_detection() -> None:
    key = "a" * 32
    wrong_key = "b" * 32
    link = "https://app.retailops.example/reset-password?token=secret-tok-123"

    blob1 = encrypt_reset_secret(link, key)
    blob2 = encrypt_reset_secret(link, key)

    assert blob1[:1] == RESET_SECRET_VERSION
    assert blob1 != blob2  # random 12-byte nonce per encryption
    assert b"secret-tok-123" not in blob1
    assert decrypt_reset_secret(blob1, key) == link

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_reset_secret(blob1, wrong_key)

    tampered = bytearray(blob1)
    tampered[-1] ^= 0xFF
    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_reset_secret(bytes(tampered), key)


def test_email_worker_handles_password_reset_valid_expired_and_inactive(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    sf = _make_sqlite_session_factory()
    secret_key = "w" * 32
    now_box = [datetime(2026, 11, 18, 10, 0, 0)]
    adapter = OutboxPasswordResetEmailAdapter(secret_key=secret_key)
    service = AuthResetService(
        email_port=adapter,
        reset_base_url="https://app.retailops.example/reset-password",
        token_ttl_seconds=900,
        password_hasher=PasswordHasher(work_factor=4),
        clock=lambda: now_box[0].replace(tzinfo=UTC),
    )

    sent_transport = MagicMock()
    handler = EmailEventHandler(
        sf,
        sent_transport,
        clock=lambda: now_box[0],
        secret_key=secret_key,
    )

    with sf() as s:
        _seed_user(s, email="staff@example.com")
        service.request_reset(s, email="staff@example.com")
        ev1 = s.scalar(select(OutboxEvent))
        assert ev1 is not None
        ev1_id = ev1.id

    # 1. Valid active token -> SENT with reset link, no token in logs
    out1 = handler.handle(event_id=ev1_id)
    assert out1.status == "SENT"
    sent_transport.send.assert_called_once()
    sent_email = sent_transport.send.call_args.kwargs["email"]
    assert "https://app.retailops.example/reset-password?token=" in sent_email.text
    assert "https://app.retailops.example/reset-password?token=" not in caplog.text

    # 2. Replaced / inactive token -> FAILED (TOKEN_INACTIVE), transport not called
    sent_transport.reset_mock()
    with sf() as s:
        service.request_reset(s, email="staff@example.com")
        events = list(s.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at)))
        ev2_id = events[-1].id
        # Replace ev2's token by issuing ev3
        service.request_reset(s, email="staff@example.com")
        events = list(s.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at)))
        ev3_id = events[-1].id

    out2 = handler.handle(event_id=ev2_id)
    assert out2.status == "FAILED"
    sent_transport.send.assert_not_called()

    # 3. Expired event -> FAILED (SECRET_EXPIRED), transport not called
    now_box[0] = now_box[0] + timedelta(seconds=901)
    out3 = handler.handle(event_id=ev3_id)
    assert out3.status == "FAILED"
    sent_transport.send.assert_not_called()
