"""Service layer for sales analytics calculations and period resolution."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.analytics.repository import SalesAnalyticsRepository
from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD, LowStockPage
from app.modules.inventory.service import InventoryQueryService

VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
try:
    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:  # pragma: no cover
    VN_TZ = VIETNAM_TIMEZONE

MAX_QUERY_DAYS = 365


@dataclass(frozen=True)
class Period:
    """UTC boundary period matching retailops_extended_ports.pyi."""

    start_utc: datetime
    end_utc_exclusive: datetime


@dataclass(frozen=True)
class SalesSummary:
    """Sales KPI summary matching retailops_extended_ports.pyi."""

    period_start: datetime
    period_end_exclusive: datetime
    revenue_vnd: int
    completed_orders: int
    cancelled_orders: int
    aov_vnd: int


@dataclass(frozen=True)
class ProductAnalyticsItem:
    """Product performance metric item matching retailops_extended_ports.pyi."""

    product_id: int
    sku: str
    name: str
    sold_units: int
    revenue_vnd: int
    quantity: int | None = None
    first_stocked_at: datetime | None = None


@dataclass(frozen=True)
class ProductAnalyticsPage:
    """Paginated product analytics result."""

    items: tuple[ProductAnalyticsItem, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class DashboardData:
    """Dashboard metrics aggregate matching ports DashboardRead."""

    sales: SalesSummary
    low_stock_count: int
    top_products: tuple[ProductAnalyticsItem, ...]


def resolve_sales_period(
    from_date: date | None = None,
    to_date: date | None = None,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> Period:
    """Resolve Vietnam business date range into half-open UTC bounds.

    Returns:
        Period with [start_utc, end_utc_exclusive) boundaries.

    Rules:
    - Omit both: default to today in VN time (from_date = to_date = today_vn).
    - Omit to: default to_date = today_vn.
    - Omit from: default from_date = to_date.
    - Validations:
      - to_date >= date.max -> 422 DomainValidationError.
      - from_date > to_date -> 422 DomainValidationError.
      - (to_date - from_date).days > 365 -> 422 DomainValidationError.
    """
    now_dt = now_fn() if now_fn is not None else datetime.now(VN_TZ)
    today_vn = now_dt.astimezone(VN_TZ).date()

    resolved_from = from_date
    resolved_to = to_date

    if resolved_from is None and resolved_to is None:
        resolved_from = today_vn
        resolved_to = today_vn
    elif resolved_from is not None and resolved_to is None:
        resolved_to = today_vn
    elif resolved_from is None and resolved_to is not None:
        resolved_from = resolved_to

    assert resolved_from is not None
    assert resolved_to is not None

    if resolved_to >= date.max:
        raise DomainValidationError("Giá trị to vượt giới hạn cho phép.")

    if resolved_from <= date.min:
        raise DomainValidationError("Giá trị from vượt giới hạn cho phép.")

    if resolved_from > resolved_to:
        raise DomainValidationError("from must not be greater than to")

    if (resolved_to - resolved_from).days > MAX_QUERY_DAYS:
        raise DomainValidationError(
            "Khoảng thời gian tra cứu không được vượt quá 366 ngày."
        )

    try:
        start_utc = datetime.combine(resolved_from, time.min, tzinfo=VN_TZ).astimezone(
            UTC
        )
        end_utc_exclusive = datetime.combine(
            resolved_to + timedelta(days=1), time.min, tzinfo=VN_TZ
        ).astimezone(UTC)
    except OverflowError as err:
        raise DomainValidationError("Khoảng ngày lọc vượt giới hạn cho phép.") from err

    return Period(start_utc=start_utc, end_utc_exclusive=end_utc_exclusive)


def resolve_days_period(
    days: int = 7,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> Period:
    """Resolve rolling N Vietnam business days (1..366) into half-open UTC bounds."""
    if days < 1 or days > 366:
        raise DomainValidationError(
            "Số ngày tra cứu phải nằm trong khoảng từ 1 đến 366."
        )
    now_dt = now_fn() if now_fn is not None else datetime.now(VN_TZ)
    today_vn = now_dt.astimezone(VN_TZ).date()
    from_date = today_vn - timedelta(days=days - 1)
    return resolve_sales_period(from_date=from_date, to_date=today_vn, now_fn=now_fn)


class SalesAnalyticsService:
    """Read-only sales analytics service computing revenue, order counts and AOV."""

    def __init__(
        self,
        repository: SalesAnalyticsRepository | None = None,
    ) -> None:
        self._repository = repository or SalesAnalyticsRepository()

    def summary(self, session: Session, *, period: Period) -> SalesSummary:
        """Compute sales KPI summary for the given UTC period.

        Never commits or rolls back the session (read-only invariant).
        """
        raw = self._repository.aggregate_sales(
            session,
            start_utc=period.start_utc,
            end_utc_exclusive=period.end_utc_exclusive,
        )

        revenue_vnd = int(raw["revenue_vnd"])
        completed_orders = int(raw["completed_orders"])
        cancelled_orders = int(raw["cancelled_orders"])

        if completed_orders == 0:
            aov_vnd = 0
        else:
            aov_vnd = int(
                (Decimal(revenue_vnd) / Decimal(completed_orders)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )

        return SalesSummary(
            period_start=period.start_utc,
            period_end_exclusive=period.end_utc_exclusive,
            revenue_vnd=revenue_vnd,
            completed_orders=completed_orders,
            cancelled_orders=cancelled_orders,
            aov_vnd=aov_vnd,
        )


class ProductAnalyticsPort(Protocol):
    """Protocol for product analytics top product query."""

    def top(
        self,
        session: Session,
        *,
        period: Period,
        page: int = 1,
        page_size: int = 5,
    ) -> list[ProductAnalyticsItem]: ...


class DefaultProductAnalyticsAdapter:
    """Default SQL-backed adapter implementing ProductAnalyticsPort."""

    def __init__(self, repository: SalesAnalyticsRepository | None = None) -> None:
        self._repository = repository or SalesAnalyticsRepository()

    def top(
        self,
        session: Session,
        *,
        period: Period,
        page: int = 1,
        page_size: int = 5,
    ) -> list[ProductAnalyticsItem]:
        """Fetch top products by sold quantity and revenue.

        Internal Top-N adapter for Dashboard. Windowing is handled via limit and offset.
        """
        offset = max(page - 1, 0) * max(page_size, 0)
        raw_items = self._repository.get_top_products(
            session,
            start_utc=period.start_utc,
            end_utc_exclusive=period.end_utc_exclusive,
            limit=page_size,
            offset=offset,
        )
        return [
            ProductAnalyticsItem(
                product_id=item["product_id"],
                sku=item["sku"],
                name=item["name"],
                sold_units=item["sold_units"],
                revenue_vnd=item["revenue_vnd"],
                quantity=item["quantity"],
                first_stocked_at=item["first_stocked_at"],
            )
            for item in raw_items
        ]


def _to_product_analytics_item(item: dict) -> ProductAnalyticsItem:
    return ProductAnalyticsItem(
        product_id=item["product_id"],
        sku=item["sku"],
        name=item["name"],
        sold_units=item["sold_units"],
        revenue_vnd=item["revenue_vnd"],
        quantity=item["quantity"],
        first_stocked_at=item["first_stocked_at"],
    )


class ProductAnalyticsService:
    """Read-only product analytics service for top, slow-moving, and low-stock."""

    def __init__(
        self,
        repository: SalesAnalyticsRepository | None = None,
        inventory_query: InventoryQueryService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository or SalesAnalyticsRepository()
        self._inventory_query = inventory_query or InventoryQueryService()
        self._clock = clock or (lambda: datetime.now(UTC))

    def top(
        self,
        session: Session,
        *,
        period: Period,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductAnalyticsPage:
        """Return paginated top-selling products for COMPLETED orders in period."""
        offset = (page - 1) * page_size
        raw_items = self._repository.get_top_products(
            session,
            start_utc=period.start_utc,
            end_utc_exclusive=period.end_utc_exclusive,
            limit=page_size,
            offset=offset,
        )
        total = self._repository.count_top_products(
            session,
            start_utc=period.start_utc,
            end_utc_exclusive=period.end_utc_exclusive,
        )
        return ProductAnalyticsPage(
            items=tuple(_to_product_analytics_item(i) for i in raw_items),
            total=total,
            page=page,
            page_size=page_size,
        )

    def slow(
        self,
        session: Session,
        *,
        as_of_utc: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductAnalyticsPage:
        """Return paginated slow-moving ACTIVE products (>7d stocked, <=2 sold/30d)."""
        effective_now = as_of_utc if as_of_utc is not None else self._clock()
        offset = (page - 1) * page_size
        raw_items, total = self._repository.list_slow_products(
            session,
            as_of_utc=effective_now,
            limit=page_size,
            offset=offset,
        )
        return ProductAnalyticsPage(
            items=tuple(_to_product_analytics_item(i) for i in raw_items),
            total=total,
            page=page,
            page_size=page_size,
        )

    def low_stock(
        self,
        session: Session,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> LowStockPage:
        """Delegate low-stock query to InventoryQueryService with P0 threshold."""
        return self._inventory_query.get_low_stock(
            session=session,
            page=page,
            page_size=page_size,
            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        )


class DashboardService:
    """Read-only dashboard façade aggregating sales, low stock, and top products."""

    def __init__(
        self,
        sales_service: SalesAnalyticsService | None = None,
        product_analytics: ProductAnalyticsPort | None = None,
        low_stock_counter: Callable[[Session], int] | None = None,
    ) -> None:
        self._sales_service = sales_service or SalesAnalyticsService()
        self._product_analytics = product_analytics or DefaultProductAnalyticsAdapter()
        self._low_stock_counter = low_stock_counter or self._default_low_stock_count

    @staticmethod
    def _default_low_stock_count(session: Session) -> int:
        from app.modules.inventory.repository import InventoryQueryRepository
        from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD

        return InventoryQueryRepository().count_low_stock(
            session, threshold=DEFAULT_LOW_STOCK_THRESHOLD
        )

    def read(self, session: Session, *, period: Period) -> DashboardData:
        """Aggregate sales summary, low stock count, and top products.

        Never commits or rolls back the session (read-only invariant).
        """
        sales = self._sales_service.summary(session, period=period)
        low_stock_count = self._low_stock_counter(session)
        top_products = self._product_analytics.top(
            session, period=period, page=1, page_size=5
        )

        return DashboardData(
            sales=sales,
            low_stock_count=low_stock_count,
            top_products=tuple(top_products),
        )
