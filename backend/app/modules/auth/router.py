"""HTTP boundary for authentication cookies, headers, and DTOs."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.auth.dependencies import bearer_scheme, get_auth_service
from app.modules.auth.schemas import CsrfResponse, LoginRequest, TokenResponse
from app.modules.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/login", response_model=TokenResponse)
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


@router.post("/refresh", response_model=TokenResponse)
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
