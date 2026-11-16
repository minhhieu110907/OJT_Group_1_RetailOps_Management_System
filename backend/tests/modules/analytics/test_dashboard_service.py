"""Unit tests for DashboardService façade and default adapter."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.analytics.repository import SalesAnalyticsRepository
from app.modules.analytics.service import (
    DashboardData,
    DashboardService,
    DefaultProductAnalyticsAdapter,
    Period,
    ProductAnalyticsItem,
    SalesAnalyticsService,
    SalesSummary,
)


def test_dashboard_service_combines_all_three_sources() -> None:
    """DashboardService combines sales KPI, low-stock count, and top products."""
    mock_session = MagicMock(spec=Session)

    mock_sales_service = MagicMock(spec=SalesAnalyticsService)
    fixed_sales = SalesSummary(
        period_start=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        period_end_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
        revenue_vnd=250_000,
        completed_orders=2,
        cancelled_orders=1,
        aov_vnd=125_000,
    )
    mock_sales_service.summary.return_value = fixed_sales

    mock_low_stock_counter = MagicMock(return_value=7)

    mock_product_adapter = MagicMock()
    mock_product_adapter.top.return_value = [
        ProductAnalyticsItem(
            product_id=10,
            sku="SKU-TOP-1",
            name="Cà phê đen",
            sold_units=5,
            revenue_vnd=150_000,
            quantity=12,
            first_stocked_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC),
        ),
        ProductAnalyticsItem(
            product_id=20,
            sku="SKU-TOP-2",
            name="Trà sữa trân châu",
            sold_units=3,
            revenue_vnd=100_000,
            quantity=4,
            first_stocked_at=datetime(2026, 11, 5, 8, 0, 0, tzinfo=UTC),
        ),
    ]

    service = DashboardService(
        sales_service=mock_sales_service,
        product_analytics=mock_product_adapter,
        low_stock_counter=mock_low_stock_counter,
    )

    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    result = service.read(mock_session, period=period)

    assert isinstance(result, DashboardData)
    assert result.sales == fixed_sales
    assert result.low_stock_count == 7
    assert len(result.top_products) == 2
    assert result.top_products[0].sku == "SKU-TOP-1"
    assert result.top_products[0].sold_units == 5
    assert result.top_products[1].sku == "SKU-TOP-2"

    # Verify delegation calls
    mock_sales_service.summary.assert_called_once_with(mock_session, period=period)
    mock_low_stock_counter.assert_called_once_with(mock_session)
    mock_product_adapter.top.assert_called_once_with(
        mock_session, period=period, page=1, page_size=5
    )

    # Read-only invariant: session.commit and rollback must never be called
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_not_called()


def test_dashboard_service_empty_period_zero_metrics() -> None:
    """Empty period returns zero sales, zero low-stock, and empty top products."""
    mock_session = MagicMock(spec=Session)

    mock_sales_service = MagicMock(spec=SalesAnalyticsService)
    mock_sales_service.summary.return_value = SalesSummary(
        period_start=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        period_end_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
        revenue_vnd=0,
        completed_orders=0,
        cancelled_orders=0,
        aov_vnd=0,
    )

    mock_low_stock_counter = MagicMock(return_value=0)
    mock_product_adapter = MagicMock()
    mock_product_adapter.top.return_value = []

    service = DashboardService(
        sales_service=mock_sales_service,
        product_analytics=mock_product_adapter,
        low_stock_counter=mock_low_stock_counter,
    )

    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    result = service.read(mock_session, period=period)

    assert result.sales.revenue_vnd == 0
    assert result.sales.completed_orders == 0
    assert result.sales.cancelled_orders == 0
    assert result.sales.aov_vnd == 0
    assert result.low_stock_count == 0
    assert result.top_products == ()

    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_not_called()


def test_default_product_analytics_adapter_delegates_to_repo() -> None:
    """DefaultProductAnalyticsAdapter queries repository and maps to dataclasses."""
    mock_session = MagicMock(spec=Session)
    mock_repo = MagicMock(spec=SalesAnalyticsRepository)
    mock_repo.get_top_products.return_value = [
        {
            "product_id": 1,
            "sku": "SKU-1",
            "name": "Sản phẩm 1",
            "sold_units": 10,
            "revenue_vnd": 500_000,
            "quantity": 15,
            "first_stocked_at": datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC),
        }
    ]

    adapter = DefaultProductAnalyticsAdapter(repository=mock_repo)
    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    items = adapter.top(mock_session, period=period, page=1, page_size=5)

    assert len(items) == 1
    assert items[0].product_id == 1
    assert items[0].sku == "SKU-1"
    assert items[0].sold_units == 10
    assert items[0].revenue_vnd == 500_000

    mock_repo.get_top_products.assert_called_once_with(
        mock_session,
        start_utc=period.start_utc,
        end_utc_exclusive=period.end_utc_exclusive,
        limit=5,
        offset=0,
    )


def test_default_product_analytics_adapter_pagination_offset() -> None:
    """Adapter translates page and page_size into SQL limit and offset."""
    mock_session = MagicMock(spec=Session)
    mock_repo = MagicMock(spec=SalesAnalyticsRepository)
    mock_repo.get_top_products.return_value = []

    adapter = DefaultProductAnalyticsAdapter(repository=mock_repo)
    period = Period(
        start_utc=datetime(2026, 11, 17, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 18, 17, 0, 0, tzinfo=UTC),
    )
    adapter.top(mock_session, period=period, page=3, page_size=10)

    mock_repo.get_top_products.assert_called_once_with(
        mock_session,
        start_utc=period.start_utc,
        end_utc_exclusive=period.end_utc_exclusive,
        limit=10,
        offset=20,
    )


def test_dashboard_service_default_low_stock_counter_calls_count_low_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_default_low_stock_count invokes count_low_stock on InventoryQueryRepository."""
    mock_session = MagicMock(spec=Session)
    mock_inv_repo = MagicMock()
    mock_inv_repo.count_low_stock.return_value = 42

    monkeypatch.setattr(
        "app.modules.inventory.repository.InventoryQueryRepository",
        lambda: mock_inv_repo,
    )

    count = DashboardService._default_low_stock_count(mock_session)
    assert count == 42
    mock_inv_repo.count_low_stock.assert_called_once_with(mock_session, threshold=5)
