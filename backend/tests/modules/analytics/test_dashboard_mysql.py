"""MySQL integration tests for T04AA36 Dashboard API."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.analytics.service import (
    DashboardService,
    resolve_sales_period,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.models import Inventory
from app.modules.inventory.repository import InventoryQueryRepository
from app.modules.products.models import CatalogStatus, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04AA36_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_dashboard_test_rows(migrated_integration_engine: Engine):
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


def test_dashboard_mysql_aggregation_and_sources(
    migrated_integration_engine: Engine,
) -> None:
    """Validate full Dashboard aggregation on real MySQL:

    - Sales KPI: only COMPLETED orders in target period count.
    - Sales KPI: CANCELLED orders count towards cancelled_orders.
    - Low-stock count: active products with quantity <= 5.
    - Top products: sorted by sold_units DESC, revenue_vnd DESC, product_id ASC.
    - Excludes cancelled orders and out-of-period orders from top products.
    """
    now_unaware = datetime.now(UTC).replace(tzinfo=None)

    # Fixed target date in Vietnam time: 2026-11-25
    period = resolve_sales_period(
        from_date=date(2026, 11, 25), to_date=date(2026, 11, 25)
    )

    t_in_period_1 = datetime(2026, 11, 25, 2, 0, 0)
    t_in_period_2 = datetime(2026, 11, 25, 6, 0, 0)
    t_in_period_3 = datetime(2026, 11, 25, 9, 0, 0)
    t_cancelled_later = datetime(2026, 11, 26, 2, 0, 0)
    t_outside_period = datetime(2026, 11, 20, 2, 0, 0)

    # Check baseline low stock count before inserting test data
    with Session(migrated_integration_engine) as session:
        baseline_low_stock = InventoryQueryRepository().list_low_stock(
            session, page=1, page_size=1, threshold=5
        )[1]

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

        # Product A: ACTIVE, low stock (qty=3)
        prod_a = Product(
            sku=f"{TEST_PREFIX}SKU_A_{uuid4().hex[:6]}",
            name="Product A",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=20_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # Product B: ACTIVE, low stock (qty=5)
        prod_b = Product(
            sku=f"{TEST_PREFIX}SKU_B_{uuid4().hex[:6]}",
            name="Product B",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=25_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # Product C: ACTIVE, normal stock (qty=20 > 5)
        prod_c = Product(
            sku=f"{TEST_PREFIX}SKU_C_{uuid4().hex[:6]}",
            name="Product C",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=30_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # Product D: INACTIVE, low stock (qty=1 <= 5) -> not in low_stock
        prod_d = Product(
            sku=f"{TEST_PREFIX}SKU_D_{uuid4().hex[:6]}",
            name="Product D (Archived)",
            category_id=category.id,
            status=CatalogStatus.ARCHIVED.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([prod_a, prod_b, prod_c, prod_d])
        session.flush()

        inv_a = Inventory(
            product_id=prod_a.id,
            quantity=3,
            first_stocked_at=now_unaware,
            last_stocked_at=now_unaware,
        )
        inv_b = Inventory(
            product_id=prod_b.id,
            quantity=5,
            first_stocked_at=now_unaware,
            last_stocked_at=now_unaware,
        )
        inv_c = Inventory(
            product_id=prod_c.id,
            quantity=20,
            first_stocked_at=now_unaware,
            last_stocked_at=now_unaware,
        )
        inv_d = Inventory(
            product_id=prod_d.id,
            quantity=1,
            first_stocked_at=now_unaware,
            last_stocked_at=now_unaware,
        )
        session.add_all([inv_a, inv_b, inv_c, inv_d])
        session.flush()

        # Order 1 (COMPLETED, in period): 5 prod_a (100k) + 2 prod_b (50k) = 150k
        order1 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=150_000,
            created_by=admin.id,
            sold_at=t_in_period_1,
        )
        session.add(order1)
        session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=order1.id,
                    product_id=prod_a.id,
                    sku_snapshot=prod_a.sku,
                    product_name_snapshot=prod_a.name,
                    quantity=5,
                    unit_price_vnd=20_000,
                    line_total_vnd=100_000,
                ),
                OrderItem(
                    order_id=order1.id,
                    product_id=prod_b.id,
                    sku_snapshot=prod_b.sku,
                    product_name_snapshot=prod_b.name,
                    quantity=2,
                    unit_price_vnd=25_000,
                    line_total_vnd=50_000,
                ),
            ]
        )

        # Order 2 (COMPLETED, in period): 3 prod_b (75k) + 1 prod_c (30k) = 105k
        order2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=105_000,
            created_by=admin.id,
            sold_at=t_in_period_2,
        )
        session.add(order2)
        session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=order2.id,
                    product_id=prod_b.id,
                    sku_snapshot=prod_b.sku,
                    product_name_snapshot=prod_b.name,
                    quantity=3,
                    unit_price_vnd=25_000,
                    line_total_vnd=75_000,
                ),
                OrderItem(
                    order_id=order2.id,
                    product_id=prod_c.id,
                    sku_snapshot=prod_c.sku,
                    product_name_snapshot=prod_c.name,
                    quantity=1,
                    unit_price_vnd=30_000,
                    line_total_vnd=30_000,
                ),
            ]
        )

        # Order 3 (CANCELLED): 10 prod_a. Must NOT count towards top products!
        order3 = Order(
            status=OrderStatus.CANCELLED.value,
            total_vnd=200_000,
            created_by=admin.id,
            sold_at=t_in_period_3,
            cancelled_by=admin.id,
            cancelled_at=t_cancelled_later,
            cancel_reason="Customer cancelled",
        )
        session.add(order3)
        session.flush()
        session.add(
            OrderItem(
                order_id=order3.id,
                product_id=prod_a.id,
                sku_snapshot=prod_a.sku,
                product_name_snapshot=prod_a.name,
                quantity=10,
                unit_price_vnd=20_000,
                line_total_vnd=200_000,
            )
        )

        # Order 4 (COMPLETED, outside period): 100 prod_c (3,000k). Must NOT count!
        order4 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=3_000_000,
            created_by=admin.id,
            sold_at=t_outside_period,
        )
        session.add(order4)
        session.flush()
        session.add(
            OrderItem(
                order_id=order4.id,
                product_id=prod_c.id,
                sku_snapshot=prod_c.sku,
                product_name_snapshot=prod_c.name,
                quantity=100,
                unit_price_vnd=30_000,
                line_total_vnd=3_000_000,
            )
        )

    # Query with DashboardService on real MySQL
    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=period)

    # Verify Sales KPI
    assert data.sales.revenue_vnd == 255_000  # order1 (150k) + order2 (105k)
    assert data.sales.completed_orders == 2
    assert data.sales.cancelled_orders == 1
    assert data.sales.aov_vnd == 127_500  # 255_000 / 2

    # Verify Low Stock count
    # Prod A (3 <= 5) and Prod B (5 <= 5) are active -> +2
    # Prod C is > 5; Prod D is ARCHIVED -> not counted
    assert data.low_stock_count == baseline_low_stock + 2

    # Verify Top Products
    # Prod B: 2 + 3 = 5 units, 125,000 VND
    # Prod A: 5 units, 100,000 VND
    # Prod C: 1 unit, 30,000 VND
    # Both B and A have 5 sold_units, but B has higher revenue -> B rank 1, A rank 2
    top_skus = [p.sku for p in data.top_products]
    assert prod_b.sku in top_skus
    assert prod_a.sku in top_skus
    assert prod_c.sku in top_skus

    # Find the positions
    b_idx = top_skus.index(prod_b.sku)
    a_idx = top_skus.index(prod_a.sku)
    c_idx = top_skus.index(prod_c.sku)

    assert b_idx < a_idx < c_idx
    assert data.top_products[b_idx].sold_units == 5
    assert data.top_products[b_idx].revenue_vnd == 125_000
    assert data.top_products[b_idx].quantity == 5
    assert data.top_products[a_idx].sold_units == 5
    assert data.top_products[a_idx].revenue_vnd == 100_000
    assert data.top_products[a_idx].quantity == 3


def test_dashboard_mysql_empty_period(
    migrated_integration_engine: Engine,
) -> None:
    """Empty period returns 0 sales and empty top_products without SQL errors."""
    empty_period = resolve_sales_period(
        from_date=date(2020, 1, 1), to_date=date(2020, 1, 1)
    )

    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=empty_period)

    assert data.sales.revenue_vnd == 0
    assert data.sales.completed_orders == 0
    assert data.sales.cancelled_orders == 0
    assert data.sales.aov_vnd == 0
    assert data.top_products == ()
    assert data.low_stock_count >= 0
