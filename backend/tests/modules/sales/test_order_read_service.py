"""Unit tests for OrderReadService logic, dates, search, and exceptions."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import (
    DomainValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.repository import _escape_like
from app.modules.sales.schemas import OrderPage, OrderRead
from app.modules.sales.service import OrderQuery, OrderReadService


def test_order_read_service_requires_admin_or_staff() -> None:
    service = OrderReadService()
    session = MagicMock()
    with pytest.raises(ForbiddenError):
        service.list(
            session,
            actor_id=1,
            actor_role="GUEST",
            filters=OrderQuery(),
        )

    with pytest.raises(ForbiddenError):
        service.get(
            session,
            actor_id=1,
            actor_role="UNKNOWN",
            order_id=1,
        )


def test_from_date_greater_than_to_date_raises_domain_validation_error() -> None:
    service = OrderReadService()
    session = MagicMock()
    filters = OrderQuery(
        from_date=date(2026, 11, 15),
        to_date=date(2026, 11, 14),
    )
    with pytest.raises(
        DomainValidationError, match="from_date must not be greater than to_date"
    ):
        service.list(
            session,
            actor_id=1,
            actor_role="STAFF",
            filters=filters,
        )


def test_to_date_overflow_raises_domain_validation_error() -> None:
    service = OrderReadService()
    session = MagicMock()
    filters = OrderQuery(to_date=date.max)
    with pytest.raises(
        DomainValidationError, match="Giá trị to_date vượt giới hạn cho phép."
    ):
        service.list(
            session,
            actor_id=1,
            actor_role="STAFF",
            filters=filters,
        )


def test_vietnam_business_date_to_utc_conversion() -> None:
    repo = MagicMock()
    repo.list_orders.return_value = ([], 0)
    service = OrderReadService(repository=repo)
    session = MagicMock()

    filters = OrderQuery(
        from_date=date(2026, 11, 14),
        to_date=date(2026, 11, 14),
    )
    result = service.list(
        session,
        actor_id=1,
        actor_role="STAFF",
        filters=filters,
    )

    assert isinstance(result, OrderPage)
    assert result.total == 0
    assert result.items == []

    # Check that repo.list_orders was called with correct UTC timestamps:
    # 2026-11-14 00:00:00 VN (+07) -> 2026-11-13 17:00:00 UTC
    # 2026-11-15 00:00:00 VN (+07) -> 2026-11-14 17:00:00 UTC
    repo.list_orders.assert_called_once_with(
        session,
        status=None,
        sold_from_utc=datetime(2026, 11, 13, 17, 0, 0),
        sold_to_utc_exclusive=datetime(2026, 11, 14, 17, 0, 0),
        order_id_exact=None,
        sku_search=None,
        offset=0,
        limit=20,
    )


def test_search_parsing_logic() -> None:
    repo = MagicMock()
    repo.list_orders.return_value = ([], 0)
    service = OrderReadService(repository=repo)
    session = MagicMock()

    # 1. Blank search
    service.list(
        session,
        actor_id=1,
        actor_role="ADMIN",
        filters=OrderQuery(search="   "),
    )
    repo.list_orders.assert_called_with(
        session,
        status=None,
        sold_from_utc=None,
        sold_to_utc_exclusive=None,
        order_id_exact=None,
        sku_search=None,
        offset=0,
        limit=20,
    )

    # 2. Integer search (Order ID & SKU)
    service.list(
        session,
        actor_id=1,
        actor_role="ADMIN",
        filters=OrderQuery(search="  42  "),
    )
    repo.list_orders.assert_called_with(
        session,
        status=None,
        sold_from_utc=None,
        sold_to_utc_exclusive=None,
        order_id_exact=42,
        sku_search="42",
        offset=0,
        limit=20,
    )

    # 3. Text SKU search
    service.list(
        session,
        actor_id=1,
        actor_role="STAFF",
        filters=OrderQuery(search="  SKU-MILK-99  "),
    )
    repo.list_orders.assert_called_with(
        session,
        status=None,
        sold_from_utc=None,
        sold_to_utc_exclusive=None,
        order_id_exact=None,
        sku_search="SKU-MILK-99",
        offset=0,
        limit=20,
    )


def test_get_order_not_found_raises_resource_not_found() -> None:
    repo = MagicMock()
    repo.get_by_id.return_value = None
    service = OrderReadService(repository=repo)
    session = MagicMock()

    with pytest.raises(ResourceNotFoundError, match="Không tìm thấy đơn hàng"):
        service.get(session, actor_id=1, actor_role="STAFF", order_id=999)


def test_get_order_success() -> None:
    order = Order(
        id=10,
        status="COMPLETED",
        total_vnd=50_000,
        created_by=2,
        sold_at=datetime(2026, 11, 14, 3, 0, 0),  # Naive UTC
        cancelled_by=None,
        cancelled_at=None,
        cancel_reason=None,
    )
    order.items = [
        OrderItem(
            order_id=10,
            product_id=5,
            sku_snapshot="SKU-005",
            product_name_snapshot="Cà phê",
            quantity=2,
            unit_price_vnd=25_000,
            line_total_vnd=50_000,
        )
    ]

    repo = MagicMock()
    repo.get_by_id.return_value = order
    service = OrderReadService(repository=repo)
    session = MagicMock()

    result = service.get(session, actor_id=1, actor_role="STAFF", order_id=10)
    assert isinstance(result, OrderRead)
    assert result.id == 10
    assert result.status == "COMPLETED"
    assert result.total_vnd == 50_000
    assert result.sold_at.tzinfo == UTC
    assert len(result.items) == 1
    assert result.items[0].sku_snapshot == "SKU-005"
    assert result.items[0].quantity == 2


def test_escape_like_helper() -> None:
    assert _escape_like("plain") == "plain"
    assert _escape_like("50%") == "50\\%"
    assert _escape_like("item_1") == "item\\_1"
    assert _escape_like("path\\file") == "path\\\\file"
    assert _escape_like("50%_off\\now") == "50\\%\\_off\\\\now"
