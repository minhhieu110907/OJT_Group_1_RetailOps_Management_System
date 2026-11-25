"""MySQL integration tests for T04A947 Product Analytics (top, slow, low-stock)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.analytics.service import Period, ProductAnalyticsService
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.models import (
    Inventory,
    InventoryAdjustment,
    StockMovement,
)
from app.modules.inventory.schemas import DEFAULT_LOW_STOCK_THRESHOLD
from app.modules.inventory.service import InventoryQueryService
from app.modules.products.models import CatalogStatus, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class ProductAnalyticsRunContext:
    """Run-scoped ownership tracker for safe, isolated MySQL test cleanup."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.run_id = uuid4().hex[:8]
        self.user_ids: list[int] = []
        self.category_ids: list[int] = []
        self.product_ids: list[int] = []
        self.order_ids: list[int] = []

    def seed_user_and_category(self, session: Session) -> tuple[User, Category]:
        now = datetime(2026, 11, 16, 0, 0, 0)
        tag = f"{self.run_id}_{uuid4().hex[:6]}"
        user = User(
            email_normalized=f"t04a947_{tag}@example.com",
            password_hash="x",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        cat = Category(
            name=f"T04A947_Cat_{tag}",
            status=CatalogStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        session.add_all([user, cat])
        session.flush()
        self.user_ids.append(user.id)
        self.category_ids.append(cat.id)
        return user, cat

    def add_product(
        self,
        session: Session,
        *,
        category_id: int,
        sku_suffix: str,
        name: str,
        price_vnd: int,
        quantity: int,
        first_stocked_at: datetime | None,
        status: CatalogStatus = CatalogStatus.ACTIVE,
    ) -> Product:
        now = datetime(2026, 11, 16, 0, 0, 0)
        prod = Product(
            category_id=category_id,
            sku=f"T04A947_{self.run_id}_{sku_suffix}_{uuid4().hex[:4]}",
            name=name,
            status=status.value,
            sale_price_vnd=price_vnd,
            created_at=now,
            updated_at=now,
        )
        session.add(prod)
        session.flush()
        self.product_ids.append(prod.id)
        inv = Inventory(
            product_id=prod.id,
            quantity=quantity,
            stock_version=1 if first_stocked_at is not None else 0,
            first_stocked_at=first_stocked_at,
            updated_at=now,
        )
        session.add(inv)
        session.flush()
        return prod

    def add_order(
        self,
        session: Session,
        *,
        actor_id: int,
        product: Product,
        quantity: int,
        sold_at: datetime,
        status: OrderStatus = OrderStatus.COMPLETED,
    ) -> Order:
        line_total = quantity * product.sale_price_vnd
        order = Order(
            status=status.value,
            total_vnd=line_total,
            created_by=actor_id,
            sold_at=sold_at,
            cancelled_by=actor_id if status == OrderStatus.CANCELLED else None,
            cancelled_at=(
                sold_at + timedelta(minutes=5)
                if status == OrderStatus.CANCELLED
                else None
            ),
            cancel_reason=(
                "Customer cancelled" if status == OrderStatus.CANCELLED else None
            ),
        )
        session.add(order)
        session.flush()
        self.order_ids.append(order.id)
        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            sku_snapshot=product.sku,
            product_name_snapshot=product.name,
            quantity=quantity,
            unit_price_vnd=product.sale_price_vnd,
            line_total_vnd=line_total,
        )
        session.add(item)
        session.flush()
        return order

    def cleanup(self) -> None:
        """Delete strictly this run's tracked rows with fail-closed reference checks."""
        if self.order_ids:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(self.order_ids))
                )
                session.execute(delete(Order).where(Order.id.in_(self.order_ids)))
            self.order_ids.clear()

        if not (self.product_ids or self.category_ids or self.user_ids):
            return

        with Session(self.engine) as session, session.begin():
            if self.product_ids:
                ext_item = session.scalar(
                    select(OrderItem.order_id)
                    .where(OrderItem.product_id.in_(self.product_ids))
                    .limit(1)
                )
                if ext_item is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external OrderItem (order_id={ext_item})."
                    )
                ext_move = session.scalar(
                    select(StockMovement.id)
                    .where(StockMovement.product_id.in_(self.product_ids))
                    .limit(1)
                )
                if ext_move is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external StockMovement (id={ext_move})."
                    )
                ext_adj = session.scalar(
                    select(InventoryAdjustment.id)
                    .where(InventoryAdjustment.product_id.in_(self.product_ids))
                    .limit(1)
                )
                if ext_adj is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external InventoryAdjustment (id={ext_adj})."
                    )
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(self.product_ids))
                )
                session.execute(delete(Product).where(Product.id.in_(self.product_ids)))
                self.product_ids.clear()

            if self.category_ids:
                ext_prod = session.scalar(
                    select(Product.id)
                    .where(Product.category_id.in_(self.category_ids))
                    .limit(1)
                )
                if ext_prod is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked category(ies) still referenced "
                        f"by external Product (id={ext_prod})."
                    )
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )
                self.category_ids.clear()

            if self.user_ids:
                ext_order = session.scalar(
                    select(Order.id)
                    .where(
                        (Order.created_by.in_(self.user_ids))
                        | (Order.cancelled_by.in_(self.user_ids))
                    )
                    .limit(1)
                )
                if ext_order is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked user(s) still referenced "
                        f"by external Order (id={ext_order})."
                    )
                session.execute(delete(User).where(User.id.in_(self.user_ids)))
                self.user_ids.clear()


