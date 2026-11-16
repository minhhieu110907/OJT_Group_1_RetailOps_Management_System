"""MySQL integration tests for T04A840 Order History and Detail APIs."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.models import Inventory
from app.modules.products.models import CatalogStatus, Product
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.repository import OrderRepository
from app.modules.sales.service import OrderQuery, OrderReadService
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04A840_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


def _unique_token(suffix: str) -> str:
    return f"{TEST_PREFIX}{suffix}_{uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def clean_orders_test_rows(migrated_integration_engine: Engine):
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


def test_order_read_mysql_sorting_dates_and_search_no_duplicates(
    migrated_integration_engine: Engine,
) -> None:
    now_unaware = datetime.now(UTC).replace(tzinfo=None)

    with Session(migrated_integration_engine) as session, session.begin():
        staff = User(
            email_normalized=f"{TEST_PREFIX.lower()}staff_{uuid4().hex[:6]}@example.com",
            password_hash="$2b$04$test.hash.staff",
            role=UserRole.STAFF.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=None,
            last_reapplied_at=None,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(staff)
        session.flush()
        staff_id = staff.id

        category = Category(
            name=_unique_token("Cat"),
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(category)
        session.flush()

        # Seed products
        p1 = Product(
            sku=f"{TEST_PREFIX}SKU-MULTI-A",
            name="Product A",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=20_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        p2 = Product(
            sku=f"{TEST_PREFIX}SKU-MULTI-B",
            name="Product B",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=30_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        p3 = Product(
            sku=f"{TEST_PREFIX}SKU-MULTI-C",
            name="Product C",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=40_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add_all([p1, p2, p3])
        session.flush()

        # Order 1: Sold at 2026-11-14 23:30:00 Vietnam time (UTC: 2026-11-14 16:30:00)
        # Contains 2 items: SKU-MULTI-A and SKU-MULTI-B
        o1 = Order(
            status="COMPLETED",
            total_vnd=50_000,
            created_by=staff_id,
            sold_at=datetime(2026, 11, 14, 16, 30, 0),
        )
        session.add(o1)
        session.flush()
        session.add(
            OrderItem(
                order_id=o1.id,
                product_id=p1.id,
                sku_snapshot=p1.sku,
                product_name_snapshot=p1.name,
                quantity=1,
                unit_price_vnd=20_000,
                line_total_vnd=20_000,
            )
        )
        session.add(
            OrderItem(
                order_id=o1.id,
                product_id=p2.id,
                sku_snapshot=p2.sku,
                product_name_snapshot=p2.name,
                quantity=1,
                unit_price_vnd=30_000,
                line_total_vnd=30_000,
            )
        )

        # Order 2: Sold at 2026-11-15 00:15:00 Vietnam time (UTC: 2026-11-14 17:15:00)
        # Status CANCELLED, contains SKU-MULTI-A and SKU-MULTI-C
        o2 = Order(
            status="CANCELLED",
            total_vnd=60_000,
            created_by=staff_id,
            sold_at=datetime(2026, 11, 14, 17, 15, 0),
            cancelled_by=staff_id,
            cancelled_at=datetime(2026, 11, 14, 17, 25, 0),
            cancel_reason="Customer changed mind",
        )
        session.add(o2)
        session.flush()
        session.add(
            OrderItem(
                order_id=o2.id,
                product_id=p1.id,
                sku_snapshot=p1.sku,
                product_name_snapshot=p1.name,
                quantity=1,
                unit_price_vnd=20_000,
                line_total_vnd=20_000,
            )
        )
        session.add(
            OrderItem(
                order_id=o2.id,
                product_id=p3.id,
                sku_snapshot=p3.sku,
                product_name_snapshot=p3.name,
                quantity=1,
                unit_price_vnd=40_000,
                line_total_vnd=40_000,
            )
        )

        # Order 3: Sold earlier at 17:00 VN time (UTC: 2026-11-14 10:00:00)
        # Status COMPLETED, contains SKU-MULTI-B
        o3 = Order(
            status="COMPLETED",
            total_vnd=30_000,
            created_by=staff_id,
            sold_at=datetime(2026, 11, 14, 10, 0, 0),
        )
        session.add(o3)
        session.flush()
        session.add(
            OrderItem(
                order_id=o3.id,
                product_id=p2.id,
                sku_snapshot=p2.sku,
                product_name_snapshot=p2.name,
                quantity=1,
                unit_price_vnd=30_000,
                line_total_vnd=30_000,
            )
        )

        o1_id, o2_id, o3_id = o1.id, o2.id, o3.id

    service = OrderReadService(repository=OrderRepository())

    with Session(migrated_integration_engine) as session:
        # 1. Test sorting: sold_at DESC, id DESC
        # Order 2 (17:15 UTC) > Order 1 (16:30 UTC) > Order 3 (10:00 UTC)
        page_all = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(search=TEST_PREFIX),
        )
        assert page_all.total == 3
        returned_ids = [order.id for order in page_all.items]
        assert returned_ids == [o2_id, o1_id, o3_id]

        # 2. Test Vietnam business date boundaries:
        # 2026-11-14 VN covers [2026-11-13 17:00:00 UTC, 2026-11-14 17:00:00 UTC)
        # Must include o1 (16:30 UTC) and o3 (10:00 UTC)
        # Must exclude o2 (17:15 UTC which is 00:15 VN on 2026-11-15)
        page_nov14 = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(
                from_date=date(2026, 11, 14),
                to_date=date(2026, 11, 14),
                search=TEST_PREFIX,
            ),
        )
        assert page_nov14.total == 2
        nov14_ids = [order.id for order in page_nov14.items]
        assert nov14_ids == [o1_id, o3_id]

        # 2026-11-15 VN covers [2026-11-14 17:00:00 UTC, 2026-11-15 17:00:00 UTC)
        # Must include o2 (17:15 UTC) only
        page_nov15 = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(
                from_date=date(2026, 11, 15),
                to_date=date(2026, 11, 15),
                search=TEST_PREFIX,
            ),
        )
        assert page_nov15.total == 1
        assert page_nov15.items[0].id == o2_id

        # 3. Test status filter
        page_cancelled = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(status="CANCELLED", search=TEST_PREFIX),
        )
        assert page_cancelled.total == 1
        cancelled_item = page_cancelled.items[0]
        assert cancelled_item.id == o2_id
        assert cancelled_item.status == "CANCELLED"
        assert cancelled_item.cancelled_by == staff_id
        assert cancelled_item.cancel_reason == "Customer changed mind"
        assert cancelled_item.cancelled_at is not None
        assert cancelled_item.cancelled_at.tzinfo == UTC

        # 4. Test search without duplicate rows
        # SKU-MULTI-A is present in both o1 and o2 (which have 2 lines each)
        # EXISTS subquery ensures each matching Order is returned exactly once
        page_sku_a = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(search="SKU-MULTI-A"),
        )
        assert page_sku_a.total == 2
        assert len(page_sku_a.items) == 2
        sku_a_ids = [order.id for order in page_sku_a.items]
        assert sku_a_ids == [o2_id, o1_id]

        # Search by exact order ID
        page_order_1 = service.list(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            filters=OrderQuery(search=str(o1_id)),
        )
        assert page_order_1.total == 1
        assert page_order_1.items[0].id == o1_id

        # 5. Test single order retrieval by ID
        order_detail = service.get(
            session, actor_id=staff_id, actor_role="STAFF", order_id=o2_id
        )
        assert order_detail.id == o2_id
        assert order_detail.status == "CANCELLED"
        assert order_detail.total_vnd == 60_000
        assert len(order_detail.items) == 2
        assert {item.sku_snapshot for item in order_detail.items} == {
            f"{TEST_PREFIX}SKU-MULTI-A",
            f"{TEST_PREFIX}SKU-MULTI-C",
        }
