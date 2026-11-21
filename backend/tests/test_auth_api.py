"""HTTP boundary tests for cookies, Origin, CSRF, and cold start."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from pymysql.err import IntegrityError as PyMySQLIntegrityError
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AccountLockedError,
    AccountPendingError,
    AccountRejectedError,
    InvalidCredentialsError,
)
from app.db.session import get_db_session
from app.infrastructure.dependencies import (
    enforce_login_rate_limit,
    enforce_refresh_rate_limit,
    enforce_registration_rate_limit,
)
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.schemas import AuthenticatedUser, RegisterResponse, TokenResponse
from app.modules.auth.security import PasswordHasher
from app.modules.auth.service import (
    REGISTER_ACCEPTED_MESSAGE,
    AuthResult,
    AuthService,
    is_duplicate_email_integrity_error,
)

ORIGIN = "http://127.0.0.1:5173"


@pytest.mark.parametrize(
    ("code", "key", "expected"),
    [
        (1062, "users.uq_users_email_normalized", True),
        (1062, "uq_users_email_normalized", True),
        (1062, "users.uq_users_admin_slot", False),
        (1452, "users.uq_users_email_normalized", False),
    ],
)
def test_duplicate_email_integrity_error_classification(
    code: int, key: str, expected: bool
) -> None:
    driver_error = PyMySQLIntegrityError(
        code, f"Database constraint failure for key '{key}'"
    )
    error = IntegrityError("INSERT users", {}, driver_error)

    assert is_duplicate_email_integrity_error(error) is expected


def auth_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def override_db() -> object:
    yield object()


class FakeLoginService:
    def login(self, _session: object, _email: str, _password: str) -> AuthResult:
        return AuthResult(
            response=TokenResponse(
                access_token="access-token",
                expires_in=900,
                user=AuthenticatedUser(
                    id=1,
                    email_normalized="active@example.com",
                    full_name=None,
                    role="STAFF",
                    status="ACTIVE",
                ),
            ),
            refresh_token="refresh-token",
            csrf_token="csrf-token",
            session_expires_at=datetime.now(UTC) + timedelta(hours=8),
        )


class FakeRegisterService:
    def register(
        self,
        _session: object,
        _email: str,
        _password: str,
        _full_name: str | None = None,
    ) -> RegisterResponse:
        return RegisterResponse(message=REGISTER_ACCEPTED_MESSAGE)


class FakeBlockedLoginService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def login(self, _session: object, _email: str, _password: str) -> AuthResult:
        raise self.error


@pytest.mark.anyio
async def test_register_returns_generic_accepted_response_without_tokens() -> None:
    settings = auth_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = FakeRegisterService
    application.dependency_overrides[enforce_registration_rate_limit] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "new.staff@example.com", "password": "valid-password"},
        )

    assert response.status_code == 202
    assert response.json() == {"message": REGISTER_ACCEPTED_MESSAGE}
    assert "access_token" not in response.text
    assert response.headers.get_list("set-cookie") == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_register_rejects_client_controlled_role() -> None:
    settings = auth_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = FakeRegisterService
    application.dependency_overrides[enforce_registration_rate_limit] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new.staff@example.com",
                "password": "valid-password",
                "role": "ADMIN",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_register_rejects_password_exceeding_bcrypt_byte_limit() -> None:
    settings = auth_settings()
    service = AuthService(settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    application.dependency_overrides[enforce_registration_rate_limit] = lambda: None
    password = "🙂" * 19
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "new.staff@example.com", "password": password},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert password not in response.text


@pytest.mark.anyio
async def test_login_sets_scoped_httponly_refresh_and_csrf_proof() -> None:
    settings = auth_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = FakeLoginService
    application.dependency_overrides[enforce_login_rate_limit] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "active@example.com", "password": "valid-password"},
        )

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    refresh_cookie = next(item for item in cookies if "retailops_refresh=" in item)
    csrf_cookie = next(item for item in cookies if "retailops_csrf=" in item)
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/v1/auth" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert response.headers["x-csrf-token"] == "csrf-token"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (AccountPendingError(), "ACCOUNT_PENDING"),
        (AccountRejectedError(), "ACCOUNT_REJECTED"),
    ],
)
@pytest.mark.anyio
async def test_blocked_login_returns_stable_error_without_auth_cookies(
    error: Exception,
    expected_code: str,
) -> None:
    settings = auth_settings()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: (
        FakeBlockedLoginService(error)
    )
    application.dependency_overrides[enforce_login_rate_limit] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "staff@example.com", "password": "valid-password"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "code": expected_code,
        "message": error.message,
        "details": None,
    }
    assert response.headers.get_list("set-cookie") == []
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text


@pytest.mark.anyio
async def test_csrf_cold_start_does_not_require_session() -> None:
    settings = auth_settings()
    service = AuthService(settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/auth/csrf")

    assert response.status_code == 200
    token = response.json()["csrf_token"]
    service.csrf.verify_pair(
        header_token=token,
        cookie_token=token,
        expected_session_id=None,
    )
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_refresh_rejects_missing_origin_before_database_work() -> None:
    settings = auth_settings()
    service = AuthService(settings)
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = override_db
    application.dependency_overrides[get_auth_service] = lambda: service
    application.dependency_overrides[enforce_refresh_rate_limit] = lambda: None
    session_id = uuid4()
    csrf_token = service.csrf.issue(session_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        client.cookies.set(settings.refresh_cookie_name, "unknown")
        client.cookies.set(settings.csrf_cookie_name, csrf_token)
        response = await client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf_token},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REJECTED"


def test_login_checks_password_before_reporting_locked_status() -> None:
    """Ensure LOCKED status is never disclosed before password verification."""
    settings = auth_settings()
    hasher = PasswordHasher(work_factor=4)
    valid_hash = hasher.hash("correct-password-123")
    active_user = User(
        id=10,
        email_normalized="active@example.com",
        password_hash=valid_hash,
        full_name="Active Staff",
        role=UserRole.STAFF,
        status=UserStatus.ACTIVE,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    locked_user = User(
        id=11,
        email_normalized="locked@example.com",
        password_hash=valid_hash,
        full_name="Locked Staff",
        role=UserRole.STAFF,
        status=UserStatus.LOCKED,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    users_by_email = {
        active_user.email_normalized: active_user,
        locked_user.email_normalized: locked_user,
    }
    users_by_id = {u.id: u for u in users_by_email.values()}

    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.commits = 0
            self.rollbacks = 0

        def add(self, obj: object) -> None:
            self.added.append(obj)

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    class FakeRepo:
        def find_user_by_email(self, _session: object, email: str) -> User | None:
            return users_by_email.get(email)

        def lock_user_by_id(self, _session: object, user_id: int) -> User | None:
            return users_by_id.get(user_id)

        def add_session(
            self, session: FakeSession, auth_session: object, refresh_token: object
        ) -> None:
            session.add((auth_session, refresh_token))

        def add_refresh(self, session: FakeSession, refresh: object) -> None:
            session.add(refresh)

    service = AuthService(
        settings,
        repository=FakeRepo(),  # type: ignore[arg-type]
        password_hasher=hasher,
    )

    # 1. Non-existent email -> INVALID_CREDENTIALS, no session/token created
    s1 = FakeSession()
    with pytest.raises(InvalidCredentialsError):
        service.login(s1, "missing@example.com", "any-password")  # type: ignore[arg-type]
    assert s1.added == [] and s1.commits == 0

    # 2. Existing active email, wrong password -> INVALID_CREDENTIALS
    s2 = FakeSession()
    with pytest.raises(InvalidCredentialsError):
        service.login(s2, "active@example.com", "wrong-password")  # type: ignore[arg-type]
    assert s2.added == [] and s2.commits == 0

    # 3. LOCKED user, wrong password -> INVALID_CREDENTIALS (no enumeration!)
    s3 = FakeSession()
    with pytest.raises(InvalidCredentialsError):
        service.login(s3, "locked@example.com", "wrong-password")  # type: ignore[arg-type]
    assert s3.added == [] and s3.commits == 0

    # 4. LOCKED user, correct password -> ACCOUNT_LOCKED, no session/token created
    s4 = FakeSession()
    with pytest.raises(AccountLockedError):
        service.login(s4, "locked@example.com", "correct-password-123")  # type: ignore[arg-type]
    assert s4.added == [] and s4.commits == 0

    # 5. ACTIVE user, correct password -> Login succeeds with session + tokens
    s5 = FakeSession()
    result = service.login(s5, "active@example.com", "correct-password-123")  # type: ignore[arg-type]
    assert result.response.access_token
    assert result.refresh_token
    assert s5.commits == 1