def test_top_products_ranking_and_excludes_cancelled(
    migrated_integration_engine: Engine,
) -> None:
    """Top products ranks by COMPLETED sold_units DESC, revenue DESC, product_id ASC."""
    ctx = ProductAnalyticsRunContext(migrated_integration_engine)
    as_of = datetime(2026, 11, 16, 10, 0, 0, tzinfo=UTC)
    period = Period(
        start_utc=datetime(2026, 11, 9, 17, 0, 0, tzinfo=UTC),
        end_utc_exclusive=datetime(2026, 11, 16, 17, 0, 0, tzinfo=UTC),
    )

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            user, cat = ctx.seed_user_and_category(session)
            p_best = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="TOP_A",
                name="Top A",
                price_vnd=10000,
                quantity=50,
                first_stocked_at=datetime(2026, 10, 1, 0, 0, 0),
            )
            p_tie_hi = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="TOP_B",
                name="Top B Tie High Rev",
                price_vnd=20000,
                quantity=50,
                first_stocked_at=datetime(2026, 10, 1, 0, 0, 0),
            )
            p_tie_lo = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="TOP_C",
                name="Top C Tie Low Rev",
                price_vnd=5000,
                quantity=50,
                first_stocked_at=datetime(2026, 10, 1, 0, 0, 0),
            )
            p_cancelled_only = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="TOP_CAN",
                name="Cancelled Only",
                price_vnd=30000,
                quantity=50,
                first_stocked_at=datetime(2026, 10, 1, 0, 0, 0),
            )

            sold_time = as_of.replace(tzinfo=None) - timedelta(days=1)
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_best,
                quantity=5,
                sold_at=sold_time,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_tie_hi,
                quantity=3,
                sold_at=sold_time,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_tie_lo,
                quantity=3,
                sold_at=sold_time,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_tie_lo,
                quantity=10,
                sold_at=sold_time,
                status=OrderStatus.CANCELLED,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_cancelled_only,
                quantity=8,
                sold_at=sold_time,
                status=OrderStatus.CANCELLED,
            )

            service = ProductAnalyticsService()
            page1 = service.top(session, period=period, page=1, page_size=2)
            assert page1.total == 3
            assert [i.product_id for i in page1.items] == [p_best.id, p_tie_hi.id]
            assert page1.items[0].sold_units == 5
            assert page1.items[0].revenue_vnd == 50000

            page2 = service.top(session, period=period, page=2, page_size=2)
            assert [i.product_id for i in page2.items] == [p_tie_lo.id]
            assert page2.items[0].sold_units == 3
            assert page2.items[0].revenue_vnd == 15000
    finally:
        ctx.cleanup()


