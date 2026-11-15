"""Service layer for sales analytics calculations and period resolution."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.analytics.repository import SalesAnalyticsRepository

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
