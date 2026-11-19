"""HTTP boundary for authentication cookies, headers, and DTOs."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.infrastructure.dependencies import (
    enforce_forgot_password_rate_limit,
    enforce_login_rate_limit,
    enforce_refresh_rate_limit,
    enforce_registration_rate_limit,
    enforce_reset_password_rate_limit,
)
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    bearer_scheme,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.reset_email import build_password_reset_email_adapter
from app.modules.auth.reset_service import AuthResetService
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    CsrfResponse,
    ForgotPasswordRequest,
    GenericMessageResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_registration_rate_limit)],
)
def register(
    payload: RegisterRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> RegisterResponse:
    response.headers["Cache-Control"] = "no-store"
    return service.register(
        session, str(payload.email), payload.password, payload.full_name
    )


def _set_auth_cookies(
    response: Response,
    result: AuthResult,
    settings: Settings,
) -> None:
    expires_at = result.session_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    remaining = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=result.refresh_token,
        max_age=remaining,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path=settings.auth_cookie_path,
    )
    _set_csrf_cookie(response, result.csrf_token, settings)
    response.headers["X-CSRF-Token"] = result.csrf_token
    response.headers["Cache-Control"] = "no-store"


def _set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.csrf_ttl_seconds,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path=settings.auth_cookie_path,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    result = service.login(session, str(payload.email), payload.password)
    _set_auth_cookies(response, result, settings)
    return result.response


@router.get("/csrf", response_model=CsrfResponse)
def csrf(
    request: Request,
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CsrfResponse:
    access_token = credentials.credentials if credentials is not None else None
    session_id = service.csrf_binding(
        session,
        access_token,
        request.cookies.get(settings.refresh_cookie_name),
    )
    token = service.csrf.issue(session_id)
    _set_csrf_cookie(response, token, settings)
    response.headers["Cache-Control"] = "no-store"
    return CsrfResponse(csrf_token=token)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_refresh_rate_limit)],
)
def refresh(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header()] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> TokenResponse:
    result = service.refresh(
        session,
        request.cookies.get(settings.refresh_cookie_name),
        csrf_header,
        request.cookies.get(settings.csrf_cookie_name),
        origin,
    )
    _set_auth_cookies(response, result, settings)
    return result.response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header()] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    service.logout(
        session,
        request.cookies.get(settings.refresh_cookie_name),
        csrf_header,
        request.cookies.get(settings.csrf_cookie_name),
        origin,
    )
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.auth_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path=settings.auth_cookie_path,
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def get_auth_reset_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResetService:
    """Dependency provider for AuthResetService."""
    if (
        settings.environment.strip().lower() == "production"
        and not settings.password_reset_base_url.startswith("https://")
    ):
        raise RuntimeError(
            "RETAILOPS_PASSWORD_RESET_BASE_URL must be explicitly configured "
            "with HTTPS in production"
        )
    return AuthResetService(
        email_port=build_password_reset_email_adapter(settings),
        reset_base_url=settings.password_reset_base_url,
        token_ttl_seconds=settings.password_reset_ttl_seconds,
    )


@router.post(
    "/forgot-password",
    response_model=GenericMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_forgot_password_rate_limit)],
)
def forgot_password(
    payload: ForgotPasswordRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthResetService, Depends(get_auth_reset_service)],
) -> GenericMessageResponse:
    """Initiate STAFF password reset with a generic non-enumerating 202 response."""
    response.headers["Cache-Control"] = "no-store"
    ack = service.request_reset(session, email=str(payload.email))
    return GenericMessageResponse(message=ack.message)


@router.post(
    "/reset-password",
    response_model=GenericMessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_reset_password_rate_limit)],
)
def reset_password(
    payload: ResetPasswordRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AuthResetService, Depends(get_auth_reset_service)],
) -> GenericMessageResponse:
    """Consume a one-time reset token, update STAFF password, and revoke sessions."""
    response.headers["Cache-Control"] = "no-store"
    ack = service.consume_reset(
        session,
        token=payload.token,
        new_password=payload.new_password,
    )
    return GenericMessageResponse(message=ack.message)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header()] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> TokenResponse:
    """Authenticated change: validate cookie+CSRF, rotate current refresh.

    The new access token must replace the caller's in-memory token. No
    automatic retry of this mutation is permitted by the frontend client.
    """
    result = service.change_password(
        session,
        actor_id=principal.user.id,
        session_id=principal.session_id,
        current_password=payload.current_password,
        new_password=payload.new_password,
        refresh_token=request.cookies.get(settings.refresh_cookie_name),
        csrf_header=csrf_header,
        csrf_cookie=request.cookies.get(settings.csrf_cookie_name),
        origin=origin,
    )
    _set_auth_cookies(response, result, settings)
    return result.response
