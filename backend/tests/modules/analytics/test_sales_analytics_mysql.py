"""MySQL integration tests for T04A92B Sales Analytics."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.analytics.service import (
    SalesAnalyticsService,
    resolve_sales_period,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.models import Inventory
from app.modules.products.models import CatalogStatus, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04A92B_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_analytics_test_rows(migrated_integration_engine: Engine):
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        user_ids = list(
            session.scalars(
                select(User.id).where(
                    User.email_normalized.like(f"{TEST_PREFIX.lower()}%")
                )
            )
        )
        if user_ids:
            order_ids = list(
                session.scalars(select(Order.id).where(Order.created_by.in_(user_ids)))
            )
            if order_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
                )
                session.execute(delete(Order).where(Order.id.in_(order_ids)))

        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{TEST_PREFIX}%"))
            )
        )
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        session.execute(delete(Category).where(Category.name.like(f"{TEST_PREFIX}%")))
        if user_ids:
            session.execute(delete(User).where(User.id.in_(user_ids)))


def test_sales_analytics_mysql_aggregation_and_boundaries(
    migrated_integration_engine: Engine,
) -> None:
    """Validate sales aggregation on real MySQL:

    - Only COMPLETED orders count towards revenue and completed_orders.
    - CANCELLED orders count towards cancelled_orders by sold_at, not cancelled_at.
    - Orders outside the target period are excluded.
    - AOV is rounded ROUND_HALF_UP.
    """
    now_unaware = datetime.now(UTC).replace(tzinfo=None)

    # Pick a fixed date in Vietnam time: 2026-11-18
    # Period: [2026-11-17 17:00:00 UTC, 2026-11-18 17:00:00 UTC)
    period = resolve_sales_period(
        from_date=date(2026, 11, 18), to_date=date(2026, 11, 18)
    )

    t_in_period_1 = datetime(2026, 11, 18, 2, 0, 0)  # 09:00 VN
    t_in_period_2 = datetime(2026, 11, 18, 5, 0, 0)  # 12:00 VN
    t_in_period_3 = datetime(2026, 11, 18, 8, 0, 0)  # 15:00 VN
    t_cancelled_later = datetime(2026, 11, 19, 3, 0, 0)  # cancelled next day
    t_outside_past = datetime(2026, 11, 15, 2, 0, 0)  # 3 days earlier

    with Session(migrated_integration_engine) as session, session.begin():
        admin = User(
            email_normalized=f"{TEST_PREFIX.lower()}admin_{uuid4().hex[:6]}@example.com",
            password_hash="$2b$04$test.hash.admin",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        category = Category(
            name=f"{TEST_PREFIX}Cat_{uuid4().hex[:6]}",
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([admin, category])
        session.flush()

        product = Product(
            sku=f"{TEST_PREFIX}SKU_{uuid4().hex[:6]}",
            name="Analytics Test Product",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=50_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(product)
        session.flush()

        # Order 1 (COMPLETED, in period): 100,000 VND
        order1 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=100_000,
            created_by=admin.id,
            sold_at=t_in_period_1,
        )
        session.add(order1)
        session.flush()
        session.add(
            OrderItem(
                order_id=order1.id,
                product_id=product.id,
                sku_snapshot=product.sku,
                product_name_snapshot=product.name,
                quantity=2,
                unit_price_vnd=50_000,
                line_total_vnd=100_000,
            )
        )

        # Order 2 (COMPLETED, in period): 30,000 VND
        order2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=30_000,
            created_by=admin.id,
            sold_at=t_in_period_2,
        )
        session.add(order2)
        session.flush()
        session.add(
            OrderItem(
                order_id=order2.id,
                product_id=product.id,
                sku_snapshot=product.sku,
                product_name_snapshot=product.name,
                quantity=1,
                unit_price_vnd=30_000,
                line_total_vnd=30_000,
            )
        )

        # Order 3 (CANCELLED, sold in period, cancelled next day): 50,000 VND
        order3 = Order(
            status=OrderStatus.CANCELLED.value,
            total_vnd=50_000,
            created_by=admin.id,
            sold_at=t_in_period_3,
            cancelled_by=admin.id,
            cancelled_at=t_cancelled_later,
            cancel_reason="Customer change of mind",
        )
        session.add(order3)
        session.flush()
        session.add(
            OrderItem(
                order_id=order3.id,
                product_id=product.id,
                sku_snapshot=product.sku,
                product_name_snapshot=product.name,
                quantity=1,
                unit_price_vnd=50_000,
                line_total_vnd=50_000,
            )
        )

        # Order 4 (COMPLETED, outside period): 200,000 VND
        order4 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=200_000,
            created_by=admin.id,
            sold_at=t_outside_past,
        )
        session.add(order4)
        session.flush()
        session.add(
            OrderItem(
                order_id=order4.id,
                product_id=product.id,
                sku_snapshot=product.sku,
                product_name_snapshot=product.name,
                quantity=4,
                unit_price_vnd=50_000,
                line_total_vnd=200_000,
            )
        )

    # Query with SalesAnalyticsService on real MySQL
    service = SalesAnalyticsService()
    with Session(migrated_integration_engine) as session:
        summary = service.summary(session, period=period)

    # Expected:
    # revenue_vnd = order1 (100k) + order2 (30k) = 130k
    # completed_orders = 2 (order1, order2)
    # cancelled_orders = 1 (order3)
    # aov_vnd = 130,000 / 2 = 65,000
    assert summary.revenue_vnd == 130_000
    assert summary.completed_orders == 2
    assert summary.cancelled_orders == 1
    assert summary.aov_vnd == 65_000
    assert summary.period_start == period.start_utc
    assert summary.period_end_exclusive == period.end_utc_exclusive


def test_sales_analytics_mysql_empty_period(
    migrated_integration_engine: Engine,
) -> None:
    """Empty period returns all zeroes without SQL error or division by zero."""
    empty_period = resolve_sales_period(
        from_date=date(2020, 1, 1), to_date=date(2020, 1, 1)
    )

    service = SalesAnalyticsService()
    with Session(migrated_integration_engine) as session:
        summary = service.summary(session, period=empty_period)

    assert summary.revenue_vnd == 0
    assert summary.completed_orders == 0
    assert summary.cancelled_orders == 0
    assert summary.aov_vnd == 0
