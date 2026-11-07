"""Top-level API router."""

from typing import Literal, TypedDict

from fastapi import APIRouter, status

from app.modules.auth.router import router as auth_router
from app.modules.notifications.router import router as notifications_router


class HealthResponse(TypedDict):
    """Health endpoint response payload."""

    status: Literal["ok"]


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(notifications_router)


@api_router.get("/health", status_code=status.HTTP_200_OK)
def health() -> HealthResponse:
    """Report process health without accessing external dependencies."""
    return {"status": "ok"}
