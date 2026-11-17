"""MySQL integration tests for T04AAD7 cross-module reconciliation.

Real-service execution on MySQL 8.4 covering:
1. Seed Data + Independent Dataset & Deterministic Pagination (Seed data preserved)
2. Real Checkout Service Mutation & Cross-Module Reconciliation:
   (CheckoutService -> Order & OrderItems committed -> Inventory & StockMovement ->
    OrderReadService -> SalesAnalyticsService -> DashboardService -> ProductService)
3. Real Order Cancellation Reconciliation, Stock Restoration & RBAC Ownership
4. Snapshot Intactness Across Real Catalog Updates and Subsequent Checkouts
5. Cross-Run Isolation & No Cross-Cleanup Regression
"""

from datetime import UTC, datetime
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
from app.modules.inventory.models import Inventory, MovementKind, StockMovement
from app.modules.products.models import CatalogStatus, Product
from app.modules.products.schemas import ProductSortOrder, ProductUpdateRequest
from app.modules.products.service import ProductService
from app.modules.sales.models import Order, OrderItem, OrderStatus
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import (
    CheckoutService,
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


class TestRunContext:
    """Manages unique test run isolation and dependency-aware teardown."""

    __test__ = False

    def __init__(self, engine: Engine, test_name: str) -> None:
        self.engine = engine
        self.run_id = uuid4().hex[:8]
        self.prefix = f"{TEST_PREFIX}{test_name[:6]}_{self.run_id}_"
        self.user_ids: list[int] = []
        self.product_ids: list[int] = []
        self.category_ids: list[int] = []
        self.order_ids: list[int] = []

    def cleanup(self) -> None:
        """Teardown strictly this run's data in correct foreign-key dependency order."""
        with (
            Session(self.engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # Resolve order IDs created by this run's users or products
            order_ids_from_users = (
                list(
                    session.scalars(
                        select(Order.id).where(Order.created_by.in_(self.user_ids))
                    )
                )
                if self.user_ids
                else []
            )
            order_ids_from_products = (
                list(
                    session.scalars(
                        select(OrderItem.order_id).where(
                            OrderItem.product_id.in_(self.product_ids)
                        )
                    )
                )
                if self.product_ids
                else []
            )
            all_order_ids = list(
                set(self.order_ids + order_ids_from_users + order_ids_from_products)
            )

            # 1. Delete stock_movements (references order_items, inventory,
            # orders, users)
            if all_order_ids:
                session.execute(
                    delete(StockMovement).where(
                        StockMovement.order_id.in_(all_order_ids)
                    )
                )
            if self.product_ids:
                session.execute(
                    delete(StockMovement).where(
                        StockMovement.product_id.in_(self.product_ids)
                    )
                )

            # 2. Delete order_items (references orders, products)
            if all_order_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(all_order_ids))
                )
            if self.product_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.product_id.in_(self.product_ids))
                )

            # 3. Delete orders (references users)
            if all_order_ids:
                session.execute(delete(Order).where(Order.id.in_(all_order_ids)))

            # 4. Delete idempotency records (references users)
            if self.user_ids:
                session.execute(
                    delete(IdempotencyRecord).where(
                        IdempotencyRecord.user_id.in_(self.user_ids)
                    )
                )

            # 5. Delete inventory (references products)
            if self.product_ids:
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(self.product_ids))
                )

            # 6. Delete products (references categories)
            if self.product_ids:
                session.execute(delete(Product).where(Product.id.in_(self.product_ids)))

            # 7. Delete test-specific categories ONLY (never seeded categories!)
            if self.category_ids:
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )
            session.execute(
                delete(Category).where(Category.name.like(f"{self.prefix}%"))
            )

            # 8. Delete test users
            if self.user_ids:
                session.execute(delete(User).where(User.id.in_(self.user_ids)))
            session.execute(
                delete(User).where(
                    User.email_normalized.like(f"{self.prefix.lower()}%")
                )
            )


