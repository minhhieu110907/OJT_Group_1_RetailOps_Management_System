"""Top-level API router."""

import hashlib
import hmac
import re
from typing import Literal, TypedDict

from fastapi import APIRouter, Header, Request, Response, status
from sqlalchemy import text

from app.db.session import get_session_factory
from app.modules.ai.router import router as ai_router
from app.modules.analytics.router import dashboard_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.account_router import admin_router as staff_accounts_router
from app.modules.auth.account_router import profile_router as profile_router
from app.modules.auth.approval_router import router as staff_approval_router
from app.modules.auth.router import router as auth_router
from app.modules.categories.router import category_router
from app.modules.inventory.router import (
    router as inventory_router,
)
from app.modules.inventory.router import (
    stock_movements_router,
)
from app.modules.notifications.router import router as notifications_router
from app.modules.products.router import router as products_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.sales.router import router as sales_router
from app.modules.suppliers.router import supplier_router


class HealthResponse(TypedDict):
    """Health endpoint response payload."""

    status: Literal["ok"]


api_router = APIRouter()
BENCHMARK_CHALLENGE_HEADER = "X-RetailOps-Benchmark-Challenge"
BENCHMARK_ATTESTATION_HEADER = "X-RetailOps-Benchmark-Attestation"
_CHALLENGE_PATTERN = re.compile(r"[0-9a-f]{64}")
api_router.include_router(auth_router)
api_router.include_router(staff_approval_router)
api_router.include_router(staff_accounts_router)
api_router.include_router(profile_router)
api_router.include_router(notifications_router)
api_router.include_router(category_router)
api_router.include_router(inventory_router)
api_router.include_router(stock_movements_router)
api_router.include_router(supplier_router)
api_router.include_router(products_router)
api_router.include_router(purchasing_router)
api_router.include_router(sales_router)
api_router.include_router(analytics_router)
api_router.include_router(dashboard_router)
api_router.include_router(ai_router)


@api_router.get("/health", status_code=status.HTTP_200_OK)
def health(
    request: Request,
    response: Response,
    benchmark_challenge: str | None = Header(
        default=None, alias=BENCHMARK_CHALLENGE_HEADER
    ),
) -> HealthResponse:
    """Report process health and optionally prove an isolated benchmark target."""
    settings = request.app.state.settings
    secret = settings.benchmark_attestation_secret
    expected_database = settings.benchmark_isolated_database
    if (
        benchmark_challenge is not None
        and _CHALLENGE_PATTERN.fullmatch(benchmark_challenge)
        and secret is not None
        and expected_database is not None
        and settings.environment.strip().casefold() == "test"
    ):
        with get_session_factory()() as session:
            actual_database = session.scalar(text("SELECT DATABASE()"))
        if actual_database == expected_database:
            database_digest = hashlib.sha256(actual_database.encode()).hexdigest()
            payload = f"v1:{benchmark_challenge}:{database_digest}"
            signature = hmac.new(
                secret.get_secret_value().encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            response.headers[BENCHMARK_ATTESTATION_HEADER] = (
                f"v1:{database_digest}:{signature}"
            )
    return {"status": "ok"}
