"""Tests for safe Auth response schemas."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.modules.auth.schemas import (
    AuthSessionRead,
    RefreshTokenMetadata,
    UserRead,
)


def test_user_read_does_not_expose_password_hash() -> None:
    now = datetime(2026, 11, 6)
    user = SimpleNamespace(
        id=1,
        email_normalized="admin@example.com",
        password_hash="must-not-leak",
        role="ADMIN",
        status="ACTIVE",
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )

    payload = UserRead.model_validate(user).model_dump()

    assert "password_hash" not in payload
    assert "must-not-leak" not in str(payload)


def test_session_and_refresh_metadata_do_not_expose_digest() -> None:
    now = datetime(2026, 11, 6)
    session_id = uuid4()
    session_payload = AuthSessionRead(
        id=session_id,
        user_id=1,
        created_at=now,
        expires_at=now,
        revoked_at=None,
    ).model_dump()
    refresh_payload = RefreshTokenMetadata(
        session_id=session_id,
        generation=0,
        issued_at=now,
        consumed_at=None,
    ).model_dump()

    assert "token_digest" not in session_payload
    assert "token_digest" not in refresh_payload