def _create_user(
    session: Session,
    *,
    role: str = "ADMIN",
    status: str = "ACTIVE",
    now_unaware: datetime,
    prefix: str,
) -> User:
    """Helper to create a test user safely with unique test run prefix."""
    suffix = uuid4().hex[:6]
    user = User(
        email_normalized=f"{prefix.lower()}{role.lower()}_{suffix}@example.com",
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
    ctx = TestRunContext(migrated_integration_engine, "seed")
    frozen_time_utc = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # 1. First execution of seed functions
            first_cats_added = seed_categories(session)
            first_supps_added = seed_suppliers(session)
            assert first_cats_added >= 0
            assert first_supps_added >= 0
            session.flush()

            initial_categories = list(
                session.scalars(select(Category).order_by(Category.id))
            )
            initial_suppliers = list(
                session.scalars(select(Supplier).order_by(Supplier.id))
            )
            initial_cat_ids = {c.id for c in initial_categories}
            initial_supp_ids = {s.id for s in initial_suppliers}
            initial_cat_names = [c.name for c in initial_categories]
            initial_supp_names = [s.name for s in initial_suppliers]

            assert "Đồ uống" in initial_cat_names
            assert "Bánh kẹo & Đồ ăn vặt" in initial_cat_names
            assert "Công ty TNHH Phân phối Nước giải khát Việt" in initial_supp_names

            # Re-run seed to prove idempotency: must be a strict no-op
            second_cats_added = seed_categories(session)
            second_supps_added = seed_suppliers(session)
            session.flush()

            assert second_cats_added == 0, (
                "seed_categories must add 0 rows on duplicate execution"
            )
            assert second_supps_added == 0, (
                "seed_suppliers must add 0 rows on duplicate execution"
            )

            after_categories = list(
                session.scalars(select(Category).order_by(Category.id))
            )
            after_suppliers = list(
                session.scalars(select(Supplier).order_by(Supplier.id))
            )
            assert len(after_categories) == len(initial_categories)
            assert len(after_suppliers) == len(initial_suppliers)
            assert {c.id for c in after_categories} == initial_cat_ids
            assert {s.id for s in after_suppliers} == initial_supp_ids

            do_uong_count = sum(1 for c in after_categories if c.name == "Đồ uống")
            assert do_uong_count == 1, "'Đồ uống' category must not duplicate"

            drink_supplier_count = sum(
                1
                for s in after_suppliers
                if s.name == "Công ty TNHH Phân phối Nước giải khát Việt"
            )
            assert drink_supplier_count == 1, "Supplier must not duplicate"

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
                (f"{ctx.prefix}P1", "Nước suối khoáng", drink_id, 10_000, "ACTIVE", 50),
                (f"{ctx.prefix}P2", "Nước ngọt có ga", drink_id, 15_000, "ACTIVE", 40),
                (
                    f"{ctx.prefix}P3",
                    "Trà xanh đóng chai",
                    drink_id,
                    12_000,
                    "ACTIVE",
                    30,
                ),
                (
                    f"{ctx.prefix}P4",
                    "Cà phê lon ngừng bán",
                    drink_id,
                    18_000,
                    "INACTIVE",
                    5,
                ),
                (f"{ctx.prefix}P5", "Bánh quy bơ", snack_id, 25_000, "ACTIVE", 20),
                (f"{ctx.prefix}P6", "Kẹo dẻo trái cây", snack_id, 20_000, "ACTIVE", 15),
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
                ctx.product_ids.append(p.id)

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
            # Products created in drink category must be included
            returned_ids = {item.id for item in drink_res.items}
            created_drink_ids = set(ctx.product_ids[:4])
            assert created_drink_ids.issubset(returned_ids)

            # B. Filter by status ACTIVE
            active_res = product_service.list_products(
                session,
                category_id=drink_id,
                status=CatalogStatus.ACTIVE,
                page=1,
                page_size=10,
            )
            active_ids = {item.id for item in active_res.items}
            assert ctx.product_ids[3] not in active_ids  # INACTIVE product excluded
            assert set(ctx.product_ids[:3]).issubset(active_ids)

            # C. Search by SKU
            search_res = product_service.list_products(
                session, search=f"{ctx.prefix}P1", page=1, page_size=10
            )
            assert search_res.total == 1
            assert search_res.items[0].sku == f"{ctx.prefix}P1"

            # D. Deterministic Pagination across multiple pages
            page_1 = product_service.list_products(
                session,
                search=ctx.prefix,
                sort=ProductSortOrder.CREATED_DESC,
                page=1,
                page_size=2,
            )
            page_2 = product_service.list_products(
                session,
                search=ctx.prefix,
                sort=ProductSortOrder.CREATED_DESC,
                page=2,
                page_size=2,
            )
            page_empty = product_service.list_products(
                session,
                search=ctx.prefix,
                sort=ProductSortOrder.CREATED_DESC,
                page=99,
                page_size=2,
            )

            assert len(page_1.items) == 2
            assert len(page_2.items) == 2
            assert page_empty.items == []
            assert page_empty.total == 6  # Total count preserved

            # Disjoint pages (no item duplicates across pages)
            p1_ids = {item.id for item in page_1.items}
            p2_ids = {item.id for item in page_2.items}
            assert p1_ids.isdisjoint(p2_ids)
    finally:
        ctx.cleanup()


# ==============================================================================
# Test 2: Real Checkout Service Mutation & Cross-Module Reconciliation
# ==============================================================================


def test_cross_module_reconciliation_checkout_orders_sales_dashboard(
    migrated_integration_engine: Engine,
) -> None:
    """Validate real-service checkout reconciliation across all modules."""
    ctx = TestRunContext(migrated_integration_engine, "check")
    frozen_time_utc = datetime(2026, 11, 20, 3, 30, tzinfo=UTC)
    target_date = frozen_time_utc.astimezone(VN_TZ).date()
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            admin = _create_user(
                session, role="ADMIN", now_unaware=now_unaware, prefix=ctx.prefix
            )
            ctx.user_ids.append(admin.id)

            category = Category(
                name=f"{ctx.prefix}Cat_{uuid4().hex[:6]}",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(category)
            session.flush()
            ctx.category_ids.append(category.id)

            prod_a = Product(
                sku=f"{ctx.prefix}PROD_A",
                name="Sản phẩm A",
                category_id=category.id,
                sale_price_vnd=50_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            prod_b = Product(
                sku=f"{ctx.prefix}PROD_B",
                name="Sản phẩm B",
                category_id=category.id,
                sale_price_vnd=100_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add_all([prod_a, prod_b])
            session.flush()
            ctx.product_ids.extend([prod_a.id, prod_b.id])

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

            admin_id = admin.id
            prod_a_id = prod_a.id
            prod_b_id = prod_b.id

        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        sales_service = SalesAnalyticsService()
        with Session(migrated_integration_engine) as session:
            baseline_summary = sales_service.summary(session, period=period)

        # Real Checkout Service executing genuine database transactions
        checkout_service = CheckoutService(
            InventoryService(), clock=lambda: frozen_time_utc
        )

        # Transaction 1: 2 units of A (2 * 50k = 100k)
        with Session(migrated_integration_engine) as session:
            o1 = checkout_service.checkout(
                session,
                actor_id=admin_id,
                idempotency_key=f"{ctx.prefix}idem_1_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_a_id,
                        quantity=2,
                        viewed_unit_price_vnd=50_000,
                    )
                ],
            )
            ctx.order_ids.append(o1.id)
            assert o1.status == "COMPLETED"
            assert o1.total_vnd == 100_000

        # Transaction 2: 1 unit of A (50k) + 1 unit of B (100k) = 150k
        with Session(migrated_integration_engine) as session:
            o2 = checkout_service.checkout(
                session,
                actor_id=admin_id,
                idempotency_key=f"{ctx.prefix}idem_2_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_a_id,
                        quantity=1,
                        viewed_unit_price_vnd=50_000,
                    ),
                    CheckoutLine(
                        product_id=prod_b_id,
                        quantity=1,
                        viewed_unit_price_vnd=100_000,
                    ),
                ],
            )
            ctx.order_ids.append(o2.id)
            assert o2.status == "COMPLETED"
            assert o2.total_vnd == 150_000

        # Transaction 3: 2 units of B (2 * 100k = 200k)
        with Session(migrated_integration_engine) as session:
            o3 = checkout_service.checkout(
                session,
                actor_id=admin_id,
                idempotency_key=f"{ctx.prefix}idem_3_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_b_id,
                        quantity=2,
                        viewed_unit_price_vnd=100_000,
                    )
                ],
            )
            ctx.order_ids.append(o3.id)
            assert o3.status == "COMPLETED"
            assert o3.total_vnd == 200_000

        # Verify real database state and cross-module reconciliation
        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        with Session(migrated_integration_engine) as session:
            # 1. Verify StockMovements created by real checkout
            movements = list(
                session.scalars(
                    select(StockMovement).where(
                        StockMovement.order_id.in_(ctx.order_ids)
                    )
                )
            )
            assert len(movements) == 4  # 1 for o1 + 2 for o2 + 1 for o3
            assert all(m.kind == MovementKind.SALE.value for m in movements)
            assert all(m.actor_id == admin_id for m in movements)

            # 2. Verify Orders Read Service
            order_service = OrderReadService()
            orders_page = order_service.list(
                session,
                actor_id=admin_id,
                actor_role="ADMIN",
                filters=OrderQuery(from_date=target_date, to_date=target_date),
            )
            test_orders = [o for o in orders_page.items if o.id in ctx.order_ids]
            sum_order_revenue = sum(
                o.total_vnd
                for o in test_orders
                if o.status == OrderStatus.COMPLETED.value
            )
            assert sum_order_revenue == 450_000
            assert len(test_orders) == 3

            # 3. Verify Sales Analytics Service (baseline controlled + delta)
            sales_service = SalesAnalyticsService()
            sales_summary = sales_service.summary(session, period=period)
            assert sales_summary.revenue_vnd == baseline_summary.revenue_vnd + 450_000
            assert (
                sales_summary.completed_orders == baseline_summary.completed_orders + 3
            )
            assert sales_summary.cancelled_orders == baseline_summary.cancelled_orders
            assert baseline_summary.completed_orders == 0
            assert sales_summary.revenue_vnd == 450_000
            assert sales_summary.completed_orders == 3
            assert sales_summary.cancelled_orders == 0
            assert sales_summary.aov_vnd == 150_000  # 450,000 / 3

            # 4. Verify Dashboard Service
            dash_service = DashboardService()
            dashboard_data = dash_service.read(session, period=period)
            assert dashboard_data.sales.revenue_vnd == sales_summary.revenue_vnd
            assert (
                dashboard_data.sales.completed_orders == sales_summary.completed_orders
            )
            assert (
                dashboard_data.sales.cancelled_orders == sales_summary.cancelled_orders
            )
            assert dashboard_data.sales.aov_vnd == sales_summary.aov_vnd

            # Top products ranking:
            # Prod B: 3 units, 300,000 VND
            # Prod A: 3 units, 150,000 VND
            # Prod B ranks 1st due to higher revenue!
            top_map = {p.product_id: p for p in dashboard_data.top_products}
            assert prod_b_id in top_map
            assert prod_a_id in top_map
            assert top_map[prod_b_id].sold_units == 3
            assert top_map[prod_b_id].revenue_vnd == 300_000
            assert top_map[prod_a_id].sold_units == 3
            assert top_map[prod_a_id].revenue_vnd == 150_000

            # 5. Verify real inventory deduction & stock version increment
            prod_service = ProductService()
            p_a = prod_service.get_product(session, prod_a_id)
            p_b = prod_service.get_product(session, prod_b_id)
            assert p_a.quantity == 17  # 20 - 3 = 17
            assert p_b.quantity == 27  # 30 - 3 = 27
            assert p_a.stock_version == 3  # Initial 1 + 2 decrements
            assert p_b.stock_version == 3  # Initial 1 + 2 decrements
    finally:
        ctx.cleanup()


# ==============================================================================
# Test 3: Real Order Cancellation Reconciliation & RBAC Ownership
# ==============================================================================


def test_cancellation_reconciliation_and_rbac_ownership(
    migrated_integration_engine: Engine,
) -> None:
    """Validate cancellation exclusion, stock restoration, and RBAC ownership."""
    ctx = TestRunContext(migrated_integration_engine, "cancel")
    frozen_time_utc = datetime(2026, 11, 21, 3, 30, tzinfo=UTC)
    target_date = frozen_time_utc.astimezone(VN_TZ).date()
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            staff_a = _create_user(
                session, role="STAFF", now_unaware=now_unaware, prefix=ctx.prefix
            )
            staff_b = _create_user(
                session, role="STAFF", now_unaware=now_unaware, prefix=ctx.prefix
            )
            ctx.user_ids.extend([staff_a.id, staff_b.id])

            category = Category(
                name=f"{ctx.prefix}Cat_{uuid4().hex[:6]}",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(category)
            session.flush()
            ctx.category_ids.append(category.id)

            prod_c = Product(
                sku=f"{ctx.prefix}PROD_C",
                name="Sản phẩm C",
                category_id=category.id,
                sale_price_vnd=80_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_c)
            session.flush()
            ctx.product_ids.append(prod_c.id)

            inv_c = Inventory(
                product_id=prod_c.id,
                quantity=15,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv_c)
            session.flush()

            staff_a_id = staff_a.id
            staff_b_id = staff_b.id
            prod_c_id = prod_c.id

        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        with Session(migrated_integration_engine) as session:
            baseline_summary = SalesAnalyticsService().summary(session, period=period)

        # Place order via real CheckoutService (deducting inventory from 15 to 13)
        checkout_service = CheckoutService(
            InventoryService(), clock=lambda: frozen_time_utc
        )
        with Session(migrated_integration_engine) as session:
            checkout_res = checkout_service.checkout(
                session,
                actor_id=staff_a_id,
                idempotency_key=f"{ctx.prefix}idem_chk_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_c_id,
                        quantity=2,
                        viewed_unit_price_vnd=80_000,
                    )
                ],
            )
            ctx.order_ids.append(checkout_res.id)
            order_id = checkout_res.id

        # Verify stock decreased to 13 before cancellation
        with Session(migrated_integration_engine) as session:
            p_before = ProductService().get_product(session, prod_c_id)
            assert p_before.quantity == 13

        order_service = OrderService(InventoryService(), clock=lambda: frozen_time_utc)

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
                idempotency_key=f"{ctx.prefix}idem_can_b_{uuid4().hex[:12]}",
            )

        # 2. STAFF_A cancels own order -> Success!
        with Session(migrated_integration_engine) as session:
            result = order_service.cancel(
                session,
                actor_id=staff_a_id,
                actor_role="STAFF",
                order_id=order_id,
                reason="Khách hàng đổi ý muốn hủy đơn hàng này",
                idempotency_key=f"{ctx.prefix}idem_can_a_{uuid4().hex[:12]}",
            )
            assert result.status == OrderStatus.CANCELLED.value

        # 3. Cross-Module Reconciliation after cancellation
        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        with Session(migrated_integration_engine) as session:
            # Sales Analytics: cancelled order excluded, counted in cancelled_orders
            sales_summary = SalesAnalyticsService().summary(session, period=period)
            assert sales_summary.revenue_vnd == baseline_summary.revenue_vnd
            assert sales_summary.completed_orders == baseline_summary.completed_orders
            assert (
                sales_summary.cancelled_orders == baseline_summary.cancelled_orders + 1
            )
            assert sales_summary.aov_vnd == baseline_summary.aov_vnd

            assert baseline_summary.cancelled_orders == 0
            assert baseline_summary.completed_orders == 0
            assert baseline_summary.revenue_vnd == 0
            assert sales_summary.revenue_vnd == 0
            assert sales_summary.completed_orders == 0
            assert sales_summary.cancelled_orders == 1
            assert sales_summary.aov_vnd == 0

            # Dashboard: verified identical to sales analytics
            dashboard_data = DashboardService().read(session, period=period)
            assert dashboard_data.sales.revenue_vnd == sales_summary.revenue_vnd
            assert (
                dashboard_data.sales.completed_orders == sales_summary.completed_orders
            )
            assert (
                dashboard_data.sales.cancelled_orders == sales_summary.cancelled_orders
            )
            assert dashboard_data.sales.aov_vnd == sales_summary.aov_vnd
            # Cancelled product is excluded from top products
            top_ids = [p.product_id for p in dashboard_data.top_products]
            assert prod_c_id not in top_ids

            # Inventory restoration check: Product C stock restored from 13 back to 15!
            prod_res = ProductService().get_product(session, prod_c_id)
            assert prod_res.quantity == 15

            # Stock movements check: 1 SALE and 1 ORDER_CANCEL
            order_movements = list(
                session.scalars(
                    select(StockMovement).where(StockMovement.order_id == order_id)
                )
            )
            assert len(order_movements) == 2
            kinds = {m.kind for m in order_movements}
            assert kinds == {
                MovementKind.SALE.value,
                MovementKind.ORDER_CANCEL.value,
            }
    finally:
        ctx.cleanup()


# ==============================================================================
# Test 4: Snapshot Intactness Across Catalog Updates
# ==============================================================================


def test_snapshot_intactness_across_catalog_updates(
    migrated_integration_engine: Engine,
) -> None:
    """Validate snapshot preservation in orders when catalog item is modified."""
    ctx = TestRunContext(migrated_integration_engine, "snap")
    frozen_time_utc = datetime(2026, 11, 22, 5, 0, tzinfo=UTC)
    target_date = frozen_time_utc.astimezone(VN_TZ).date()
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            admin = _create_user(
                session, role="ADMIN", now_unaware=now_unaware, prefix=ctx.prefix
            )
            ctx.user_ids.append(admin.id)

            category = Category(
                name=f"{ctx.prefix}Cat_{uuid4().hex[:6]}",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(category)
            session.flush()
            ctx.category_ids.append(category.id)

            # Product initial version
            prod = Product(
                sku=f"{ctx.prefix}MILK_TEA",
                name="Trà sữa Ô long",
                category_id=category.id,
                sale_price_vnd=50_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod)
            session.flush()
            ctx.product_ids.append(prod.id)

            inv = Inventory(
                product_id=prod.id,
                quantity=50,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv)
            session.flush()

            admin_id = admin.id
            prod_id = prod.id

        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        with Session(migrated_integration_engine) as session:
            baseline_summary = SalesAnalyticsService().summary(session, period=period)

        checkout_service = CheckoutService(
            InventoryService(), clock=lambda: frozen_time_utc
        )

        # Order 1 placed via real checkout: 2 units at original price 50k = 100k
        with Session(migrated_integration_engine) as session:
            o1_res = checkout_service.checkout(
                session,
                actor_id=admin_id,
                idempotency_key=f"{ctx.prefix}idem_snap_1_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_id,
                        quantity=2,
                        viewed_unit_price_vnd=50_000,
                    )
                ],
            )
            ctx.order_ids.append(o1_res.id)
            o1_id = o1_res.id

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

        # Order 2 placed via real checkout: 1 unit at updated price 75k = 75k
        with Session(migrated_integration_engine) as session:
            o2_res = checkout_service.checkout(
                session,
                actor_id=admin_id,
                idempotency_key=f"{ctx.prefix}idem_snap_2_{uuid4().hex[:12]}",
                items=[
                    CheckoutLine(
                        product_id=prod_id,
                        quantity=1,
                        viewed_unit_price_vnd=75_000,
                    )
                ],
            )
            ctx.order_ids.append(o2_res.id)
            o2_id = o2_res.id

        # Verify Snapshot Invariants across orders and analytics
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
            assert sales_summary.revenue_vnd == baseline_summary.revenue_vnd + 175_000
            assert (
                sales_summary.completed_orders == baseline_summary.completed_orders + 2
            )
            assert baseline_summary.completed_orders == 0
            assert sales_summary.revenue_vnd == 175_000  # 100,000 + 75,000
            assert sales_summary.completed_orders == 2

            # Invariant 4: Dashboard aggregates under single product_id
            # with current name
            dashboard_data = DashboardService().read(session, period=period)
            assert dashboard_data.sales.revenue_vnd == sales_summary.revenue_vnd
            assert (
                dashboard_data.sales.completed_orders == sales_summary.completed_orders
            )
            prod_entries = [
                p for p in dashboard_data.top_products if p.product_id == prod_id
            ]
            assert len(prod_entries) == 1
            entry = prod_entries[0]
            assert entry.sold_units == 3  # 2 + 1
            assert entry.revenue_vnd == 175_000
            assert entry.name == "Trà sữa Ô long Đặc biệt"
    finally:
        ctx.cleanup()


# ==============================================================================
# Test 5: Cross-Run Isolation & No Cross-Cleanup Regression
# ==============================================================================


def test_cross_run_isolation_and_no_cross_cleanup(
    migrated_integration_engine: Engine,
) -> None:
    """Validate that TestRunContext cleanup never deletes another run's or seed data."""
    ctx_a = TestRunContext(migrated_integration_engine, "run_a")
    ctx_b = TestRunContext(migrated_integration_engine, "run_b")
    frozen_time_utc = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # 1. Ensure baseline seed data is present
            seed_categories(session)
            seed_suppliers(session)

            cat_drink = session.scalars(
                select(Category).where(Category.name == "Đồ uống")
            ).first()
            assert cat_drink is not None
            drink_id = cat_drink.id

            # 2. Run A creates User A, Product A, Inventory A
            user_a = _create_user(
                session,
                role="STAFF",
                now_unaware=now_unaware,
                prefix=ctx_a.prefix,
            )
            ctx_a.user_ids.append(user_a.id)
            user_a_id = user_a.id

            prod_a = Product(
                sku=f"{ctx_a.prefix}PROD_A",
                name="Sản phẩm Run A",
                category_id=drink_id,
                sale_price_vnd=20_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_a)
            session.flush()
            ctx_a.product_ids.append(prod_a.id)
            prod_a_id = prod_a.id

            inv_a = Inventory(
                product_id=prod_a_id,
                quantity=10,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv_a)

            # 3. Run B creates User B, Product B, Inventory B
            user_b = _create_user(
                session,
                role="STAFF",
                now_unaware=now_unaware,
                prefix=ctx_b.prefix,
            )
            ctx_b.user_ids.append(user_b.id)
            user_b_id = user_b.id

            prod_b = Product(
                sku=f"{ctx_b.prefix}PROD_B",
                name="Sản phẩm Run B",
                category_id=drink_id,
                sale_price_vnd=30_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_b)
            session.flush()
            ctx_b.product_ids.append(prod_b.id)
            prod_b_id = prod_b.id

            inv_b = Inventory(
                product_id=prod_b_id,
                quantity=20,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv_b)

        # 4. Execute cleanup for Run A ONLY
        ctx_a.cleanup()

        with Session(migrated_integration_engine) as session:
            # Run A data must be deleted
            assert session.get(User, user_a_id) is None
            assert session.get(Product, prod_a_id) is None
            assert session.get(Inventory, prod_a_id) is None

            # Run B data MUST STILL EXIST (Proof of no cross-run cleanup!)
            assert session.get(User, user_b_id) is not None
            assert session.get(Product, prod_b_id) is not None
            assert session.get(Inventory, prod_b_id) is not None

            # Seed data must still exist
            cat_still_there = session.scalars(
                select(Category).where(Category.name == "Đồ uống")
            ).first()
            assert cat_still_there is not None

        # 5. Execute cleanup for Run B
        ctx_b.cleanup()

        with Session(migrated_integration_engine) as session:
            # Run B data now deleted
            assert session.get(User, user_b_id) is None
            assert session.get(Product, prod_b_id) is None
            assert session.get(Inventory, prod_b_id) is None

            # Seed data must still exist
            cat_still_there = session.scalars(
                select(Category).where(Category.name == "Đồ uống")
            ).first()
            assert cat_still_there is not None
    finally:
        ctx_a.cleanup()
        ctx_b.cleanup()
