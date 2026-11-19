"""HTTP router for sales analytics and dashboard endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.db.session import get_db_session
from app.modules.analytics.schemas import (
    DashboardRead,
    ProductAnalyticsItemRead,
    ProductAnalyticsPageRead,
    SalesSummaryRead,
)
from app.modules.analytics.service import (
    DashboardService,
    ProductAnalyticsItem,
    ProductAnalyticsService,
    SalesAnalyticsService,
    resolve_days_period,
    resolve_sales_period,
)
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])
dashboard_router = APIRouter(tags=["dashboard"])


def get_sales_analytics_service() -> SalesAnalyticsService:
    """Dependency provider for SalesAnalyticsService."""
    return SalesAnalyticsService()


def get_dashboard_service() -> DashboardService:
    """Dependency provider for DashboardService."""
    return DashboardService()


def get_product_analytics_service() -> ProductAnalyticsService:
    """Dependency provider for ProductAnalyticsService."""
    return ProductAnalyticsService()


def _to_product_item_read(item: ProductAnalyticsItem) -> ProductAnalyticsItemRead:
    return ProductAnalyticsItemRead(
        product_id=item.product_id,
        sku=item.sku,
        name=item.name,
        sold_units=item.sold_units,
        revenue_vnd=item.revenue_vnd,
        quantity=item.quantity,
        first_stocked_at=item.first_stocked_at,
    )


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


@router.get("/sales/daily/export/csv")
def export_daily_sales_csv(
    request: Request,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    _admin: Annotated[User, Depends(require_active_admin)] = None,  # type: ignore[assignment]
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
    service: Annotated[
        SalesAnalyticsService, Depends(get_sales_analytics_service)
    ] = None,  # type: ignore[assignment]
) -> Response:
    """Retrieve daily sales analytics as CSV (ADMIN only)."""
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

    return service.export_daily_sales_csv(
        session,
        from_date=effective_from,
        to_date=effective_to,
    )


@dashboard_router.get("/dashboard", response_model=DashboardRead)
def get_dashboard(
    request: Request,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    _admin: Annotated[User, Depends(require_active_admin)] = None,  # type: ignore[assignment]
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
    service: Annotated[DashboardService, Depends(get_dashboard_service)] = None,  # type: ignore[assignment]
) -> DashboardRead:
    """Retrieve executive dashboard metrics for the specified period.

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
    data = service.read(session, period=period)

    return DashboardRead(
        sales=SalesSummaryRead(
            period_start=data.sales.period_start,
            period_end_exclusive=data.sales.period_end_exclusive,
            revenue_vnd=data.sales.revenue_vnd,
            completed_orders=data.sales.completed_orders,
            cancelled_orders=data.sales.cancelled_orders,
            aov_vnd=data.sales.aov_vnd,
        ),
        low_stock_count=data.low_stock_count,
        top_products=[_to_product_item_read(p) for p in data.top_products],
    )


@router.get("/products/top", response_model=ProductAnalyticsPageRead)
def get_top_products(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    days: Annotated[int, Query(ge=1, le=366)] = 7,
    _admin: Annotated[User, Depends(require_active_admin)] = None,  # type: ignore[assignment]
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
    service: Annotated[
        ProductAnalyticsService, Depends(get_product_analytics_service)
    ] = None,  # type: ignore[assignment]
) -> ProductAnalyticsPageRead:
    """Retrieve paginated top-selling products for COMPLETED orders (ADMIN only)."""
    period = resolve_days_period(days)
    result = service.top(session, period=period, page=page, page_size=page_size)
    return ProductAnalyticsPageRead(
        items=[_to_product_item_read(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/products/slow", response_model=ProductAnalyticsPageRead)
def get_slow_products(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    _admin: Annotated[User, Depends(require_active_admin)] = None,  # type: ignore[assignment]
    session: Annotated[Session, Depends(get_db_session)] = None,  # type: ignore[assignment]
    service: Annotated[
        ProductAnalyticsService, Depends(get_product_analytics_service)
    ] = None,  # type: ignore[assignment]
) -> ProductAnalyticsPageRead:
    """Retrieve paginated slow-moving ACTIVE products (ADMIN only)."""
    result = service.slow(session, page=page, page_size=page_size)
    return ProductAnalyticsPageRead(
        items=[_to_product_item_read(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )
