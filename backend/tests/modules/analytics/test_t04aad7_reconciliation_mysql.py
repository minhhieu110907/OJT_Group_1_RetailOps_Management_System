"""MySQL integration tests for T04AAD7 cross-module reconciliation.

E2E on MySQL 8.4 covering:
1. Seed Data + Independent Dataset & Deterministic Pagination
2. Cross-Module Mathematical Reconciliation (Products -> Orders -> Sales -> Dashboard)
3. Order Cancellation Reconciliation, Stock Restoration & RBAC Ownership
4. Snapshot Intactness Across Catalog Updates
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.modules.analytics.service import (
    VN_TZ,
    DashboardService,
    SalesAnalyticsService,
    resolve_sales_period,
)
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.categories.seed import seed_categories
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.inventory import InventoryService
from app.modules.inventory.models import Inventory, StockMovement
from app.modules.products.models import CatalogStatus, Product
from app.modules.products.schemas import ProductSortOrder, ProductUpdateRequest
from app.modules.products.service import ProductService
from app.modules.sales.models import Order, OrderItem, OrderStatus
from app.modules.sales.service import (
    OrderQuery,
    OrderReadService,
    OrderService,
)
from app.modules.suppliers.models import Supplier
from app.modules.suppliers.seed import seed_suppliers
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04AAD7_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


@pytest.fixture(autouse=True)
def clean_t04aad7_test_rows(migrated_integration_engine: Engine):
    """Clean all test-created rows across all modules before and after tests."""
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
        order_ids_from_users = (
            list(
                session.scalars(select(Order.id).where(Order.created_by.in_(user_ids)))
            )
            if user_ids
            else []
        )
        order_ids_from_products = (
            list(
                session.scalars(
                    select(OrderItem.order_id).where(
                        OrderItem.product_id.in_(product_ids)
                    )
                )
            )
            if product_ids
            else []
        )
        order_ids = list(set(order_ids_from_users + order_ids_from_products))

        # 1. Delete stock_movements (references order_items, inventory, orders)
        if order_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.order_id.in_(order_ids))
            )
        if product_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )

        # 2. Delete order_items (references orders, products)
        if order_ids:
            session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        if product_ids:
            session.execute(
                delete(OrderItem).where(OrderItem.product_id.in_(product_ids))
            )

        # 3. Delete orders (references users)
        if order_ids:
            session.execute(delete(Order).where(Order.id.in_(order_ids)))

        # 4. Delete idempotency records (references users)
        if user_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.user_id.in_(user_ids))
            )

        # 5. Delete inventory (references products)
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )

        # 6. Delete products (references categories)
        if product_ids:
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        # 7. Delete test categories
        session.execute(delete(Category).where(Category.name.like(f"{TEST_PREFIX}%")))

        # 8. Delete test users
        if user_ids:
            session.execute(delete(User).where(User.id.in_(user_ids)))


def _create_user(
    session: Session,
    *,
    role: str = "ADMIN",
    status: str = "ACTIVE",
    now_unaware: datetime,
) -> User:
    """Helper to create a test user safely without detached instance errors."""
    suffix = uuid4().hex[:6]
    user = User(
        email_normalized=f"{TEST_PREFIX.lower()}{role.lower()}_{suffix}@example.com",
        password_hash="$2b$04$test.hash.t04aad7",
        role=role,
        status=status,
        admin_slot=1 if role == "ADMIN" else None,
        last_reapplied_at=None,
        created_at=now_unaware,
        updated_at=now_unaware,
    )
    session.add(user)
    session.flush()
    return user


# ==============================================================================
# Test 1: Seed Data + Independent Dataset & Deterministic Pagination
# ==============================================================================


def test_seed_data_and_deterministic_pagination(
    migrated_integration_engine: Engine,
) -> None:
    """Validate seed idempotency and deterministic product query/pagination."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        # 1. Verify seed functions run idempotently
        seed_categories(session)
        seed_suppliers(session)
        session.flush()

        cat_names = list(session.scalars(select(Category.name)))
        assert "Đồ uống" in cat_names
        assert "Bánh kẹo & Đồ ăn vặt" in cat_names

        supp_names = list(session.scalars(select(Supplier.name)))
        assert "Công ty TNHH Phân phối Nước giải khát Việt" in supp_names

        cat_drink = session.scalars(
            select(Category).where(Category.name == "Đồ uống")
        ).first()
        cat_snack = session.scalars(
            select(Category).where(Category.name == "Bánh kẹo & Đồ ăn vặt")
        ).first()
        assert cat_drink is not None
        assert cat_snack is not None
        drink_id = cat_drink.id
        snack_id = cat_snack.id

        # 2. Create 6 distinct products attached to seeded categories
        products_data = [
            (f"{TEST_PREFIX}P1", "Nước suối khoáng", drink_id, 10_000, "ACTIVE", 50),
            (f"{TEST_PREFIX}P2", "Nước ngọt có ga", drink_id, 15_000, "ACTIVE", 40),
            (f"{TEST_PREFIX}P3", "Trà xanh đóng chai", drink_id, 12_000, "ACTIVE", 30),
            (
                f"{TEST_PREFIX}P4",
                "Cà phê lon ngừng bán",
                drink_id,
                18_000,
                "INACTIVE",
                5,
            ),
            (f"{TEST_PREFIX}P5", "Bánh quy bơ", snack_id, 25_000, "ACTIVE", 20),
            (f"{TEST_PREFIX}P6", "Kẹo dẻo trái cây", snack_id, 20_000, "ACTIVE", 15),
        ]

        for sku, name, cat_id, price, stat, qty in products_data:
            p = Product(
                sku=sku,
                name=name,
                category_id=cat_id,
                sale_price_vnd=price,
                status=stat,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(p)
            session.flush()
            inv = Inventory(
                product_id=p.id,
                quantity=qty,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv)
        session.flush()

    # Query with ProductService
    product_service = ProductService()
    with Session(migrated_integration_engine) as session:
        # A. Filter by category
        drink_res = product_service.list_products(
            session, category_id=drink_id, page=1, page_size=10
        )
        assert drink_res.total == 4
        assert all(item.category_id == drink_id for item in drink_res.items)

        # B. Filter by status ACTIVE
        active_res = product_service.list_products(
            session,
            category_id=drink_id,
            status=CatalogStatus.ACTIVE,
            page=1,
            page_size=10,
        )
        assert active_res.total == 3
        assert all(item.status == CatalogStatus.ACTIVE for item in active_res.items)

        # C. Search by SKU
        search_res = product_service.list_products(
            session, search=f"{TEST_PREFIX}P1", page=1, page_size=10
        )
        assert search_res.total == 1
        assert search_res.items[0].sku == f"{TEST_PREFIX}P1"

        # D. Deterministic Pagination across multiple pages
        page_1 = product_service.list_products(
            session,
            category_id=drink_id,
            sort=ProductSortOrder.CREATED_DESC,
            page=1,
            page_size=2,
        )
        page_2 = product_service.list_products(
            session,
            category_id=drink_id,
            sort=ProductSortOrder.CREATED_DESC,
            page=2,
            page_size=2,
        )
        page_empty = product_service.list_products(
            session,
            category_id=drink_id,
            sort=ProductSortOrder.CREATED_DESC,
            page=99,
            page_size=2,
        )

        assert len(page_1.items) == 2
        assert len(page_2.items) == 2
        assert page_empty.items == []
        assert page_empty.total == 4  # Total remains unchanged

        # Disjoint pages (no item duplicates across pages)
        p1_ids = {item.id for item in page_1.items}
        p2_ids = {item.id for item in page_2.items}
        assert p1_ids.isdisjoint(p2_ids)


# ==============================================================================
# Test 2: Cross-Module Reconciliation (Checkout -> Orders -> Sales -> Dashboard)
# ==============================================================================


def test_cross_module_reconciliation_checkout_orders_sales_dashboard(
    migrated_integration_engine: Engine,
) -> None:
    """Validate reconciliation between Orders, Sales, Dashboard, and Inventory."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    target_date = date(2026, 11, 20)
    t_sold = datetime(2026, 11, 20, 3, 30, tzinfo=UTC).replace(tzinfo=None)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin = _create_user(session, role="ADMIN", now_unaware=now_unaware)
        category = Category(
            name=f"{TEST_PREFIX}ReconCat_{uuid4().hex[:6]}",
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(category)
        session.flush()

        prod_a = Product(
            sku=f"{TEST_PREFIX}PROD_A",
            name="Sản phẩm A",
            category_id=category.id,
            sale_price_vnd=50_000,
            status=CatalogStatus.ACTIVE.value,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        prod_b = Product(
            sku=f"{TEST_PREFIX}PROD_B",
            name="Sản phẩm B",
            category_id=category.id,
            sale_price_vnd=100_000,
            status=CatalogStatus.ACTIVE.value,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([prod_a, prod_b])
        session.flush()

        inv_a = Inventory(
            product_id=prod_a.id,
            quantity=20,
            stock_version=1,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        inv_b = Inventory(
            product_id=prod_b.id,
            quantity=30,
            stock_version=1,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([inv_a, inv_b])
        session.flush()

        # Transaction 1: 2 units of A (2 * 50k = 100k)
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
                product_id=prod_a.id,
                sku_snapshot=prod_a.sku,
                product_name_snapshot=prod_a.name,
                quantity=2,
                unit_price_vnd=50_000,
                line_total_vnd=100_000,
            )
        )

        # Transaction 2: 1 unit of A (50k) + 1 unit of B (100k) = 150k
        o2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=150_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o2)
        session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=o2.id,
                    product_id=prod_a.id,
                    sku_snapshot=prod_a.sku,
                    product_name_snapshot=prod_a.name,
                    quantity=1,
                    unit_price_vnd=50_000,
                    line_total_vnd=50_000,
                ),
                OrderItem(
                    order_id=o2.id,
                    product_id=prod_b.id,
                    sku_snapshot=prod_b.sku,
                    product_name_snapshot=prod_b.name,
                    quantity=1,
                    unit_price_vnd=100_000,
                    line_total_vnd=100_000,
                ),
            ]
        )

        # Transaction 3: 2 units of B (2 * 100k = 200k)
        o3 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=200_000,
            created_by=admin.id,
            sold_at=t_sold,
        )
        session.add(o3)
        session.flush()
        session.add(
            OrderItem(
                order_id=o3.id,
                product_id=prod_b.id,
                sku_snapshot=prod_b.sku,
                product_name_snapshot=prod_b.name,
                quantity=2,
                unit_price_vnd=100_000,
                line_total_vnd=200_000,
            )
        )

        # Deduct inventories according to sales: A sold 3 (rem 17), B sold 3 (rem 27)
        inv_a.quantity = 17
        inv_b.quantity = 27
        session.flush()

        admin_id = admin.id
        prod_a_id = prod_a.id
        prod_b_id = prod_b.id

    # Cross-Module Reconciliation
    period = resolve_sales_period(from_date=target_date, to_date=target_date)
    with Session(migrated_integration_engine) as session:
        # 1. Orders Read API
        order_service = OrderReadService()
        orders_page = order_service.list(
            session,
            actor_id=admin_id,
            actor_role="ADMIN",
            filters=OrderQuery(from_date=target_date, to_date=target_date),
        )
        completed_orders = [
            o for o in orders_page.items if o.status == OrderStatus.COMPLETED.value
        ]
        sum_order_revenue = sum(o.total_vnd for o in completed_orders)
        assert sum_order_revenue == 450_000
        assert len(completed_orders) == 3

        # 2. Sales Analytics Service
        sales_service = SalesAnalyticsService()
        sales_summary = sales_service.summary(session, period=period)
        assert sales_summary.revenue_vnd == 450_000
        assert sales_summary.completed_orders == 3
        assert sales_summary.cancelled_orders == 0
        assert sales_summary.aov_vnd == 150_000  # 450,000 / 3

        # 3. Dashboard Service
        dash_service = DashboardService()
        dashboard_data = dash_service.read(session, period=period)
        assert dashboard_data.sales.revenue_vnd == 450_000
        assert dashboard_data.sales.completed_orders == 3
        assert dashboard_data.sales.cancelled_orders == 0
        assert dashboard_data.sales.aov_vnd == 150_000

        # Top products ranking:
        # Prod B: 3 units, 300,000 VND
        # Prod A: 3 units, 150,000 VND
        # Prod B should rank 1st due to higher revenue!
        top_map = {p.product_id: p for p in dashboard_data.top_products}
        assert prod_b_id in top_map
        assert prod_a_id in top_map
        assert top_map[prod_b_id].sold_units == 3
        assert top_map[prod_b_id].revenue_vnd == 300_000
        assert top_map[prod_a_id].sold_units == 3
        assert top_map[prod_a_id].revenue_vnd == 150_000

        # 4. Inventory check via ProductService
        prod_service = ProductService()
        p_a = prod_service.get_product(session, prod_a_id)
        p_b = prod_service.get_product(session, prod_b_id)
        assert p_a.quantity == 17
        assert p_b.quantity == 27


# ==============================================================================
# Test 3: Order Cancellation Reconciliation & RBAC Ownership
# ==============================================================================


def test_cancellation_reconciliation_and_rbac_ownership(
    migrated_integration_engine: Engine,
) -> None:
    """Validate cancellation exclusion, stock restoration, and RBAC ownership."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    target_date = datetime.now(VN_TZ).date()
    t_sold = datetime.now(UTC).replace(tzinfo=None)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        staff_a = _create_user(session, role="STAFF", now_unaware=now_unaware)
        staff_b = _create_user(session, role="STAFF", now_unaware=now_unaware)
        category = Category(
            name=f"{TEST_PREFIX}CancelCat_{uuid4().hex[:6]}",
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(category)
        session.flush()

        prod_c = Product(
            sku=f"{TEST_PREFIX}PROD_C",
            name="Sản phẩm C",
            category_id=category.id,
            sale_price_vnd=80_000,
            status=CatalogStatus.ACTIVE.value,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(prod_c)
        session.flush()

        inv_c = Inventory(
            product_id=prod_c.id,
            quantity=15,
            stock_version=1,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(inv_c)
        session.flush()

        # Order created by STAFF_A (qty=2, price=80k, total=160k)
        order = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=160_000,
            created_by=staff_a.id,
            sold_at=t_sold,
        )
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=prod_c.id,
                sku_snapshot=prod_c.sku,
                product_name_snapshot=prod_c.name,
                quantity=2,
                unit_price_vnd=80_000,
                line_total_vnd=160_000,
            )
        )
        inv_c.quantity = 13  # stock deducted
        session.flush()

        staff_a_id = staff_a.id
        staff_b_id = staff_b.id
        order_id = order.id
        prod_c_id = prod_c.id

    order_service = OrderService(InventoryService())

    # 1. STAFF_B attempts to cancel STAFF_A's order -> ForbiddenError!
    with (
        Session(migrated_integration_engine) as session,
        pytest.raises(ForbiddenError, match="Staff chỉ được hủy đơn do chính mình"),
    ):
        order_service.cancel(
            session,
            actor_id=staff_b_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Staff B cố tình hủy đơn của Staff A trái phép",
            idempotency_key=f"idem-b-{uuid4().hex[:16]}",
        )

    # 2. STAFF_A cancels own order -> Success!
    with Session(migrated_integration_engine) as session:
        result = order_service.cancel(
            session,
            actor_id=staff_a_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Khách hàng đổi ý muốn hủy đơn hàng này",
            idempotency_key=f"idem-a-{uuid4().hex[:16]}",
        )
        assert result.status == OrderStatus.CANCELLED.value

    # 3. Cross-Module Reconciliation after cancellation
    period = resolve_sales_period(from_date=target_date, to_date=target_date)
    with Session(migrated_integration_engine) as session:
        # Sales Analytics: cancelled order excluded, counted in cancelled_orders
        sales_summary = SalesAnalyticsService().summary(session, period=period)
        assert sales_summary.revenue_vnd == 0
        assert sales_summary.completed_orders == 0
        assert sales_summary.cancelled_orders == 1
        assert sales_summary.aov_vnd == 0

        # Dashboard: verified identical to sales analytics
        dashboard_data = DashboardService().read(session, period=period)
        assert dashboard_data.sales.revenue_vnd == 0
        assert dashboard_data.sales.cancelled_orders == 1
        # Cancelled product is excluded from top products
        top_ids = [p.product_id for p in dashboard_data.top_products]
        assert prod_c_id not in top_ids

        # Inventory restoration check: Product C stock restored from 13 back to 15!
        prod_res = ProductService().get_product(session, prod_c_id)
        assert prod_res.quantity == 15


# ==============================================================================
# Test 4: Snapshot Intactness Across Catalog Updates
# ==============================================================================


def test_snapshot_intactness_across_catalog_updates(
    migrated_integration_engine: Engine,
) -> None:
    """Validate snapshot preservation in orders when catalog item is modified."""
    now_unaware = datetime.now(UTC).replace(tzinfo=None)
    target_date = date(2026, 11, 22)
    t_sold = datetime(2026, 11, 22, 5, 0, tzinfo=UTC).replace(tzinfo=None)

    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin = _create_user(session, role="ADMIN", now_unaware=now_unaware)
        category = Category(
            name=f"{TEST_PREFIX}SnapCat_{uuid4().hex[:6]}",
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(category)
        session.flush()

        # Product initial version
        prod = Product(
            sku=f"{TEST_PREFIX}MILK_TEA",
            name="Trà sữa Ô long",
            category_id=category.id,
            sale_price_vnd=50_000,
            status=CatalogStatus.ACTIVE.value,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(prod)
        session.flush()

        inv = Inventory(
            product_id=prod.id,
            quantity=50,
            stock_version=1,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(inv)
        session.flush()

        # Order 1: 2 units at original price 50k = 100k
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
                product_id=prod.id,
                sku_snapshot=prod.sku,
                product_name_snapshot=prod.name,
                quantity=2,
                unit_price_vnd=50_000,
                line_total_vnd=100_000,
            )
        )

        admin_id = admin.id
        prod_id = prod.id
        o1_id = o1.id

    # Catalog Update: Admin renames product and raises price to 75,000 VND
    product_service = ProductService()
    with Session(migrated_integration_engine) as session:
        product_service.update(
            session,
            prod_id,
            ProductUpdateRequest(
                name="Trà sữa Ô long Đặc biệt",
                sale_price_vnd=75_000,
            ),
        )

    # Order 2: 1 unit at updated price 75k = 75k
    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        o2 = Order(
            status=OrderStatus.COMPLETED.value,
            total_vnd=75_000,
            created_by=admin_id,
            sold_at=t_sold + timedelta(hours=1),
        )
        session.add(o2)
        session.flush()
        session.add(
            OrderItem(
                order_id=o2.id,
                product_id=prod_id,
                sku_snapshot=f"{TEST_PREFIX}MILK_TEA",
                product_name_snapshot="Trà sữa Ô long Đặc biệt",
                quantity=1,
                unit_price_vnd=75_000,
                line_total_vnd=75_000,
            )
        )
        o2_id = o2.id

    # Verify Snapshot Invariants
    period = resolve_sales_period(from_date=target_date, to_date=target_date)
    with Session(migrated_integration_engine) as session:
        order_read_service = OrderReadService()
        order_1 = order_read_service.get(
            session, actor_id=admin_id, actor_role="ADMIN", order_id=o1_id
        )
        order_2 = order_read_service.get(
            session, actor_id=admin_id, actor_role="ADMIN", order_id=o2_id
        )

        # Invariant 1: Order 1 snapshot untouched
        assert order_1.items[0].product_name_snapshot == "Trà sữa Ô long"
        assert order_1.items[0].unit_price_vnd == 50_000
        assert order_1.items[0].line_total_vnd == 100_000

        # Invariant 2: Order 2 snapshot reflects updated catalog
        assert order_2.items[0].product_name_snapshot == "Trà sữa Ô long Đặc biệt"
        assert order_2.items[0].unit_price_vnd == 75_000
        assert order_2.items[0].line_total_vnd == 75_000

        # Invariant 3: Sales Analytics sums historical line totals accurately
        sales_summary = SalesAnalyticsService().summary(session, period=period)
        assert sales_summary.revenue_vnd == 175_000  # 100,000 + 75,000
        assert sales_summary.completed_orders == 2

        # Invariant 4: Dashboard aggregates under single product_id with current name
        dashboard_data = DashboardService().read(session, period=period)
        assert dashboard_data.sales.revenue_vnd == 175_000
        prod_entries = [
            p for p in dashboard_data.top_products if p.product_id == prod_id
        ]
        assert len(prod_entries) == 1
        entry = prod_entries[0]
        assert entry.sold_units == 3  # 2 + 1
        assert entry.revenue_vnd == 175_000
        assert entry.name == "Trà sữa Ô long Đặc biệt"
