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
    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        user_ids = list(
            session.scalars(
                select(User.id).where(
                    User.email_normalized.like(f"{TEST_PREFIX.lower()}%")
                )
            )
        )
        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{TEST_PREFIX}%"))
            )
        )
        if product_ids:
            session.execute(
                delete(OrderItem).where(OrderItem.product_id.in_(product_ids))
            )
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
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

        if product_ids:
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        session.execute(delete(Category).where(Category.name.like(f"{TEST_PREFIX}%")))
        if user_ids:
            session.execute(delete(User).where(User.id.in_(user_ids)))


def _create_test_context(
    session: Session, now_unaware: datetime
) -> tuple[User, Category]:
    """Helper creating a test admin user and product category."""
    admin = User(
        email_normalized=f"{TEST_PREFIX.lower()}adm_{uuid4().hex[:6]}@example.com",
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
    return admin, category


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
        baseline_low_stock = InventoryQueryRepository().count_low_stock(
            session, threshold=5
        )

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin, category = _create_test_context(session, now_unaware)

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
            name="Product D (Inactive)",
            category_id=category.id,
            status=CatalogStatus.INACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([prod_a, prod_b, prod_c, prod_d])
        session.flush()

        inv_a = Inventory(
            product_id=prod_a.id,
            quantity=3,
            stock_version=0,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        inv_b = Inventory(
            product_id=prod_b.id,
            quantity=5,
            stock_version=0,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        inv_c = Inventory(
            product_id=prod_c.id,
            quantity=20,
            stock_version=0,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        inv_d = Inventory(
            product_id=prod_d.id,
            quantity=1,
            stock_version=0,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
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

        session.flush()
        prod_a_sku = prod_a.sku
        prod_b_sku = prod_b.sku
        prod_c_sku = prod_c.sku

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
    # Prod C is > 5; Prod D is INACTIVE -> not counted
    assert data.low_stock_count == baseline_low_stock + 2

    # Verify Top Products
    top_skus = [p.sku for p in data.top_products]
    assert prod_b_sku in top_skus
    assert prod_a_sku in top_skus
    assert prod_c_sku in top_skus

    b_idx = top_skus.index(prod_b_sku)
    a_idx = top_skus.index(prod_a_sku)
    c_idx = top_skus.index(prod_c_sku)

    assert b_idx < a_idx < c_idx
    assert data.top_products[b_idx].sold_units == 5
    assert data.top_products[b_idx].revenue_vnd == 125_000
    assert data.top_products[b_idx].quantity == 5
    assert data.top_products[a_idx].sold_units == 5
    assert data.top_products[a_idx].revenue_vnd == 100_000
    assert data.top_products[a_idx].quantity == 3


def test_top_products_same_product_different_snapshots(
    migrated_integration_engine: Engine,
) -> None:
    """Test A: Product sold under multiple historical snapshots aggregates once.

    When a product had an older name or SKU in past orders, the query must:
    1. Group by Product ID so it appears at most ONCE.
    2. Sum sold_units (12 + 8 = 20) and revenue_vnd across all orders.
    3. Return current product master name and SKU.
    """
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    period = resolve_sales_period(
        from_date=date(2026, 11, 25), to_date=date(2026, 11, 25)
    )
    t_sold = datetime(2026, 11, 25, 4, 0, 0)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin, category = _create_test_context(session, now_unaware)

        prod = Product(
            sku=f"{TEST_PREFIX}SKU_SNAP_{uuid4().hex[:6]}",
            name="Product Master Current Name",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(prod)
        session.flush()

        session.add(
            Inventory(
                product_id=prod.id,
                quantity=15,
                stock_version=0,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
        )
        session.flush()

        # Order 1: old name snapshot, sold 12 units = 120,000 VND
        o1 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=120_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o1)
        session.flush()
        session.add(
            OrderItem(
                order_id=o1.id,
                product_id=prod.id,
                sku_snapshot="OLD-SKU-SNAPSHOT",
                product_name_snapshot="Old Historical Name Snapshot",
                quantity=12,
                unit_price_vnd=10_000,
                line_total_vnd=120_000,
            )
        )

        # Order 2: current name snapshot, sold 8 units = 80,000 VND
        o2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=80_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o2)
        session.flush()
        session.add(
            OrderItem(
                order_id=o2.id,
                product_id=prod.id,
                sku_snapshot=prod.sku,
                product_name_snapshot=prod.name,
                quantity=8,
                unit_price_vnd=10_000,
                line_total_vnd=80_000,
            )
        )

        session.flush()
        target_prod_id = prod.id
        target_sku = prod.sku
        target_name = prod.name

    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=period)

    matching_items = [p for p in data.top_products if p.product_id == target_prod_id]
    # Invariant: Appears at most once
    assert len(matching_items) == 1
    item = matching_items[0]
    assert item.sku == target_sku
    assert item.name == target_name
    assert item.sold_units == 20  # 12 + 8
    assert item.revenue_vnd == 200_000  # 120k + 80k
    assert item.quantity == 15


def test_top_products_top_5_limit_with_snapshot_changes(
    migrated_integration_engine: Engine,
) -> None:
    """Test B: Exactly 5 products returned; multi-snapshot product doesn't steal rank.

    Setup 6 products. P1 has two orders with different snapshots (10 + 15 = 25).
    P2 (20), P3 (15), P4 (10), P5 (5), P6 (1).
    Expected Top 5: P1 (25), P2 (20), P3 (15), P4 (10), P5 (5).
    P6 must be excluded; P1 must not appear twice.
    """
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    period = resolve_sales_period(
        from_date=date(2026, 11, 25), to_date=date(2026, 11, 25)
    )
    t_sold = datetime(2026, 11, 25, 5, 0, 0)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin, category = _create_test_context(session, now_unaware)

        # Create 6 products
        prods = [
            Product(
                sku=f"{TEST_PREFIX}P{i}_{uuid4().hex[:4]}",
                name=f"Product {i}",
                category_id=category.id,
                status=CatalogStatus.ACTIVE.value,
                sale_price_vnd=10_000,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            for i in range(1, 7)
        ]
        session.add_all(prods)
        session.flush()

        for p in prods:
            session.add(
                Inventory(
                    product_id=p.id,
                    quantity=50,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                )
            )
        session.flush()

        # P1: 2 orders with different name snapshots -> 10 + 15 = 25
        o1 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=100_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o1)
        session.flush()
        session.add(
            OrderItem(
                order_id=o1.id,
                product_id=prods[0].id,
                sku_snapshot="OLD-SKU-P1",
                product_name_snapshot="Old P1 Name",
                quantity=10,
                unit_price_vnd=10_000,
                line_total_vnd=100_000,
            )
        )

        o2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=150_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o2)
        session.flush()
        session.add(
            OrderItem(
                order_id=o2.id,
                product_id=prods[0].id,
                sku_snapshot=prods[0].sku,
                product_name_snapshot=prods[0].name,
                quantity=15,
                unit_price_vnd=10_000,
                line_total_vnd=150_000,
            )
        )

        # P2: 20 units, P3: 15 units, P4: 10 units, P5: 5 units, P6: 1 unit
        quantities = [20, 15, 10, 5, 1]
        for p, q in zip(prods[1:], quantities, strict=True):
            o = Order(
                status=OrderStatus.COMPLETED.value,
                total_vnd=q * 10_000,
                created_by=admin.id,
                sold_at=t_sold,
            )
            session.add(o)
            session.flush()
            session.add(
                OrderItem(
                    order_id=o.id,
                    product_id=p.id,
                    sku_snapshot=p.sku,
                    product_name_snapshot=p.name,
                    quantity=q,
                    unit_price_vnd=10_000,
                    line_total_vnd=q * 10_000,
                )
            )

        session.flush()
        p1_id = prods[0].id
        p6_id = prods[5].id

    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=period)

    # Invariant: Top 5 limit preserved
    assert len(data.top_products) <= 5
    top_ids = [p.product_id for p in data.top_products]
    assert p1_id in top_ids
    assert p6_id not in top_ids
    # P1 appears exactly once and is rank 1
    assert top_ids[0] == p1_id
    assert data.top_products[0].sold_units == 25


def test_top_products_deterministic_tie_breaking(
    migrated_integration_engine: Engine,
) -> None:
    """Test C: Tie-breaking is deterministic (revenue_vnd DESC, then product_id ASC)."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    period = resolve_sales_period(
        from_date=date(2026, 11, 25), to_date=date(2026, 11, 25)
    )
    t_sold = datetime(2026, 11, 25, 6, 0, 0)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin, category = _create_test_context(session, now_unaware)

        # P_high_rev: 10 units @ 20,000 = 200,000 VND
        # P_low_rev:  10 units @ 10,000 = 100,000 VND
        p_high_rev = Product(
            sku=f"{TEST_PREFIX}HIGH_REV_{uuid4().hex[:4]}",
            name="High Rev Product",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=20_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        p_low_rev = Product(
            sku=f"{TEST_PREFIX}LOW_REV_{uuid4().hex[:4]}",
            name="Low Rev Product",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([p_high_rev, p_low_rev])
        session.flush()

        for p in (p_high_rev, p_low_rev):
            session.add(
                Inventory(
                    product_id=p.id,
                    quantity=30,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                )
            )
        session.flush()

        o = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=300_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o)
        session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=o.id,
                    product_id=p_high_rev.id,
                    sku_snapshot=p_high_rev.sku,
                    product_name_snapshot=p_high_rev.name,
                    quantity=10,
                    unit_price_vnd=20_000,
                    line_total_vnd=200_000,
                ),
                OrderItem(
                    order_id=o.id,
                    product_id=p_low_rev.id,
                    sku_snapshot=p_low_rev.sku,
                    product_name_snapshot=p_low_rev.name,
                    quantity=10,
                    unit_price_vnd=10_000,
                    line_total_vnd=100_000,
                ),
            ]
        )
        session.flush()
        high_id = p_high_rev.id
        low_id = p_low_rev.id

    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=period)

    top_ids = [p.product_id for p in data.top_products]
    assert high_id in top_ids
    assert low_id in top_ids
    # Higher revenue must rank before lower revenue when sold_units are equal
    assert top_ids.index(high_id) < top_ids.index(low_id)


def test_top_products_inactive_and_missing_inventory(
    migrated_integration_engine: Engine,
) -> None:
    """Test E: INACTIVE product with sales included; missing inventory handled."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    period = resolve_sales_period(
        from_date=date(2026, 11, 25), to_date=date(2026, 11, 25)
    )
    t_sold = datetime(2026, 11, 25, 7, 0, 0)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin, category = _create_test_context(session, now_unaware)

        # INACTIVE product with sales in period
        p_inactive = Product(
            sku=f"{TEST_PREFIX}INACTIVE_SALE_{uuid4().hex[:4]}",
            name="Inactive Product With Sales",
            category_id=category.id,
            status=CatalogStatus.INACTIVE.value,
            sale_price_vnd=50_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(p_inactive)
        session.flush()

        # Product without Inventory record
        o = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=500_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o)
        session.flush()
        session.add(
            OrderItem(
                order_id=o.id,
                product_id=p_inactive.id,
                sku_snapshot=p_inactive.sku,
                product_name_snapshot=p_inactive.name,
                quantity=100,  # massive quantity to guarantee rank 1
                unit_price_vnd=50_000,
                line_total_vnd=500_000,
            )
        )
        session.flush()
        inactive_id = p_inactive.id

    service = DashboardService()
    with Session(migrated_integration_engine) as session:
        data = service.read(session, period=period)

    top_ids = [p.product_id for p in data.top_products]
    assert inactive_id in top_ids
    item = next(p for p in data.top_products if p.product_id == inactive_id)
    assert item.sold_units == 100
    assert item.quantity is None
    assert item.first_stocked_at is None


def test_low_stock_count_boundaries(
    migrated_integration_engine: Engine,
) -> None:
    """Validate low stock count boundaries: ACTIVE, INACTIVE, and quantities 0, 5, 6."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)

    repo = InventoryQueryRepository()
    with Session(migrated_integration_engine) as session:
        baseline = repo.count_low_stock(session, threshold=5)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        _, category = _create_test_context(session, now_unaware)

        # 1. ACTIVE, quantity 0 -> counted (+1)
        p_act_0 = Product(
            sku=f"{TEST_PREFIX}ACT_0_{uuid4().hex[:4]}",
            name="Active Qty 0",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # 2. ACTIVE, quantity 5 -> counted (+1)
        p_act_5 = Product(
            sku=f"{TEST_PREFIX}ACT_5_{uuid4().hex[:4]}",
            name="Active Qty 5",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # 3. ACTIVE, quantity 6 -> NOT counted (6 > 5)
        p_act_6 = Product(
            sku=f"{TEST_PREFIX}ACT_6_{uuid4().hex[:4]}",
            name="Active Qty 6",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # 4. INACTIVE, quantity 0 -> NOT counted (INACTIVE)
        p_inact_0 = Product(
            sku=f"{TEST_PREFIX}INACT_0_{uuid4().hex[:4]}",
            name="Inactive Qty 0",
            category_id=category.id,
            status=CatalogStatus.INACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        # 5. INACTIVE, quantity 5 -> NOT counted (INACTIVE)
        p_inact_5 = Product(
            sku=f"{TEST_PREFIX}INACT_5_{uuid4().hex[:4]}",
            name="Inactive Qty 5",
            category_id=category.id,
            status=CatalogStatus.INACTIVE.value,
            sale_price_vnd=10_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )

        session.add_all([p_act_0, p_act_5, p_act_6, p_inact_0, p_inact_5])
        session.flush()

        session.add_all(
            [
                Inventory(
                    product_id=p_act_0.id,
                    quantity=0,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                ),
                Inventory(
                    product_id=p_act_5.id,
                    quantity=5,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                ),
                Inventory(
                    product_id=p_act_6.id,
                    quantity=6,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                ),
                Inventory(
                    product_id=p_inact_0.id,
                    quantity=0,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                ),
                Inventory(
                    product_id=p_inact_5.id,
                    quantity=5,
                    stock_version=0,
                    first_stocked_at=now_unaware,
                    updated_at=now_unaware,
                ),
            ]
        )
        session.flush()

    with Session(migrated_integration_engine) as session:
        new_count = repo.count_low_stock(session, threshold=5)

    # Only p_act_0 and p_act_5 must increment the count
    assert new_count == baseline + 2


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
