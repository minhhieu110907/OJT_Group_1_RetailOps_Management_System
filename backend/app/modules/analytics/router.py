"""HTTP router for sales analytics endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.db.session import get_db_session
from app.modules.analytics.schemas import SalesSummaryRead
from app.modules.analytics.service import (
    SalesAnalyticsService,
    resolve_sales_period,
)
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_sales_analytics_service() -> SalesAnalyticsService:
    """Dependency provider for SalesAnalyticsService."""
    return SalesAnalyticsService()


@router.get("/sales", response_model=SalesSummaryRead)
def get_sales_analytics(
    request: Request,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    _admin: Annotated[User, Depends(require_active_admin)] = None,  # type: ignore[assignment]
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
    service: Annotated[
        SalesAnalyticsService, Depends(get_sales_analytics_service)
    ] = None,  # type: ignore[assignment]
) -> SalesSummaryRead:
    """Retrieve sales summary analytics for the specified period.

    Role: ADMIN only.
    Query parameters:
    - from: start date (YYYY-MM-DD), inclusive. Defaults to today VN if both omitted.
    - to: end date (YYYY-MM-DD), inclusive. Defaults to today VN.
    """
    effective_from = from_date
    if effective_from is None and "from_date" in request.query_params:
        try:
            effective_from = date.fromisoformat(request.query_params["from_date"])
        except ValueError as err:
            raise DomainValidationError("Định dạng from_date không hợp lệ.") from err

    effective_to = to_date
    if effective_to is None and "to_date" in request.query_params:
        try:
            effective_to = date.fromisoformat(request.query_params["to_date"])
        except ValueError as err:
            raise DomainValidationError("Định dạng to_date không hợp lệ.") from err

    period = resolve_sales_period(from_date=effective_from, to_date=effective_to)
    summary = service.summary(session, period=period)

    return SalesSummaryRead(
        period_start=summary.period_start,
        period_end_exclusive=summary.period_end_exclusive,
        revenue_vnd=summary.revenue_vnd,
        completed_orders=summary.completed_orders,
        cancelled_orders=summary.cancelled_orders,
        aov_vnd=summary.aov_vnd,
    )
