"""Authentication security primitives."""

import bcrypt
from email_validator import EmailNotValidError, validate_email

BCRYPT_WORK_FACTOR = 12
BCRYPT_MAX_PASSWORD_BYTES = 72


class InvalidEmailError(ValueError):
    """Raised when an email cannot be represented by the ERD contract."""


class InvalidPasswordError(ValueError):
    """Raised when a password violates bcrypt input constraints."""


def normalize_email(email: str) -> str:
    """Return the approved trimmed, validated, ASCII lowercase identity."""
    candidate = email.strip()
    try:
        candidate.encode("ascii")
    except UnicodeEncodeError as error:
        raise InvalidEmailError("Email must contain ASCII characters only") from error
    try:
        validated = validate_email(candidate, check_deliverability=False)
    except EmailNotValidError as error:
        raise InvalidEmailError("Email syntax is invalid") from error
    normalized = validated.normalized.lower()
    if len(normalized) > 254:
        raise InvalidEmailError("Email exceeds 254 characters")
    return normalized


class PasswordHasher:
    """Central bcrypt password hashing service."""

    def __init__(self, work_factor: int = BCRYPT_WORK_FACTOR) -> None:
        self._work_factor = work_factor

    @staticmethod
    def _encode(password: str) -> bytes:
        encoded = password.encode("utf-8")
        if not encoded:
            raise InvalidPasswordError("Password must not be empty")
        if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
            raise InvalidPasswordError("Password exceeds bcrypt's 72-byte limit")
        return encoded

    def hash(self, password: str) -> str:
        """Hash a password without truncating its UTF-8 representation."""
        encoded = self._encode(password)
        return bcrypt.hashpw(
            encoded,
            bcrypt.gensalt(rounds=self._work_factor),
        ).decode("ascii")

    def verify(self, password: str, password_hash: str) -> bool:
        """Verify a password, treating every invalid input as a non-match."""
        try:
            encoded = self._encode(password)
            encoded_hash = password_hash.encode("ascii")
            return bcrypt.checkpw(encoded, encoded_hash)
        except (
            AttributeError,
            InvalidPasswordError,
            TypeError,
            UnicodeEncodeError,
            ValueError,
        ):
            return False
