"""Authentication security primitives without database side effects."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import bcrypt
import jwt
from email_validator import EmailNotValidError, validate_email
from jwt import InvalidTokenError

from app.core.config import Settings

BCRYPT_WORK_FACTOR = 12
BCRYPT_MAX_PASSWORD_BYTES = 72
JWT_ALGORITHM = "HS256"
CSRF_VERSION = "v1"
ANONYMOUS_CSRF_BINDING = "anonymous"


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


def generate_refresh_token() -> str:
    """Return an opaque refresh token with at least 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def digest_refresh_token(token: str) -> bytes:
    """Return the fixed-width digest stored in MySQL."""
    return hashlib.sha256(token.encode("ascii")).digest()


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: int
    session_id: UUID


class JwtService:
    """Issue and strictly validate HS256 access tokens."""

    def __init__(self, settings: Settings) -> None:
        jwt_secret, _ = settings.require_auth_secrets()
        self._secret = jwt_secret
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._ttl = settings.access_token_ttl_seconds

    def issue(
        self,
        *,
        user_id: int,
        session_id: UUID,
        session_expires_at: datetime,
        now: datetime | None = None,
    ) -> tuple[str, int]:
        issued_at = now or datetime.now(UTC)
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=UTC)
        absolute_expiry = session_expires_at
        if absolute_expiry.tzinfo is None:
            absolute_expiry = absolute_expiry.replace(tzinfo=UTC)
        expires_at = min(issued_at + timedelta(seconds=self._ttl), absolute_expiry)
        expires_in = max(0, int((expires_at - issued_at).total_seconds()))
        if expires_in <= 0:
            raise ValueError("Cannot issue an access token for an expired session")
        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "jti": str(uuid4()),
        }
        return jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM), expires_in

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[JWT_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["iss", "aud", "sub", "sid", "iat", "nbf", "exp", "jti"]
                },
            )
            user_id = int(payload["sub"])
            session_id = UUID(payload["sid"])
            if user_id <= 0:
                raise ValueError
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid access token") from error
        return AccessTokenClaims(user_id=user_id, session_id=session_id)


class CsrfService:
    """Issue HMAC-signed, expiring double-submit proofs."""

    def __init__(self, settings: Settings) -> None:
        _, csrf_secret = settings.require_auth_secrets()
        self._secret = csrf_secret
        self._ttl = settings.csrf_ttl_seconds

    def issue(self, session_id: UUID | None = None, now: datetime | None = None) -> str:
        current = now or datetime.now(UTC)
        expires_at = int(current.timestamp()) + self._ttl
        binding = str(session_id) if session_id is not None else ANONYMOUS_CSRF_BINDING
        nonce = secrets.token_urlsafe(24)
        unsigned = f"{CSRF_VERSION}.{binding}.{expires_at}.{nonce}"
        signature = hmac.new(
            self._secret, unsigned.encode(), hashlib.sha256
        ).hexdigest()
        return f"{unsigned}.{signature}"

    def verify_pair(
        self,
        *,
        header_token: str | None,
        cookie_token: str | None,
        expected_session_id: UUID | None,
        now: datetime | None = None,
    ) -> None:
        if (
            not header_token
            or not cookie_token
            or not hmac.compare_digest(header_token, cookie_token)
        ):
            raise ValueError("CSRF double-submit mismatch")
        parts = header_token.split(".")
        if len(parts) != 5:
            raise ValueError("Malformed CSRF token")
        version, binding, expires_raw, nonce, signature = parts
        unsigned = ".".join(parts[:-1])
        expected_signature = hmac.new(
            self._secret, unsigned.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("Invalid CSRF signature")
        expected_binding = (
            str(expected_session_id)
            if expected_session_id is not None
            else ANONYMOUS_CSRF_BINDING
        )
        current = now or datetime.now(UTC)
        if (
            version != CSRF_VERSION
            or not nonce
            or not hmac.compare_digest(binding, expected_binding)
            or int(expires_raw) < int(current.timestamp())
        ):
            raise ValueError("Invalid or expired CSRF token")

    def session_binding(self, token: str) -> UUID | None:
        """Validate a proof and return its authenticated session binding."""
        parts = token.split(".")
        if len(parts) != 5:
            raise ValueError("Malformed CSRF token")
        binding = parts[1]
        expected = None if binding == ANONYMOUS_CSRF_BINDING else UUID(binding)
        self.verify_pair(
            header_token=token,
            cookie_token=token,
            expected_session_id=expected,
        )
        return expected
