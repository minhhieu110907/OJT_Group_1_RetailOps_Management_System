"""Unit tests for Auth security primitives."""

import pytest

from app.modules.auth.security import (
    InvalidEmailError,
    InvalidPasswordError,
    PasswordHasher,
    normalize_email,
)


def test_normalize_email_trims_validates_and_lowercases() -> None:
    assert normalize_email("  Admin.Example@EXAMPLE.COM  ") == (
        "admin.example@example.com"
    )


@pytest.mark.parametrize("email", ["not-an-email", "tést@example.com", ""])
def test_normalize_email_rejects_invalid_or_non_ascii(email: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(email)


def test_bcrypt_hash_uses_cost_12_and_verifies() -> None:
    hasher = PasswordHasher()
    password_hash = hasher.hash("correct horse battery staple")

    assert password_hash.split("$")[2] == "12"
    assert hasher.verify("correct horse battery staple", password_hash)
    assert not hasher.verify("wrong password", password_hash)
    assert "correct horse battery staple" not in password_hash


def test_bcrypt_rejects_passwords_over_72_utf8_bytes_without_truncation() -> None:
    hasher = PasswordHasher(work_factor=4)

    with pytest.raises(InvalidPasswordError):
        hasher.hash("é" * 37)
    assert not hasher.verify("a" * 73, "$2b$12$invalid")


def test_bcrypt_malformed_hash_is_a_non_match() -> None:
    hasher = PasswordHasher(work_factor=4)

    assert not hasher.verify("valid password", "not-a-hash")
    assert not hasher.verify("", "not-a-hash")
    assert not hasher.verify("a" * 73, "not-a-hash")
    assert not hasher.verify("valid password", "nót-ascii")