def test_slow_moving_rules_and_boundaries_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify slow-moving rules: no-orders, cancelled, 7d/30d, <=2 vs 3, stock=0."""
    ctx = ProductAnalyticsRunContext(migrated_integration_engine)
    as_of = datetime(2026, 11, 16, 12, 0, 0, tzinfo=UTC)
    as_of_naive = as_of.replace(tzinfo=None)

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            user, cat = ctx.seed_user_and_category(session)

            p_zero_orders = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="SLOW_0",
                name="Slow Zero Orders",
                price_vnd=10000,
                quantity=10,
                first_stocked_at=as_of_naive - timedelta(days=10),
            )
            p_two_plus_cancelled = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="SLOW_2C",
                name="Slow 2 Completed + Cancelled",
                price_vnd=10000,
                quantity=8,
                first_stocked_at=as_of_naive - timedelta(days=15),
            )
            p_30d_stocked = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="SLOW_30D",
                name="Slow 30d Stocked",
                price_vnd=10000,
                quantity=4,
                first_stocked_at=as_of_naive - timedelta(days=30),
            )
            p_exact_7d = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="NEW_7D",
                name="New Exact 7d",
                price_vnd=10000,
                quantity=10,
                first_stocked_at=as_of_naive - timedelta(days=7),
            )
            p_new_3d = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="NEW_3D",
                name="New 3d",
                price_vnd=10000,
                quantity=10,
                first_stocked_at=as_of_naive - timedelta(days=3),
            )
            p_sold_3 = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="FAST_3",
                name="Sold 3 Units",
                price_vnd=10000,
                quantity=10,
                first_stocked_at=as_of_naive - timedelta(days=20),
            )
            p_zero_stock = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="OUT_0",
                name="Out of Stock",
                price_vnd=10000,
                quantity=0,
                first_stocked_at=as_of_naive - timedelta(days=20),
            )
            p_inactive = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="INACT",
                name="Inactive Product",
                price_vnd=10000,
                quantity=10,
                first_stocked_at=as_of_naive - timedelta(days=20),
                status=CatalogStatus.INACTIVE,
            )

            recent = as_of_naive - timedelta(days=5)
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_two_plus_cancelled,
                quantity=2,
                sold_at=recent,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_two_plus_cancelled,
                quantity=5,
                sold_at=recent,
                status=OrderStatus.CANCELLED,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_30d_stocked,
                quantity=1,
                sold_at=recent,
            )
            ctx.add_order(
                session,
                actor_id=user.id,
                product=p_sold_3,
                quantity=3,
                sold_at=recent,
            )

            service = ProductAnalyticsService()
            result = service.slow(session, as_of_utc=as_of, page=1, page_size=20)
            returned_ids = {item.product_id for item in result.items}

            assert p_zero_orders.id in returned_ids
            assert p_two_plus_cancelled.id in returned_ids
            assert p_30d_stocked.id in returned_ids

            assert p_exact_7d.id not in returned_ids
            assert p_new_3d.id not in returned_ids
            assert p_sold_3.id not in returned_ids
            assert p_zero_stock.id not in returned_ids
            assert p_inactive.id not in returned_ids

            by_id = {item.product_id: item for item in result.items}
            assert by_id[p_zero_orders.id].sold_units == 0
            assert by_id[p_two_plus_cancelled.id].sold_units == 2
    finally:
        ctx.cleanup()


def test_low_stock_matches_inventory_threshold(
    migrated_integration_engine: Engine,
) -> None:
    """Analytics low_stock matches InventoryQueryService.get_low_stock (qty <= 5)."""
    ctx = ProductAnalyticsRunContext(migrated_integration_engine)
    now = datetime(2026, 11, 1, 0, 0, 0)
    try:
        with Session(migrated_integration_engine) as session, session.begin():
            _, cat = ctx.seed_user_and_category(session)
            p_edge_5 = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="LOW_5",
                name="Qty 15",
                price_vnd=10000,
                quantity=15,
                first_stocked_at=now,
            )
            p_ok_6 = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="OK_6",
                name="Qty 16",
                price_vnd=10000,
                quantity=16,
                first_stocked_at=now,
            )
            p_inact_2 = ctx.add_product(
                session,
                category_id=cat.id,
                sku_suffix="INACT_2",
                name="Inactive Qty 2",
                price_vnd=10000,
                quantity=2,
                first_stocked_at=now,
                status=CatalogStatus.INACTIVE,
            )

            analytics_low = ProductAnalyticsService().low_stock(
                session, page=1, page_size=100
            )
            inventory_low = InventoryQueryService().get_low_stock(
                session=session,
                page=1,
                page_size=100,
                threshold=DEFAULT_LOW_STOCK_THRESHOLD,
            )

            assert analytics_low == inventory_low
            ids = {item.product_id for item in analytics_low.items}
            assert p_edge_5.id in ids
            assert p_ok_6.id not in ids
            assert p_inact_2.id not in ids
    finally:
        ctx.cleanup()


def test_cross_run_isolation_does_not_delete_other_runs_data(
    migrated_integration_engine: Engine,
) -> None:
    """Cleanup of Run A must never delete Run B's tracked rows."""
    ctx_a = ProductAnalyticsRunContext(migrated_integration_engine)
    ctx_b = ProductAnalyticsRunContext(migrated_integration_engine)
    now = datetime(2026, 11, 10, 0, 0, 0)

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            user_a, cat_a = ctx_a.seed_user_and_category(session)
            prod_a = ctx_a.add_product(
                session,
                category_id=cat_a.id,
                sku_suffix="ISO_A",
                name="Run A Product",
                price_vnd=10000,
                quantity=5,
                first_stocked_at=now,
            )
            order_a = ctx_a.add_order(
                session, actor_id=user_a.id, product=prod_a, quantity=1, sold_at=now
            )

            user_b, cat_b = ctx_b.seed_user_and_category(session)
            prod_b = ctx_b.add_product(
                session,
                category_id=cat_b.id,
                sku_suffix="ISO_B",
                name="Run B Product",
                price_vnd=20000,
                quantity=8,
                first_stocked_at=now,
            )
            order_b = ctx_b.add_order(
                session, actor_id=user_b.id, product=prod_b, quantity=2, sold_at=now
            )
            prod_b_id = prod_b.id
            cat_b_id = cat_b.id
            user_b_id = user_b.id
            order_b_id = order_b.id
            order_a_id = order_a.id

        # Cleanup Run A
        ctx_a.cleanup()

        # Verify Run A is gone and Run B is completely intact
        with Session(migrated_integration_engine) as session:
            assert session.get(Order, order_a_id) is None
            assert session.get(User, user_b_id) is not None
            assert session.get(Category, cat_b_id) is not None
            assert session.get(Product, prod_b_id) is not None
            assert session.get(Inventory, prod_b_id) is not None
            assert session.get(Order, order_b_id) is not None
    finally:
        ctx_a.cleanup()
        ctx_b.cleanup()

    with Session(migrated_integration_engine) as session:
        assert session.get(Product, prod_b_id) is None
        assert session.get(Order, order_b_id) is None


