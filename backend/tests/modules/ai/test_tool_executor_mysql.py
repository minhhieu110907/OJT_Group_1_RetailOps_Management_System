"""Read-only smoke test on the dedicated MySQL integration fixture only."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.modules.ai.tool_executor import bind_authenticated_request
from app.modules.analytics.service import (
    ProductAnalyticsService,
    SalesAnalyticsService,
    resolve_days_period,
    resolve_sales_period,
)
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.service import InventoryQueryService
from app.modules.products.models import CatalogStatus, Inventory, Product
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


def test_real_read_services_leave_database_unmodified(migrated_integration_engine):
    with Session(migrated_integration_engine) as session, session.begin():
        now = datetime(2026, 11, 18, 12, 0)
        admin = session.scalar(
            select(User).where(
                User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
            )
        )
        if admin is None:
            admin = User(
                email_normalized=f"ai-integration-{uuid4().hex}@example.test",
                password_hash="integration-fixture-no-login",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()
        staff = User(
            email_normalized=f"ai-integration-staff-{uuid4().hex}@example.test",
            password_hash="integration-fixture-no-login",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        category = Category(
            name=f"AI integration {uuid4().hex}",
            status=CatalogStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add_all([staff, category])
        session.flush()

        def clock() -> datetime:
            return datetime(2026, 11, 18, 12, 0, tzinfo=UTC)

        sales_period = resolve_sales_period(
            from_date=date(2026, 11, 18),
            to_date=date(2026, 11, 18),
            now_fn=clock,
        )
        top_period = resolve_days_period(7, now_fn=clock)
        baseline_sales = SalesAnalyticsService().summary(session, period=sales_period)
        baseline_top = (
            ProductAnalyticsService()
            .top(session, period=top_period, page=1, page_size=20)
            .total
        )
        baseline_slow = (
            ProductAnalyticsService()
            .slow(session, as_of_utc=clock(), page=1, page_size=20)
            .total
        )
        baseline_low = (
            InventoryQueryService()
            .get_low_stock(session=session, page=1, page_size=20)
            .total
        )
        sold_product = Product(
            category_id=category.id,
            sku=f"AI-SOLD-{uuid4().hex}",
            name="AI sold product",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=50_000,
            created_at=now,
            updated_at=now,
        )
        slow_product = Product(
            category_id=category.id,
            sku=f"AI-SLOW-{uuid4().hex}",
            name="AI slow low-stock product",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=25_000,
            created_at=now,
            updated_at=now,
        )
        low_product = Product(
            category_id=category.id,
            sku=f"AI-LOW-{uuid4().hex}",
            name="AI low-stock product",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=10_000,
            created_at=now,
            updated_at=now,
        )
        session.add_all([sold_product, slow_product, low_product])
        session.flush()
        session.add_all(
            [
                Inventory(
                    product_id=sold_product.id,
                    quantity=20,
                    stock_version=1,
                    first_stocked_at=datetime(2026, 10, 1),
                    updated_at=now,
                ),
                Inventory(
                    product_id=slow_product.id,
                    quantity=2_147_483_647,
                    stock_version=1,
                    first_stocked_at=datetime(1000, 1, 1),
                    updated_at=now,
                ),
                Inventory(
                    product_id=low_product.id,
                    quantity=0,
                    stock_version=0,
                    first_stocked_at=None,
                    updated_at=now,
                ),
            ]
        )
        order = Order(
            status=OrderStatus.COMPLETED,
            total_vnd=50_000_000_000,
            created_by=admin.id,
            sold_at=datetime(2026, 11, 18, 5, 0),
        )
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=sold_product.id,
                sku_snapshot=sold_product.sku,
                product_name_snapshot=sold_product.name,
                quantity=1_000_000,
                unit_price_vnd=50_000,
                line_total_vnd=50_000_000_000,
            )
        )
        session.flush()
        writes = []

        def record_write(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().split(maxsplit=1)[0].upper() not in {
                "SELECT",
                "WITH",
            }:
                writes.append(statement.split(maxsplit=1)[0])

        event.listen(migrated_integration_engine, "before_cursor_execute", record_write)
        try:
            # The contract permits three calls per request; exercise all four
            # real services across two independently bound requests.
            expected_product = {
                "get_top_products": sold_product.id,
                "get_slow_products": slow_product.id,
                "get_low_stock": low_product.id,
            }
            arguments = {
                "get_sales_summary": {
                    "start_date": "2026-11-18",
                    "end_date": "2026-11-18",
                },
                "get_top_products": {"days": 7, "limit": 20},
                "get_slow_products": {"limit": 20},
                "get_low_stock": {"limit": 20},
            }
            for index, tool_id in enumerate(
                expected_product | {"get_sales_summary": 0}
            ):
                if index % 3 == 0:
                    bound = bind_authenticated_request(
                        CurrentPrincipal(user=admin, session_id=uuid4()),
                        request_id=f"ai-mysql-smoke-{index}",
                        clock=clock,
                    )
                result = bound.executor.execute(
                    session,
                    tool_id=tool_id,
                    arguments=arguments[tool_id],
                    context=bound.context,
                )
                assert result.tool_id == tool_id
                if tool_id == "get_sales_summary":
                    assert (
                        result.data["revenue_vnd"]
                        == baseline_sales.revenue_vnd + 50_000_000_000
                    )
                    assert (
                        result.data["completed_orders"]
                        == baseline_sales.completed_orders + 1
                    )
                else:
                    baseline_total = {
                        "get_top_products": baseline_top,
                        "get_slow_products": baseline_slow,
                        "get_low_stock": baseline_low,
                    }[tool_id]
                    assert result.data["total"] == baseline_total + 1
                    assert expected_product[tool_id] in {
                        item["product_id"] for item in result.data["items"]
                    }

            staff_bound = bind_authenticated_request(
                CurrentPrincipal(user=staff, session_id=uuid4()),
                request_id="ai-mysql-staff",
            )
            with pytest.raises(ForbiddenError):
                staff_bound.executor.execute(
                    session,
                    tool_id="get_sales_summary",
                    arguments={},
                    context=staff_bound.context,
                )
        finally:
            event.remove(
                migrated_integration_engine, "before_cursor_execute", record_write
            )
        assert writes == []
        assert not session.new and not session.dirty and not session.deleted
        session.rollback()  # discard every deterministic fixture row
