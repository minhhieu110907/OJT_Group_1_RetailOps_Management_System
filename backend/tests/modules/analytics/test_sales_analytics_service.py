"""Unit tests for SalesAnalyticsService and period resolution."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.analytics.repository import SalesAnalyticsRepository
from app.modules.analytics.service import (
    VN_TZ,
    Period,
    SalesAnalyticsService,
    SalesSummary,
    resolve_sales_period,
)


def test_resolve_sales_period_default_today() -> None:
    """When from and to are omitted, defaults to today in Vietnam time."""
    fixed_now = datetime(2026, 11, 18, 10, 30, 0, tzinfo=VN_TZ)
    period = resolve_sales_period(now_fn=lambda: fixed_now)

    # Vietnam 2026-11-18 00:00:00 is UTC 2026-11-17 17:00:00
    expected_start = datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC)
    # Vietnam 2026-11-19 00:00:00 is UTC 2026-11-18 17:00:00
    expected_end = datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC)

    assert period.start_utc == expected_start
    assert period.end_utc_exclusive == expected_end


def test_resolve_sales_period_only_from_defaults_to_today() -> None:
    """When only from is provided, to defaults to today in Vietnam time."""
    fixed_now = datetime(2026, 11, 20, 15, 0, 0, tzinfo=VN_TZ)
    period = resolve_sales_period(
        from_date=date(2026, 11, 18), now_fn=lambda: fixed_now
    )

    expected_start = datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC)
    expected_end = datetime(2026, 11, 20, 17, 0, 0, tzinfo=UTC)

    assert period.start_utc == expected_start
    assert period.end_utc_exclusive == expected_end


def test_resolve_sales_period_only_to_defaults_from_to_to() -> None:
    """When only to is provided, from defaults to to_date (single day)."""
    period = resolve_sales_period(to_date=date(2026, 11, 15))

    expected_start = datetime(2026, 11, 14, 17, 0, 0, tzinfo=UTC)
    expected_end = datetime(2026, 11, 15, 17, 0, 0, tzinfo=UTC)

    assert period.start_utc == expected_start
    assert period.end_utc_exclusive == expected_end


def test_resolve_sales_period_explicit_range() -> None:
    """Explicit from and to range creates half-open UTC bounds."""
    period = resolve_sales_period(
        from_date=date(2026, 11, 1), to_date=date(2026, 11, 5)
    )

    expected_start = datetime(2026, 10, 31, 17, 0, 0, tzinfo=UTC)
    expected_end = datetime(2026, 11, 5, 17, 0, 0, tzinfo=UTC)

    assert period.start_utc == expected_start
    assert period.end_utc_exclusive == expected_end


def test_resolve_sales_period_validation_from_greater_than_to() -> None:
    """from_date > to_date raises 422 DomainValidationError."""
    with pytest.raises(DomainValidationError, match="from must not be greater than to"):
        resolve_sales_period(from_date=date(2026, 11, 20), to_date=date(2026, 11, 10))


def test_resolve_sales_period_validation_date_max_overflow() -> None:
    """to_date >= date.max raises 422 DomainValidationError."""
    with pytest.raises(DomainValidationError, match="vượt giới hạn"):
        resolve_sales_period(to_date=date.max)


def test_resolve_sales_period_validation_date_min_underflow() -> None:
    """from_date <= date.min raises 422 DomainValidationError."""
    with pytest.raises(DomainValidationError, match="vượt giới hạn"):
        resolve_sales_period(from_date=date.min, to_date=date.min)


def test_resolve_sales_period_month_boundaries() -> None:
    """Valid range across month boundary resolves correct UTC bounds."""
    # Month boundary: Jan 31 -> Feb 1
    period = resolve_sales_period(from_date=date(2026, 1, 31), to_date=date(2026, 2, 1))
    assert period.start_utc == datetime(2026, 1, 30, 17, 0, 0, tzinfo=UTC)
    assert period.end_utc_exclusive == datetime(2026, 2, 1, 17, 0, 0, tzinfo=UTC)

    # Leap year month boundary: Feb 28 -> Mar 1 (2024 is leap year)
    period_leap = resolve_sales_period(
        from_date=date(2024, 2, 28), to_date=date(2024, 3, 1)
    )
    assert period_leap.start_utc == datetime(2024, 2, 27, 17, 0, 0, tzinfo=UTC)
    assert period_leap.end_utc_exclusive == datetime(2024, 3, 1, 17, 0, 0, tzinfo=UTC)


def test_resolve_sales_period_utc_boundary_shift() -> None:
    """Verify Vietnam business date shifts exactly -7 hours to half-open UTC bounds."""
    period = resolve_sales_period(
        from_date=date(2026, 6, 15), to_date=date(2026, 6, 15)
    )
    # 2026-06-15 00:00:00+07:00 == 2026-06-14 17:00:00 UTC
    assert period.start_utc == datetime(2026, 6, 14, 17, 0, 0, tzinfo=UTC)
    # 2026-06-16 00:00:00+07:00 == 2026-06-15 17:00:00 UTC
    assert period.end_utc_exclusive == datetime(2026, 6, 15, 17, 0, 0, tzinfo=UTC)


def test_resolve_sales_period_valid_near_min_date() -> None:
    """Earliest safely convertible date 0001-01-02 resolves without error."""
    period = resolve_sales_period(from_date=date(1, 1, 2), to_date=date(1, 1, 2))
    assert period.start_utc == datetime(1, 1, 1, 17, 0, 0, tzinfo=UTC)
    assert period.end_utc_exclusive == datetime(1, 1, 2, 17, 0, 0, tzinfo=UTC)


def test_resolve_sales_period_validation_exceeds_max_days() -> None:
    """Date span exceeding 365 days raises 422 DomainValidationError."""
    with pytest.raises(DomainValidationError, match="không được vượt quá 366 ngày"):
        resolve_sales_period(from_date=date(2024, 1, 1), to_date=date(2025, 1, 2))


def test_sales_analytics_service_empty_period_zero_aov() -> None:
    """When completed_orders is 0, aov_vnd must be 0 (no divide-by-zero)."""
    mock_session = MagicMock(spec=Session)
    mock_repo = MagicMock(spec=SalesAnalyticsRepository)
    mock_repo.aggregate_sales.return_value = {
        "revenue_vnd": 0,
        "completed_orders": 0,
        "cancelled_orders": 0,
    }

    service = SalesAnalyticsService(repository=mock_repo)
    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    summary = service.summary(mock_session, period=period)

    assert isinstance(summary, SalesSummary)
    assert summary.revenue_vnd == 0
    assert summary.completed_orders == 0
    assert summary.cancelled_orders == 0
    assert summary.aov_vnd == 0
    assert summary.period_start == period.start_utc
    assert summary.period_end_exclusive == period.end_utc_exclusive

    # Read-only invariant: session.commit and rollback must never be called
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("revenue_vnd", "completed_orders", "expected_aov"),
    [
        (100_001, 2, 50_001),  # 50000.5 -> rounds up to 50001
        (100_000, 3, 33_333),  # 33333.333... -> 33333
        (200_000, 3, 66_667),  # 66666.666... -> rounds up to 66667
        (500_000, 1, 500_000),  # exact division
        (130_000, 1, 130_000),  # openapi example match
    ],
)
def test_sales_analytics_service_round_half_up(
    revenue_vnd: int, completed_orders: int, expected_aov: int
) -> None:
    """AOV must follow standard commercial ROUND_HALF_UP rounding."""
    mock_session = MagicMock(spec=Session)
    mock_repo = MagicMock(spec=SalesAnalyticsRepository)
    mock_repo.aggregate_sales.return_value = {
        "revenue_vnd": revenue_vnd,
        "completed_orders": completed_orders,
        "cancelled_orders": 2,
    }

    service = SalesAnalyticsService(repository=mock_repo)
    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    summary = service.summary(mock_session, period=period)

    assert summary.revenue_vnd == revenue_vnd
    assert summary.completed_orders == completed_orders
    assert summary.cancelled_orders == 2
    assert summary.aov_vnd == expected_aov

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_not_called()