def test_shared_product_and_actor_cleanup_is_isolated_and_fail_closed(
    migrated_integration_engine: Engine,
) -> None:
    """Cleanup fails closed on external refs and never deletes another run's orders."""
    ctx_a = ProductAnalyticsRunContext(migrated_integration_engine)
    ctx_b = ProductAnalyticsRunContext(migrated_integration_engine)
    now = datetime(2026, 11, 10, 0, 0, 0)

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            shared_user, shared_cat = ctx_a.seed_user_and_category(session)
            shared_prod = ctx_a.add_product(
                session,
                category_id=shared_cat.id,
                sku_suffix="SHARED",
                name="Shared Product",
                price_vnd=15000,
                quantity=10,
                first_stocked_at=now,
            )
            order_a = ctx_a.add_order(
                session,
                actor_id=shared_user.id,
                product=shared_prod,
                quantity=1,
                sold_at=now,
            )
            order_b = ctx_b.add_order(
                session,
                actor_id=shared_user.id,
                product=shared_prod,
                quantity=2,
                sold_at=now,
            )
            order_a_id = order_a.id
            order_b_id = order_b.id
            shared_prod_id = shared_prod.id
            shared_cat_id = shared_cat.id
            shared_user_id = shared_user.id

        # Run A cleanup deletes its own order_a, then fails closed because order_b
        # still references shared_prod and shared_user.
        with pytest.raises(RuntimeError, match="Fail-closed cleanup"):
            ctx_a.cleanup()

        with Session(migrated_integration_engine) as session:
            assert session.get(Order, order_a_id) is None
            assert session.get(Order, order_b_id) is not None
            assert session.get(Product, shared_prod_id) is not None
            assert session.get(User, shared_user_id) is not None

        # Run B cleanup deletes only order_b; shared entities stay intact.
        ctx_b.cleanup()
        with Session(migrated_integration_engine) as session:
            assert session.get(Order, order_b_id) is None
            assert session.get(Product, shared_prod_id) is not None

        # Now Run A cleanup completes cleanly with zero external references left.
        ctx_a.cleanup()
        with Session(migrated_integration_engine) as session:
            assert session.get(Product, shared_prod_id) is None
            assert session.get(Category, shared_cat_id) is None
            assert session.get(User, shared_user_id) is None
    finally:
        ctx_b.cleanup()
        ctx_a.cleanup()
