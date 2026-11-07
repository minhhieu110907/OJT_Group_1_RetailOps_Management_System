"""Unit tests for JWT, refresh, and signed CSRF primitives."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.modules.auth.security import (
    CsrfService,
    JwtService,
    digest_refresh_token,
    generate_refresh_token,
)


def auth_settings(**changes: object) -> Settings:
    values = {
        "db_host": "unused",
        "db_name": "unused",
        "db_user": "unused",
        "db_password": SecretStr("unused"),
        "jwt_secret": SecretStr("j" * 32),
        "csrf_secret": SecretStr("c" * 32),
        "cors_origins": "http://127.0.0.1:5173",
    }
    values.update(changes)
    return Settings(**values)


def test_production_requires_independent_auth_secrets() -> None:
    with pytest.raises(ValidationError):
        auth_settings(environment="production", jwt_secret=None, csrf_secret=None)


def test_jwt_round_trip_and_absolute_session_cap() -> None:
    now = datetime(2026, 11, 7, 8, 0, tzinfo=UTC)
    session_id = uuid4()
    service = JwtService(auth_settings())
    token, expires_in = service.issue(
        user_id=7,
        session_id=session_id,
        session_expires_at=now + timedelta(minutes=5),
        now=now,
    )

    assert expires_in == 300
    unverified = jwt.decode(token, options={"verify_signature": False})
    assert set(("iss", "aud", "sub", "sid", "iat", "nbf", "exp", "jti")) <= set(
        unverified
    )


def test_jwt_rejects_tampering_wrong_algorithm_and_missing_claim() -> None:
    settings = auth_settings()
    service = JwtService(settings)
    now = datetime.now(UTC)
    token, _ = service.issue(
        user_id=1,
        session_id=uuid4(),
        session_expires_at=now + timedelta(hours=1),
        now=now,
    )
    with pytest.raises(ValueError):
        service.decode(f"{token[:-1]}x")

    bad_algorithm = jwt.encode(
        {
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "sub": "1",
            "sid": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=1),
            "jti": str(uuid4()),
        },
        "not-the-real-key" * 4,
        algorithm="HS384",
    )
    with pytest.raises(ValueError):
        service.decode(bad_algorithm)

    missing_claim = jwt.encode(
        {"iss": settings.jwt_issuer, "aud": settings.jwt_audience, "sub": "1"},
        "j" * 32,
        algorithm="HS256",
    )
    with pytest.raises(ValueError):
        service.decode(missing_claim)


def test_jwt_rejects_expired_token() -> None:
    service = JwtService(auth_settings())
    now = datetime.now(UTC) - timedelta(hours=1)
    token, _ = service.issue(
        user_id=1,
        session_id=uuid4(),
        session_expires_at=now + timedelta(minutes=30),
        now=now,
    )
    with pytest.raises(ValueError):
        service.decode(token)


def test_refresh_tokens_are_random_and_digest_only() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()
    assert first != second
    assert len(digest_refresh_token(first)) == 32
    assert digest_refresh_token(first) == digest_refresh_token(first)


def test_csrf_anonymous_and_session_bound_proofs_are_distinct() -> None:
    service = CsrfService(auth_settings())
    session_id = uuid4()
    anonymous = service.issue()
    authenticated = service.issue(session_id)

    service.verify_pair(
        header_token=anonymous,
        cookie_token=anonymous,
        expected_session_id=None,
    )
    service.verify_pair(
        header_token=authenticated,
        cookie_token=authenticated,
        expected_session_id=session_id,
    )
    with pytest.raises(ValueError):
        service.verify_pair(
            header_token=authenticated,
            cookie_token=authenticated,
            expected_session_id=uuid4(),
        )
    with pytest.raises(ValueError):
        service.verify_pair(
            header_token=authenticated,
            cookie_token=f"{authenticated[:-1]}x",
            expected_session_id=session_id,
        )
