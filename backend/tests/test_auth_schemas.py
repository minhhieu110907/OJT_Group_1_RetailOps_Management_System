"""Tests for safe Auth response schemas."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import (
    AuthSessionRead,
    RefreshTokenMetadata,
    RegisterRequest,
    UserRead,
)


def test_user_read_does_not_expose_password_hash() -> None:
    now = datetime(2026, 11, 6)
    user = SimpleNamespace(
        id=1,
        email_normalized="admin@example.com",
        full_name=None,
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
    assert payload["full_name"] is None


def test_register_full_name_is_optional_trimmed_and_bounded() -> None:
    without_name = RegisterRequest(email="staff@example.com", password="password")
    with_name = RegisterRequest(
        email="staff2@example.com", password="password", full_name="  Nguyen Van A  "
    )
    assert without_name.full_name is None
    assert with_name.full_name == "Nguyen Van A"
    assert RegisterRequest(
        email="one@example.com", password="password", full_name="x"
    ).full_name == "x"
    assert RegisterRequest(
        email="max@example.com", password="password", full_name="x" * 120
    ).full_name == "x" * 120
    assert RegisterRequest(
        email="padded@example.com",
        password="password",
        full_name=f"  {'x' * 120}  ",
    ).full_name == "x" * 120
    for invalid in ("   ", "x" * 121):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="staff3@example.com", password="password", full_name=invalid
            )


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
