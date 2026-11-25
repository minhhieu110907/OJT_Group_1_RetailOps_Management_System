"""MySQL 8.4 integration tests for Reorder Advisor & sold_units_for_products."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.ai.reorder_advisor import ReadOnlyReorderAdvisor
from app.modules.ai.tool_executor import bind_authenticated_request
from app.modules.analytics.service import (
    ProductAnalyticsService,
    resolve_days_period,
)
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.security import PasswordHasher
from app.modules.categories.models import Category
from app.modules.inventory.models import StockMovement
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
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


def test_sold_units_for_products_and_reorder_advisor_readonly_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify exact COMPLETED half-open sales query and read-only invariant on MySQL."""
    run_id = uuid4().hex[:12]
    # Fixed UTC clock aligned with resolve_days_period(7) half-open UTC window
    fixed_clock = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    period = resolve_days_period(7, now_fn=lambda: fixed_clock)
    start_utc = period.start_utc
    end_utc_exclusive = period.end_utc_exclusive
    start_naive = start_utc.replace(tzinfo=None)
    end_naive = end_utc_exclusive.replace(tzinfo=None)
    now_naive = fixed_clock.replace(tzinfo=None)

    hasher = PasswordHasher(work_factor=4)
    owned_user_ids: list[int] = []
    reused_admin_id: int | None = None
    category_ids: list[int] = []
    product_ids: list[int] = []
    order_ids: list[int] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            existing_admin = session.scalar(
                select(User).where(
                    User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
                )
            )
            if existing_admin is None:
                admin = User(
                    email_normalized=f"t04ab0b-admin-{run_id}@example.com",
                    password_hash=hasher.hash("AdminPass!123"),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                    admin_slot=1,
                    created_at=now_naive,
                    updated_at=now_naive,
                )
                session.add(admin)
                session.flush()
                admin_id = admin.id
                owned_user_ids.append(admin_id)
            else:
                admin_id = existing_admin.id
                reused_admin_id = admin_id

            cat = Category(
                name=f"T04AB0B-Cat-{run_id}",
                description="MySQL integration category",
                status=CatalogStatus.ACTIVE,
                created_at=now_naive,
                updated_at=now_naive,
            )
            session.add(cat)
            session.flush()
            category_ids.append(cat.id)

            p_sold = Product(
                category_id=cat.id,
                sku=f"T04AB0B-S-{run_id}",
                name=f"Sold Item {run_id}",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=25_000,
                created_at=now_naive,
                updated_at=now_naive,
            )
            p_zero = Product(
                category_id=cat.id,
                sku=f"T04AB0B-Z-{run_id}",
                name=f"Zero Item {run_id}",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=25_000,
                created_at=now_naive,
                updated_at=now_naive,
            )
            session.add_all([p_sold, p_zero])
            session.flush()
            product_ids.extend([p_sold.id, p_zero.id])

            session.add_all(
                [
                    Inventory(
                        product_id=p_sold.id,
                        quantity=2,
                        stock_version=1,
                        first_stocked_at=now_naive - timedelta(days=2),
                        updated_at=now_naive,
                    ),
                    Inventory(
                        product_id=p_zero.id,
                        quantity=1,
                        stock_version=1,
                        first_stocked_at=now_naive - timedelta(days=2),
                        updated_at=now_naive,
                    ),
                ]
            )

            # 1) COMPLETED at exact start_utc (INCLUDED: +4)
            o_in_start = Order(
                created_by=admin_id,
                status=OrderStatus.COMPLETED,
                total_vnd=100_000,
                sold_at=start_naive,
            )
            # 2) COMPLETED inside window (INCLUDED: +3)
            o_in_mid = Order(
                created_by=admin_id,
                status=OrderStatus.COMPLETED,
                total_vnd=75_000,
                sold_at=start_naive + timedelta(days=3),
            )
            # 3) CANCELLED inside window (EXCLUDED)
            o_cancelled = Order(
                created_by=admin_id,
                status=OrderStatus.CANCELLED,
                total_vnd=50_000,
                sold_at=start_naive + timedelta(days=2),
                cancelled_by=admin_id,
                cancelled_at=start_naive + timedelta(days=2, minutes=5),
                cancel_reason="Test cancel exclusion",
            )
            # 4) COMPLETED at exact end_utc_exclusive (EXCLUDED by half-open bound)
            o_at_end = Order(
                created_by=admin_id,
                status=OrderStatus.COMPLETED,
                total_vnd=125_000,
                sold_at=end_naive,
            )
            # 5) COMPLETED before start_utc (EXCLUDED)
            o_before = Order(
                created_by=admin_id,
                status=OrderStatus.COMPLETED,
                total_vnd=25_000,
                sold_at=start_naive - timedelta(seconds=1),
            )
            session.add_all([o_in_start, o_in_mid, o_cancelled, o_at_end, o_before])
            session.flush()
            order_ids.extend(
                [o_in_start.id, o_in_mid.id, o_cancelled.id, o_at_end.id, o_before.id]
            )

            session.add_all(
                [
                    OrderItem(
                        order_id=o_in_start.id,
                        product_id=p_sold.id,
                        sku_snapshot=p_sold.sku,
                        product_name_snapshot=p_sold.name,
                        unit_price_vnd=25_000,
                        quantity=4,
                        line_total_vnd=100_000,
                    ),
                    OrderItem(
                        order_id=o_in_mid.id,
                        product_id=p_sold.id,
                        sku_snapshot=p_sold.sku,
                        product_name_snapshot=p_sold.name,
                        unit_price_vnd=25_000,
                        quantity=3,
                        line_total_vnd=75_000,
                    ),
                    OrderItem(
                        order_id=o_cancelled.id,
                        product_id=p_sold.id,
                        sku_snapshot=p_sold.sku,
                        product_name_snapshot=p_sold.name,
                        unit_price_vnd=25_000,
                        quantity=2,
                        line_total_vnd=50_000,
                    ),
                    OrderItem(
                        order_id=o_at_end.id,
                        product_id=p_sold.id,
                        sku_snapshot=p_sold.sku,
                        product_name_snapshot=p_sold.name,
                        unit_price_vnd=25_000,
                        quantity=5,
                        line_total_vnd=125_000,
                    ),
                    OrderItem(
                        order_id=o_before.id,
                        product_id=p_sold.id,
                        sku_snapshot=p_sold.sku,
                        product_name_snapshot=p_sold.name,
                        unit_price_vnd=25_000,
                        quantity=1,
                        line_total_vnd=25_000,
                    ),
                ]
            )
            sold_pid, zero_pid = p_sold.id, p_zero.id

        # Verify ProductAnalyticsService.sold_units_for_products on MySQL 8.4
        analytics = ProductAnalyticsService()
        with Session(migrated_integration_engine) as session:
            sold_map = analytics.sold_units_for_products(
                session,
                product_ids=[sold_pid, zero_pid],
                period=period,
            )
            assert set(sold_map.keys()) == {sold_pid, zero_pid}
            assert (
                sold_map[sold_pid] == 7
            )  # 4 (at start) + 3 (mid); excludes cancel/end/before
            assert sold_map[zero_pid] == 0

            # Capture DB counts before running advisor
            counts_before = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(PurchaseReceiptItem.receipt_id))),
            )

            admin_user = session.get(User, admin_id)
            assert admin_user is not None
            principal = CurrentPrincipal(user=admin_user, session_id=b"\x33" * 16)
            bound = bind_authenticated_request(
                principal,
                request_id=f"mysql-t04ab0b-{run_id}",
                clock=lambda: fixed_clock,
            )
            snapshot = bound.executor.collect_reorder_snapshot(
                session, context=bound.context, analysis_days=7
            )
            report = ReadOnlyReorderAdvisor().suggest(
                low_stock_result=snapshot.low_stock_result,
                product_sales_by_id=snapshot.product_sales_by_id,
                sales_period=snapshot.sales_period,
                slow_products_result=snapshot.slow_products_result,
                analysis_days=snapshot.analysis_days,
                low_stock_truncated=snapshot.low_stock_truncated,
                low_stock_total_available=snapshot.low_stock_total_available,
                slow_products_truncated=snapshot.slow_products_truncated,
                source_errors=snapshot.source_errors,
            )
            by_id = {r.product_id: r for r in report.recommendations}
            assert by_id[sold_pid].sold_units == 7
            assert by_id[sold_pid].suggested_quantity == 13  # max(1, 15-2, 7-2)
            assert by_id[zero_pid].sold_units == 0
            assert by_id[zero_pid].suggested_quantity is None

            # Verify zero DB mutation after advisor execution
            inv_sold = session.get(Inventory, sold_pid)
            inv_zero = session.get(Inventory, zero_pid)
            assert (
                inv_sold is not None
                and inv_sold.quantity == 2
                and inv_sold.stock_version == 1
            )
            assert (
                inv_zero is not None
                and inv_zero.quantity == 1
                and inv_zero.stock_version == 1
            )
            counts_after = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
                session.scalar(select(func.count(PurchaseReceiptItem.receipt_id))),
            )
            assert counts_after == counts_before
    finally:
        with Session(migrated_integration_engine) as session, session.begin():
            if order_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
                )
                session.execute(delete(Order).where(Order.id.in_(order_ids)))
            if product_ids:
                session.execute(
                    delete(StockMovement).where(
                        StockMovement.product_id.in_(product_ids)
                    )
                )
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(product_ids))
                )
                session.execute(delete(Product).where(Product.id.in_(product_ids)))
            if category_ids:
                session.execute(delete(Category).where(Category.id.in_(category_ids)))
            if owned_user_ids and reused_admin_id is None:
                session.execute(delete(User).where(User.id.in_(owned_user_ids)))
