"""Top-level API router."""

from typing import Literal, TypedDict

from fastapi import APIRouter, status


class HealthResponse(TypedDict):
    """Health endpoint response payload."""

    status: Literal["ok"]


api_router = APIRouter()


@api_router.get("/health", status_code=status.HTTP_200_OK)
def health() -> HealthResponse:
    """Report process health without accessing external dependencies."""
    return {"status": "ok"}
