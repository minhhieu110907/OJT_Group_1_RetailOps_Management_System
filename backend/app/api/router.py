"""Top-level API router."""

from typing import Literal, TypedDict

from fastapi import APIRouter, status

from app.modules.auth.approval_router import router as staff_approval_router
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import category_router
from app.modules.notifications.router import router as notifications_router
from app.modules.products.router import router as products_router
from app.modules.suppliers.router import supplier_router


class HealthResponse(TypedDict):
    """Health endpoint response payload."""

    status: Literal["ok"]


api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(staff_approval_router)
api_router.include_router(notifications_router)
api_router.include_router(category_router)
api_router.include_router(supplier_router)
api_router.include_router(products_router)


@api_router.get("/health", status_code=status.HTTP_200_OK)
def health() -> HealthResponse:
    """Report process health without accessing external dependencies."""
    return {"status": "ok"}
