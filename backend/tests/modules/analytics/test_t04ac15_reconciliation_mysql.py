"""MySQL integration tests for T04AC15 cross-module reconciliation.

Verification Level: MySQL 8.4 Integration Tests with Real Services
(SalesAnalyticsService, ProductAnalyticsService, DashboardService)
executing on real InnoDB tables with deterministic baseline delta assertions.

Test Scenarios:
1. Standard Demo Dataset Reconciliation on Real MySQL:
   - 4 Products: Coca 12k, Sữa TH 38k, Lay's 20k, Cá ngừ 45k
   - Purchasing: Receipt confirmed, stock movements recorded
   - POS Checkout: Order #1 (2 Coca + 1 Sữa TH = 62k) COMPLETED
   - Order Cancellation: Order #2 (3 Lay's + 1 Cá ngừ = 105k) CANCELLED, stock restored
   - Sales Analytics: revenue=62k, completed=1, cancelled=1, aov=62k
   - Product Analytics: Top (Coca, Sữa TH), Slow (Lay's, Cá ngừ)
   - Dashboard: synchronous aggregation (sales 62k, low_stock=2, top_products=2)
2. Catalog Price Mutation Snapshot Immutability on MySQL:
   - Increasing catalog prices after checkout does NOT alter historical revenue (62k)
3. Safe Teardown & Idempotent Cleanup Isolation:
   - Run A cleanup does not affect Run B (Users, Categories, Suppliers, Products).
   - Repeated cleanup() calls are safe no-ops (idempotent).
4. Fail-Closed Rollback on External Reference Violation:
   - External OrderItem referencing tracked product raises RuntimeError.
   - Atomic transaction rollback guarantees 0 partial deletions.
5. Shared ADMIN & IdempotencyRecord Immunity Defense-in-Depth:
   - Shared ADMIN (admin_slot == 1) and its IdempotencyRecords are never deleted
     even if user_ids contains admin_id.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.analytics.service import (
    VN_TZ,
    DashboardService,
    ProductAnalyticsService,
    SalesAnalyticsService,
    resolve_sales_period,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.inventory.models import Inventory, MovementKind, StockMovement
from app.modules.products.models import CatalogStatus, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.sales.models import Order, OrderItem, OrderStatus
from app.modules.suppliers.models import Supplier
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04AC15_"

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
        self.stock_movement_ids: list[int] = []
        self.order_ids: list[int] = []
        self.receipt_ids: list[int] = []
        self.product_ids: list[int] = []
        self.supplier_ids: list[int] = []
        self.category_ids: list[int] = []
        self.user_ids: list[int] = []

    def cleanup(self) -> None:
        """Teardown strictly this run's tracked rows with fail-closed reference checks.

        Guarantees:
        - Atomic execution: all checks and deletions run inside a single transaction.
        - Fail-closed: if external records reference tracked entities, raises
          RuntimeError and rolls back immediately (no partial deletions).
        - Exact ID tracking: only tracked IDs are deleted; never expands scope.
        - Shared ADMIN protection: never deletes users with admin_slot = 1.
        - Idempotency: clears all ID lists on commit; repeated calls are safe no-ops.
        """
        if not (
            self.stock_movement_ids
            or self.order_ids
            or self.receipt_ids
            or self.product_ids
            or self.supplier_ids
            or self.category_ids
            or self.user_ids
        ):
            return

        with (
            Session(self.engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # 1. Fail-closed reference checks before any deletions
            if self.product_ids:
                # External OrderItem referencing tracked products
                ext_oi_filter = [OrderItem.product_id.in_(self.product_ids)]
                if self.order_ids:
                    ext_oi_filter.append(OrderItem.order_id.not_in(self.order_ids))
                ext_oi = session.scalar(
                    select(OrderItem.order_id).where(*ext_oi_filter).limit(1)
                )
                if ext_oi is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external OrderItem (order_id={ext_oi})."
                    )

                # External PurchaseReceiptItem referencing tracked products
                ext_pri_filter = [PurchaseReceiptItem.product_id.in_(self.product_ids)]
                if self.receipt_ids:
                    ext_pri_filter.append(
                        PurchaseReceiptItem.receipt_id.not_in(self.receipt_ids)
                    )
                ext_pri = session.scalar(
                    select(PurchaseReceiptItem.receipt_id)
                    .where(*ext_pri_filter)
                    .limit(1)
                )
                if ext_pri is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external PurchaseReceiptItem (receipt_id={ext_pri})."
                    )

                # External StockMovement referencing tracked products
                ext_sm_filter = [StockMovement.product_id.in_(self.product_ids)]
                if self.stock_movement_ids:
                    ext_sm_filter.append(
                        StockMovement.id.not_in(self.stock_movement_ids)
                    )
                ext_sm = session.scalar(
                    select(StockMovement.id).where(*ext_sm_filter).limit(1)
                )
                if ext_sm is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked product(s) still referenced "
                        f"by external StockMovement (id={ext_sm})."
                    )

            if self.category_ids:
                # External Product referencing tracked categories
                ext_cat_filter = [Product.category_id.in_(self.category_ids)]
                if self.product_ids:
                    ext_cat_filter.append(Product.id.not_in(self.product_ids))
                ext_cat_prod = session.scalar(
                    select(Product.id).where(*ext_cat_filter).limit(1)
                )
                if ext_cat_prod is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked category(ies) still referenced "
                        f"by external Product (id={ext_cat_prod})."
                    )

            if self.supplier_ids:
                # External PurchaseReceipt referencing tracked suppliers
                ext_sup_filter = [PurchaseReceipt.supplier_id.in_(self.supplier_ids)]
                if self.receipt_ids:
                    ext_sup_filter.append(PurchaseReceipt.id.not_in(self.receipt_ids))
                ext_sup_receipt = session.scalar(
                    select(PurchaseReceipt.id).where(*ext_sup_filter).limit(1)
                )
                if ext_sup_receipt is not None:
                    raise RuntimeError(
                        "Fail-closed cleanup: tracked supplier(s) still referenced "
                        f"by external PurchaseReceipt (id={ext_sup_receipt})."
                    )

            if self.user_ids:
                # Check disposable test users (exclude Shared Admin with admin_slot=1)
                disposable_user_ids = list(
                    session.scalars(
                        select(User.id).where(
                            User.id.in_(self.user_ids),
                            User.admin_slot.is_(None),
                        )
                    )
                )

                if disposable_user_ids:
                    # External Order referencing disposable test users
                    ext_usr_order_filter = [
                        or_(
                            Order.created_by.in_(disposable_user_ids),
                            Order.cancelled_by.in_(disposable_user_ids),
                        )
                    ]
                    if self.order_ids:
                        ext_usr_order_filter.append(Order.id.not_in(self.order_ids))
                    ext_usr_order = session.scalar(
                        select(Order.id).where(*ext_usr_order_filter).limit(1)
                    )
                    if ext_usr_order is not None:
                        raise RuntimeError(
                            "Fail-closed cleanup: tracked user(s) still referenced "
                            f"by external Order (id={ext_usr_order})."
                        )

                    # External PurchaseReceipt referencing disposable test users
                    ext_usr_rcpt_filter = [
                        PurchaseReceipt.created_by.in_(disposable_user_ids)
                    ]
                    if self.receipt_ids:
                        ext_usr_rcpt_filter.append(
                            PurchaseReceipt.id.not_in(self.receipt_ids)
                        )
                    ext_usr_rcpt = session.scalar(
                        select(PurchaseReceipt.id).where(*ext_usr_rcpt_filter).limit(1)
                    )
                    if ext_usr_rcpt is not None:
                        raise RuntimeError(
                            "Fail-closed cleanup: tracked user(s) still referenced "
                            f"by external PurchaseReceipt (id={ext_usr_rcpt})."
                        )

                    # External StockMovement referencing disposable test users
                    ext_usr_sm_filter = [
                        StockMovement.actor_id.in_(disposable_user_ids)
                    ]
                    if self.stock_movement_ids:
                        ext_usr_sm_filter.append(
                            StockMovement.id.not_in(self.stock_movement_ids)
                        )
                    ext_usr_sm = session.scalar(
                        select(StockMovement.id).where(*ext_usr_sm_filter).limit(1)
                    )
                    if ext_usr_sm is not None:
                        raise RuntimeError(
                            "Fail-closed cleanup: tracked user(s) still referenced "
                            f"by external StockMovement (id={ext_usr_sm})."
                        )

            # 2. Deletions strictly by exact tracked IDs in reverse dependency order
            if self.stock_movement_ids:
                session.execute(
                    delete(StockMovement).where(
                        StockMovement.id.in_(self.stock_movement_ids)
                    )
                )

            if self.order_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(self.order_ids))
                )
                session.execute(delete(Order).where(Order.id.in_(self.order_ids)))

            if self.receipt_ids:
                session.execute(
                    delete(PurchaseReceiptItem).where(
                        PurchaseReceiptItem.receipt_id.in_(self.receipt_ids)
                    )
                )
                session.execute(
                    delete(PurchaseReceipt).where(
                        PurchaseReceipt.id.in_(self.receipt_ids)
                    )
                )

            if self.product_ids:
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(self.product_ids))
                )
                session.execute(delete(Product).where(Product.id.in_(self.product_ids)))

            if self.supplier_ids:
                session.execute(
                    delete(Supplier).where(Supplier.id.in_(self.supplier_ids))
                )

            if self.category_ids:
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )

            if self.user_ids:
                session.execute(
                    delete(User).where(
                        User.id.in_(self.user_ids),
                        User.admin_slot.is_(None),
                    )
                )

        # 3. Idempotent state: clear all tracked IDs after successful transaction commit
        self.stock_movement_ids.clear()
        self.order_ids.clear()
        self.receipt_ids.clear()
        self.product_ids.clear()
        self.supplier_ids.clear()
        self.category_ids.clear()
        self.user_ids.clear()


def _ensure_shared_admin(engine: Engine) -> int:
    """Find existing seed admin or create an isolated shared test admin.

    Strictly preserves admin_slot = 1 constraint.
    """
    with Session(engine) as session, session.begin():
        admin = session.scalar(select(User).where(User.admin_slot == 1))
        if admin is not None:
            return admin.id

        now = datetime(2026, 11, 20, 8, 0, 0)
        new_admin = User(
            email_normalized="t04ac15_shared_admin@example.com",
            password_hash="$2b$04$test.hash.t04ac15_shared_admin",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        session.add(new_admin)
        session.flush()
        return new_admin.id


def _create_test_staff(
    session: Session,
    *,
    now_unaware: datetime,
    prefix: str,
) -> User:
    """Helper to create a test staff user (admin_slot is always None)."""
    suffix = uuid4().hex[:6]
    staff = User(
        email_normalized=f"{prefix.lower()}staff_{suffix}@example.com",
        password_hash="$2b$04$test.hash.t04ac15_staff",
        role=UserRole.STAFF.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=None,
        created_at=now_unaware,
        updated_at=now_unaware,
    )
    session.add(staff)
    session.flush()
    return staff


# ==============================================================================
# TEST 1: STANDARD DEMO DATASET END-TO-END RECONCILIATION ON MYSQL
# ==============================================================================


def test_demo_dataset_end_to_end_reconciliation_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Thực thi trọn vẹn luồng đối soát Demo Dataset trên MySQL 8.4:

    - 4 Products: Coca 12k, Sữa TH 38k, Lay's 20k, Cá ngừ 45k
    - Purchasing: Phiếu nhập CONFIRMED tăng tồn kho, ghi thẻ kho PURCHASE_CONFIRM
    - POS Checkout: Order #1 (2 Coca + 1 TH = 62k) -> COMPLETED
    - Cancellation: Order #2 (3 Lay's + 1 Cá ngừ = 105k) -> CANCELLED, hoàn tồn kho
    - Sales Analytics: revenue=62k, completed=1, cancelled=1, aov=62k
    - Product Analytics: Top (Coca=2, TH=1), Slow (Lay's=0, Cá ngừ=0)
    - Dashboard: đồng bộ sales (62k), low_stock_count (=2), top_products (=2).
    """
    ctx = TestRunContext(migrated_integration_engine, "demo_e2e")
    admin_id = _ensure_shared_admin(migrated_integration_engine)

    # Deterministic frozen timestamp (UTC + VN) - distinct date 2026-10-15
    frozen_time_utc = datetime(2026, 10, 15, 3, 30, tzinfo=UTC)  # 10:30 AM VN
    target_date = frozen_time_utc.astimezone(VN_TZ).date()
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)
    stocked_10d_ago = now_unaware - timedelta(days=10)

    sales_svc = SalesAnalyticsService()
    dash_svc = DashboardService()
    product_svc = ProductAnalyticsService()
    period = resolve_sales_period(from_date=target_date, to_date=target_date)

    with Session(migrated_integration_engine) as baseline_session:
        baseline_sales = sales_svc.summary(baseline_session, period=period)
        baseline_low_stock = dash_svc.read(
            baseline_session, period=period
        ).low_stock_count

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # 1. Setup staff, category, supplier
            staff = _create_test_staff(
                session, now_unaware=now_unaware, prefix=ctx.prefix
            )
            ctx.user_ids.append(staff.id)

            category = Category(
                name=f"{ctx.prefix}DoUongVaThucPham",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(category)
            session.flush()
            ctx.category_ids.append(category.id)

            supplier = Supplier(
                name=f"{ctx.prefix}NhaCungCapNuocGiaiKhat",
                contact_phone="+84901234567",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(supplier)
            session.flush()
            ctx.supplier_ids.append(supplier.id)

            # 2. Setup 4 demo products
            # Coca Cola 330ml (12,000 VND)
            prod_coca = Product(
                sku=f"{ctx.prefix}DRK-COCA-330",
                name="Nước ngọt Coca Cola 330ml",
                category_id=category.id,
                sale_price_vnd=12_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            # TH True Milk 1L (38,000 VND)
            prod_milk = Product(
                sku=f"{ctx.prefix}DRK-MILK-TH1L",
                name="Sữa tươi tiệt trùng TH True Milk 1L",
                category_id=category.id,
                sale_price_vnd=38_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            # Lay's 75g (20,000 VND)
            prod_lays = Product(
                sku=f"{ctx.prefix}SNK-LAY-75G",
                name="Snack khoai tây Lay's vị tự nhiên 75g",
                category_id=category.id,
                sale_price_vnd=20_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            # Cá ngừ 185g (45,000 VND)
            prod_tuna = Product(
                sku=f"{ctx.prefix}CAN-TUNA-185G",
                name="Cá ngừ ngâm dầu Hạ Long Can 185g",
                category_id=category.id,
                sale_price_vnd=45_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add_all([prod_coca, prod_milk, prod_lays, prod_tuna])
            session.flush()
            ctx.product_ids.extend(
                [prod_coca.id, prod_milk.id, prod_lays.id, prod_tuna.id]
            )

            # 3. Setup Initial Inventory:
            # Coca: 120, Sữa TH: 50, Lay's: 5, Cá ngừ: 3
            # first_stocked_at 10 days ago (satisfies slow-moving > 7d condition)
            inv_coca = Inventory(
                product_id=prod_coca.id,
                quantity=120,
                stock_version=1,
                first_stocked_at=stocked_10d_ago,
                updated_at=now_unaware,
            )
            inv_milk = Inventory(
                product_id=prod_milk.id,
                quantity=50,
                stock_version=1,
                first_stocked_at=stocked_10d_ago,
                updated_at=now_unaware,
            )
            inv_lays = Inventory(
                product_id=prod_lays.id,
                quantity=5,
                stock_version=1,
                first_stocked_at=stocked_10d_ago,
                updated_at=now_unaware,
            )
            inv_tuna = Inventory(
                product_id=prod_tuna.id,
                quantity=3,
                stock_version=1,
                first_stocked_at=stocked_10d_ago,
                updated_at=now_unaware,
            )
            session.add_all([inv_coca, inv_milk, inv_lays, inv_tuna])
            session.flush()

            # 4. Setup Purchase Receipt CONFIRMED & Stock Movements
            # Receipt: 120 Coca (8.5k) + 50 Sữa TH (28k) + 5 Lay's (14k) + 3 Tuna (32k)
            # = 1,020,000 + 1,400,000 + 70,000 + 96,000 = 2,586,000 VND
            receipt = PurchaseReceipt(
                supplier_id=supplier.id,
                supplier_name_snapshot="Công ty TNHH Phân phối Nước giải khát Việt",
                status="CONFIRMED",
                draft_version=1,
                total_vnd=2_586_000,
                created_by=admin_id,
                closed_by=admin_id,
                created_at=stocked_10d_ago,
                updated_at=stocked_10d_ago,
                closed_at=stocked_10d_ago,
            )
            session.add(receipt)
            session.flush()
            ctx.receipt_ids.append(receipt.id)

            r_item_coca = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=prod_coca.id,
                sku_snapshot=prod_coca.sku,
                product_name_snapshot=prod_coca.name,
                quantity=120,
                unit_cost_vnd=8_500,
                line_total_vnd=120 * 8_500,
            )
            r_item_milk = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=prod_milk.id,
                sku_snapshot=prod_milk.sku,
                product_name_snapshot=prod_milk.name,
                quantity=50,
                unit_cost_vnd=28_000,
                line_total_vnd=50 * 28_000,
            )
            r_item_lays = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=prod_lays.id,
                sku_snapshot=prod_lays.sku,
                product_name_snapshot=prod_lays.name,
                quantity=5,
                unit_cost_vnd=14_000,
                line_total_vnd=5 * 14_000,
            )
            r_item_tuna = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=prod_tuna.id,
                sku_snapshot=prod_tuna.sku,
                product_name_snapshot=prod_tuna.name,
                quantity=3,
                unit_cost_vnd=32_000,
                line_total_vnd=3 * 32_000,
            )
            session.add_all([r_item_coca, r_item_milk, r_item_lays, r_item_tuna])
            session.flush()

            # Record StockMovement PURCHASE_CONFIRM for all 4 products
            sm_rcpt_coca = StockMovement(
                product_id=prod_coca.id,
                sku_snapshot=prod_coca.sku,
                receipt_id=receipt.id,
                order_id=None,
                adjustment_id=None,
                kind=MovementKind.PURCHASE_CONFIRM.value,
                quantity_before=0,
                quantity_after=120,
                stock_version_after=1,
                actor_id=admin_id,
                occurred_at=stocked_10d_ago,
            )
            sm_rcpt_milk = StockMovement(
                product_id=prod_milk.id,
                sku_snapshot=prod_milk.sku,
                receipt_id=receipt.id,
                order_id=None,
                adjustment_id=None,
                kind=MovementKind.PURCHASE_CONFIRM.value,
                quantity_before=0,
                quantity_after=50,
                stock_version_after=1,
                actor_id=admin_id,
                occurred_at=stocked_10d_ago,
            )
            sm_rcpt_lays = StockMovement(
                product_id=prod_lays.id,
                sku_snapshot=prod_lays.sku,
                receipt_id=receipt.id,
                order_id=None,
                adjustment_id=None,
                kind=MovementKind.PURCHASE_CONFIRM.value,
                quantity_before=0,
                quantity_after=5,
                stock_version_after=1,
                actor_id=admin_id,
                occurred_at=stocked_10d_ago,
            )
            sm_rcpt_tuna = StockMovement(
                product_id=prod_tuna.id,
                sku_snapshot=prod_tuna.sku,
                receipt_id=receipt.id,
                order_id=None,
                adjustment_id=None,
                kind=MovementKind.PURCHASE_CONFIRM.value,
                quantity_before=0,
                quantity_after=3,
                stock_version_after=1,
                actor_id=admin_id,
                occurred_at=stocked_10d_ago,
            )
            session.add_all([sm_rcpt_coca, sm_rcpt_milk, sm_rcpt_lays, sm_rcpt_tuna])
            session.flush()
            ctx.stock_movement_ids.extend(
                [sm_rcpt_coca.id, sm_rcpt_milk.id, sm_rcpt_lays.id, sm_rcpt_tuna.id]
            )

            # 5. Execute Order #1 (COMPLETED):
            # 2 Coca (12,000) + 1 Sữa TH (38,000) = 62,000 VND
            order_1 = Order(
                status=OrderStatus.COMPLETED.value,
                total_vnd=62_000,
                created_by=staff.id,
                sold_at=now_unaware,
                cancelled_by=None,
                cancelled_at=None,
                cancel_reason=None,
            )
            session.add(order_1)
            session.flush()
            ctx.order_ids.append(order_1.id)

            item_1_coca = OrderItem(
                order_id=order_1.id,
                product_id=prod_coca.id,
                sku_snapshot=prod_coca.sku,
                product_name_snapshot=prod_coca.name,
                quantity=2,
                unit_price_vnd=12_000,
                line_total_vnd=24_000,
            )
            item_1_milk = OrderItem(
                order_id=order_1.id,
                product_id=prod_milk.id,
                sku_snapshot=prod_milk.sku,
                product_name_snapshot=prod_milk.name,
                quantity=1,
                unit_price_vnd=38_000,
                line_total_vnd=38_000,
            )
            session.add_all([item_1_coca, item_1_milk])
            session.flush()

            # Decrement inventory and record StockMovement SALE
            inv_coca.quantity = 118
            inv_coca.stock_version = 2
            inv_coca.updated_at = now_unaware

            inv_milk.quantity = 49
            inv_milk.stock_version = 2
            inv_milk.updated_at = now_unaware

            sm_sale_coca = StockMovement(
                product_id=prod_coca.id,
                sku_snapshot=prod_coca.sku,
                receipt_id=None,
                order_id=order_1.id,
                adjustment_id=None,
                kind=MovementKind.SALE.value,
                quantity_before=120,
                quantity_after=118,
                stock_version_after=2,
                actor_id=staff.id,
                occurred_at=now_unaware,
            )
            sm_sale_milk = StockMovement(
                product_id=prod_milk.id,
                sku_snapshot=prod_milk.sku,
                receipt_id=None,
                order_id=order_1.id,
                adjustment_id=None,
                kind=MovementKind.SALE.value,
                quantity_before=50,
                quantity_after=49,
                stock_version_after=2,
                actor_id=staff.id,
                occurred_at=now_unaware,
            )
            session.add_all([sm_sale_coca, sm_sale_milk])
            session.flush()
            ctx.stock_movement_ids.extend([sm_sale_coca.id, sm_sale_milk.id])

            # 6. Execute Order #2 (CANCELLED):
            # 3 Lay's (20,000) + 1 Cá ngừ (45,000) = 105,000 VND
            cancel_time_unaware = now_unaware + timedelta(minutes=5)
            order_2 = Order(
                status=OrderStatus.CANCELLED.value,
                total_vnd=105_000,
                created_by=staff.id,
                sold_at=now_unaware,
                cancelled_by=staff.id,
                cancelled_at=cancel_time_unaware,
                cancel_reason="Khách đổi ý hủy đơn",
            )
            session.add(order_2)
            session.flush()
            ctx.order_ids.append(order_2.id)

            item_2_lays = OrderItem(
                order_id=order_2.id,
                product_id=prod_lays.id,
                sku_snapshot=prod_lays.sku,
                product_name_snapshot=prod_lays.name,
                quantity=3,
                unit_price_vnd=20_000,
                line_total_vnd=60_000,
            )
            item_2_tuna = OrderItem(
                order_id=order_2.id,
                product_id=prod_tuna.id,
                sku_snapshot=prod_tuna.sku,
                product_name_snapshot=prod_tuna.name,
                quantity=1,
                unit_price_vnd=45_000,
                line_total_vnd=45_000,
            )
            session.add_all([item_2_lays, item_2_tuna])
            session.flush()

            # Initial SALE movement when order placed (Lay's 5->2, Tuna 3->2)
            sm_sale_lays = StockMovement(
                product_id=prod_lays.id,
                sku_snapshot=prod_lays.sku,
                receipt_id=None,
                order_id=order_2.id,
                adjustment_id=None,
                kind=MovementKind.SALE.value,
                quantity_before=5,
                quantity_after=2,
                stock_version_after=2,
                actor_id=staff.id,
                occurred_at=now_unaware,
            )
            sm_sale_tuna = StockMovement(
                product_id=prod_tuna.id,
                sku_snapshot=prod_tuna.sku,
                receipt_id=None,
                order_id=order_2.id,
                adjustment_id=None,
                kind=MovementKind.SALE.value,
                quantity_before=3,
                quantity_after=2,
                stock_version_after=2,
                actor_id=staff.id,
                occurred_at=now_unaware,
            )
            session.add_all([sm_sale_lays, sm_sale_tuna])
            session.flush()
            ctx.stock_movement_ids.extend([sm_sale_lays.id, sm_sale_tuna.id])

            # Record ORDER_CANCEL movement (restores stock: Lay's 2->5, Tuna 2->3)
            inv_lays.quantity = 5
            inv_lays.stock_version = 3
            inv_lays.updated_at = cancel_time_unaware

            inv_tuna.quantity = 3
            inv_tuna.stock_version = 3
            inv_tuna.updated_at = cancel_time_unaware

            sm_cancel_lays = StockMovement(
                product_id=prod_lays.id,
                sku_snapshot=prod_lays.sku,
                receipt_id=None,
                order_id=order_2.id,
                adjustment_id=None,
                kind=MovementKind.ORDER_CANCEL.value,
                quantity_before=2,
                quantity_after=5,
                stock_version_after=3,
                actor_id=staff.id,
                occurred_at=cancel_time_unaware,
            )
            sm_cancel_tuna = StockMovement(
                product_id=prod_tuna.id,
                sku_snapshot=prod_tuna.sku,
                receipt_id=None,
                order_id=order_2.id,
                adjustment_id=None,
                kind=MovementKind.ORDER_CANCEL.value,
                quantity_before=2,
                quantity_after=3,
                stock_version_after=3,
                actor_id=staff.id,
                occurred_at=cancel_time_unaware,
            )
            session.add_all([sm_cancel_lays, sm_cancel_tuna])
            session.flush()
            ctx.stock_movement_ids.extend([sm_cancel_lays.id, sm_cancel_tuna.id])

        # ======================================================================
        # RECONCILIATION PHASE ACROSS ALL ANALYTICS SERVICES ON REAL MYSQL
        # ======================================================================
        period = resolve_sales_period(from_date=target_date, to_date=target_date)

        with Session(migrated_integration_engine) as session:
            # 1. Reconcile Sales Analytics Service
            sales_svc = SalesAnalyticsService()
            summary = sales_svc.summary(session, period=period)

            # Revenue strictly equals Order #1 total (Order #2 CANCELLED is excluded)
            assert summary.revenue_vnd - baseline_sales.revenue_vnd == 62_000
            assert summary.completed_orders - baseline_sales.completed_orders == 1
            assert summary.cancelled_orders - baseline_sales.cancelled_orders == 1
            assert summary.aov_vnd == 62_000

            # 2. Reconcile Product Analytics Service (Top Products)
            product_svc = ProductAnalyticsService()
            top_page = product_svc.top(session, period=period, page=1, page_size=10)

            # Only Coca and TH Milk appear; Lay's and Tuna are excluded
            assert top_page.total == 2
            assert len(top_page.items) == 2

            top_1 = top_page.items[0]
            assert top_1.product_id == prod_coca.id
            assert top_1.sku == prod_coca.sku
            assert top_1.sold_units == 2
            assert top_1.revenue_vnd == 24_000
            assert top_1.quantity == 118

            top_2 = top_page.items[1]
            assert top_2.product_id == prod_milk.id
            assert top_2.sku == prod_milk.sku
            assert top_2.sold_units == 1
            assert top_2.revenue_vnd == 38_000
            assert top_2.quantity == 49

            # 3. Reconcile Product Analytics Service (Slow Moving Products)
            # as_of_utc set to end of test day
            as_of_test = frozen_time_utc + timedelta(hours=2)
            slow_page = product_svc.slow(
                session, as_of_utc=as_of_test, page=1, page_size=20
            )

            # Lay's and Cá ngừ have 0 completed units, quantity > 0, and stocked > 7d
            slow_product_ids = {it.product_id for it in slow_page.items}
            assert prod_lays.id in slow_product_ids
            assert prod_tuna.id in slow_product_ids

            lays_item = next(
                it for it in slow_page.items if it.product_id == prod_lays.id
            )
            assert lays_item.sold_units == 0
            assert lays_item.revenue_vnd == 0
            assert lays_item.quantity == 5

            tuna_item = next(
                it for it in slow_page.items if it.product_id == prod_tuna.id
            )
            assert tuna_item.sold_units == 0
            assert tuna_item.revenue_vnd == 0
            assert tuna_item.quantity == 3

            # 4. Reconcile Dashboard Service (Unified Facade)
            dash_svc = DashboardService()
            dashboard = dash_svc.read(session, period=period)

            # Matches SalesSummary
            assert dashboard.sales.revenue_vnd - baseline_sales.revenue_vnd == 62_000
            assert (
                dashboard.sales.completed_orders - baseline_sales.completed_orders == 1
            )
            assert (
                dashboard.sales.cancelled_orders - baseline_sales.cancelled_orders == 1
            )
            assert dashboard.sales.aov_vnd == 62_000

            # Matches Low Stock Count (Lay's=5, Tuna=3 <= threshold 5)
            # Exactly 2 low stock products added in this run context
            assert dashboard.low_stock_count - baseline_low_stock == 2
            assert len(ctx.stock_movement_ids) == 10

            # Matches Top Products
            top_ids_dash = [p.product_id for p in dashboard.top_products]
            assert prod_coca.id in top_ids_dash
            assert prod_milk.id in top_ids_dash

    finally:
        ctx.cleanup()


# ==============================================================================
# TEST 2: CATALOG PRICE MUTATION PRESERVES HISTORICAL SNAPSHOTS ON MYSQL
# ==============================================================================


def test_catalog_price_mutation_preserves_reconciled_analytics_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Xác nhận cập nhật giá bán trên Product Catalog (Coca 12k->15k, TH 38k->45k)

    sau khi đơn hàng đã COMPLETED KHÔNG làm biến động doanh thu lịch sử (62k)
    hay doanh thu từng sản phẩm trong Top Products.
    """
    ctx = TestRunContext(migrated_integration_engine, "cat_mut")
    _ensure_shared_admin(migrated_integration_engine)

    # Deterministic frozen timestamp (UTC + VN) - distinct date 2026-10-16
    frozen_time_utc = datetime(2026, 10, 16, 4, 0, tzinfo=UTC)
    target_date = frozen_time_utc.astimezone(VN_TZ).date()
    now_unaware = frozen_time_utc.astimezone(UTC).replace(tzinfo=None)

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            staff = _create_test_staff(
                session, now_unaware=now_unaware, prefix=ctx.prefix
            )
            ctx.user_ids.append(staff.id)

            category = Category(
                name=f"{ctx.prefix}SnapshotCat",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(category)
            session.flush()
            ctx.category_ids.append(category.id)

            prod_coca = Product(
                sku=f"{ctx.prefix}DRK-COCA-330",
                name="Nước ngọt Coca Cola 330ml",
                category_id=category.id,
                sale_price_vnd=12_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            prod_milk = Product(
                sku=f"{ctx.prefix}DRK-MILK-TH1L",
                name="Sữa tươi tiệt trùng TH True Milk 1L",
                category_id=category.id,
                sale_price_vnd=38_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add_all([prod_coca, prod_milk])
            session.flush()
            ctx.product_ids.extend([prod_coca.id, prod_milk.id])

            inv_coca = Inventory(
                product_id=prod_coca.id,
                quantity=100,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            inv_milk = Inventory(
                product_id=prod_milk.id,
                quantity=100,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add_all([inv_coca, inv_milk])
            session.flush()

            # Create Order #1 at original prices (62,000 VND)
            order = Order(
                status=OrderStatus.COMPLETED.value,
                total_vnd=62_000,
                created_by=staff.id,
                sold_at=now_unaware,
                cancelled_by=None,
                cancelled_at=None,
                cancel_reason=None,
            )
            session.add(order)
            session.flush()
            ctx.order_ids.append(order.id)

            item_coca = OrderItem(
                order_id=order.id,
                product_id=prod_coca.id,
                sku_snapshot=prod_coca.sku,
                product_name_snapshot=prod_coca.name,
                quantity=2,
                unit_price_vnd=12_000,
                line_total_vnd=24_000,
            )
            item_milk = OrderItem(
                order_id=order.id,
                product_id=prod_milk.id,
                sku_snapshot=prod_milk.sku,
                product_name_snapshot=prod_milk.name,
                quantity=1,
                unit_price_vnd=38_000,
                line_total_vnd=38_000,
            )
            session.add_all([item_coca, item_milk])
            session.flush()

        # Step 2: Now Admin mutates catalog prices (Coca -> 15k, Sữa TH -> 45k)
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            coca_db = session.get(Product, prod_coca.id)
            milk_db = session.get(Product, prod_milk.id)
            assert coca_db is not None and milk_db is not None

            coca_db.sale_price_vnd = 15_000
            milk_db.sale_price_vnd = 45_000

        # Step 3: Verify that historical analytics is 100% invariant
        period = resolve_sales_period(from_date=target_date, to_date=target_date)
        with Session(migrated_integration_engine) as session:
            # Sales Analytics must still be exactly 62,000 VND
            sales_svc = SalesAnalyticsService()
            summary = sales_svc.summary(session, period=period)
            assert summary.revenue_vnd == 62_000
            assert summary.revenue_vnd != (2 * 15_000 + 1 * 45_000)

            # Product Analytics top must retain historical line_total_vnd
            product_svc = ProductAnalyticsService()
            top_page = product_svc.top(session, period=period, page=1, page_size=10)
            coca_top = next(p for p in top_page.items if p.product_id == prod_coca.id)
            milk_top = next(p for p in top_page.items if p.product_id == prod_milk.id)
            assert coca_top.revenue_vnd == 24_000
            assert milk_top.revenue_vnd == 38_000

    finally:
        ctx.cleanup()


# ==============================================================================
# TEST 3: SAFE TEARDOWN & IDEMPOTENT CLEANUP ISOLATION ON MYSQL
# ==============================================================================


def test_reconciliation_cleanup_isolation_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Xác nhận TestRunContext.cleanup() có tính cô lập và idempotent:

    - Xóa Run A không làm mất dữ liệu Run B (User, Category, Supplier, Product).
    - Gọi cleanup() 2 lần liên tiếp không gây Exception (idempotency).
    - Tuyệt đối bảo toàn tài khoản Shared ADMIN (admin_slot == 1).
    """
    ctx_a = TestRunContext(migrated_integration_engine, "run_a")
    ctx_b = TestRunContext(migrated_integration_engine, "run_b")
    admin_id = _ensure_shared_admin(migrated_integration_engine)

    now_unaware = datetime(2026, 10, 17, 5, 0, 0)
    idem_b_key = uuid4().bytes + uuid4().bytes
    idem_b_req = uuid4().bytes + uuid4().bytes
    staff_b_id: int | None = None

    try:
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            # Seed Run A (Staff, Category, Supplier, Product)
            staff_a = _create_test_staff(
                session, now_unaware=now_unaware, prefix=ctx_a.prefix
            )
            ctx_a.user_ids.append(staff_a.id)

            cat_a = Category(
                name=f"{ctx_a.prefix}CatA",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(cat_a)
            session.flush()
            ctx_a.category_ids.append(cat_a.id)

            sup_a = Supplier(
                name=f"{ctx_a.prefix}SupA",
                contact_phone="+84900000001",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(sup_a)
            session.flush()
            ctx_a.supplier_ids.append(sup_a.id)

            prod_a = Product(
                sku=f"{ctx_a.prefix}PRD-A",
                name="Sản phẩm Run A",
                category_id=cat_a.id,
                sale_price_vnd=20_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_a)
            session.flush()
            ctx_a.product_ids.append(prod_a.id)

            # Seed Run B (Staff, Category, Supplier, Product, IdempotencyRecord)
            staff_b = _create_test_staff(
                session, now_unaware=now_unaware, prefix=ctx_b.prefix
            )
            staff_b_id = staff_b.id
            ctx_b.user_ids.append(staff_b.id)

            cat_b = Category(
                name=f"{ctx_b.prefix}CatB",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(cat_b)
            session.flush()
            ctx_b.category_ids.append(cat_b.id)

            sup_b = Supplier(
                name=f"{ctx_b.prefix}SupB",
                contact_phone="+84900000002",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(sup_b)
            session.flush()
            ctx_b.supplier_ids.append(sup_b.id)

            prod_b = Product(
                sku=f"{ctx_b.prefix}PRD-B",
                name="Sản phẩm Run B",
                category_id=cat_b.id,
                sale_price_vnd=30_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_b)
            session.flush()
            ctx_b.product_ids.append(prod_b.id)

            idem_b = IdempotencyRecord(
                user_id=staff_b.id,
                operation="CHECKOUT",
                key_digest=idem_b_key,
                request_digest=idem_b_req,
                response_status=200,
                response_body={"ok": True},
                completed_at=now_unaware,
                created_at=now_unaware,
                expires_at=now_unaware,
            )
            session.add(idem_b)

        # 1. First cleanup of Run A
        ctx_a.cleanup()

        # 2. Second cleanup of Run A (Idempotency check: 0 queries, 0 exceptions)
        ctx_a.cleanup()

        # 3. Verify Run A is completely gone, but Run B and Shared ADMIN remain intact
        with Session(migrated_integration_engine) as session:
            assert session.get(Category, cat_a.id) is None
            assert session.get(Supplier, sup_a.id) is None
            assert session.get(Product, prod_a.id) is None
            assert session.get(User, staff_a.id) is None

            # Run B is completely preserved including its IdempotencyRecord
            assert session.get(Category, cat_b.id) is not None
            assert session.get(Supplier, sup_b.id) is not None
            assert session.get(Product, prod_b.id) is not None
            assert session.get(User, staff_b.id) is not None
            persisted_idem_b = session.get(
                IdempotencyRecord, (staff_b.id, "CHECKOUT", idem_b_key)
            )
            assert persisted_idem_b is not None
            assert persisted_idem_b.request_digest == idem_b_req

            # Shared ADMIN is strictly preserved
            admin = session.scalar(select(User).where(User.admin_slot == 1))
            assert admin is not None
            assert admin.id == admin_id

    finally:
        # Explicitly clean up Run B's IdempotencyRecord before ctx_b cleanup
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            if staff_b_id is not None:
                session.execute(
                    delete(IdempotencyRecord).where(
                        IdempotencyRecord.user_id == staff_b_id,
                        IdempotencyRecord.operation == "CHECKOUT",
                        IdempotencyRecord.key_digest == idem_b_key,
                    )
                )
        ctx_a.cleanup()
        ctx_b.cleanup()


# ==============================================================================
# TEST 4: FAIL-CLOSED ROLLBACK ON EXTERNAL REFERENCE VIOLATION ON MYSQL
# ==============================================================================


def test_reconciliation_cleanup_fail_closed_on_external_reference_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Fail-closed rollback: Nếu có OrderItem từ bên ngoài reference product của Run A,
    cleanup() của Run A BẮT BUỘC raise RuntimeError và rollback toàn bộ transaction
    (không partial deletion: product, inventory và category của Run A vẫn nguyên vẹn).
    """
    ctx_a = TestRunContext(migrated_integration_engine, "fail_close")
    _ensure_shared_admin(migrated_integration_engine)
    now_unaware = datetime(2026, 10, 18, 6, 0, 0)

    ext_order_id: int | None = None
    ext_staff_id: int | None = None

    try:
        # Step 1: Run A creates category, product, and inventory
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            cat_a = Category(
                name=f"{ctx_a.prefix}CatA",
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(cat_a)
            session.flush()
            ctx_a.category_ids.append(cat_a.id)

            prod_a = Product(
                sku=f"{ctx_a.prefix}PRD-FAILCLOSE",
                name="Sản phẩm kiểm thử fail-closed",
                category_id=cat_a.id,
                sale_price_vnd=50_000,
                status=CatalogStatus.ACTIVE.value,
                created_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(prod_a)
            session.flush()
            ctx_a.product_ids.append(prod_a.id)

            inv_a = Inventory(
                product_id=prod_a.id,
                quantity=10,
                stock_version=1,
                first_stocked_at=now_unaware,
                updated_at=now_unaware,
            )
            session.add(inv_a)
            session.flush()

        # Step 2: External actor creates Order + OrderItem referencing prod_a
        # Note: this external order is NOT tracked in ctx_a.order_ids!
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            ext_staff = _create_test_staff(
                session, now_unaware=now_unaware, prefix="T04AC15_ext_"
            )
            ext_staff_id = ext_staff.id

            ext_order = Order(
                status=OrderStatus.COMPLETED.value,
                total_vnd=50_000,
                created_by=ext_staff.id,
                sold_at=now_unaware,
                cancelled_by=None,
                cancelled_at=None,
                cancel_reason=None,
            )
            session.add(ext_order)
            session.flush()
            ext_order_id = ext_order.id

            ext_item = OrderItem(
                order_id=ext_order.id,
                product_id=prod_a.id,
                sku_snapshot=prod_a.sku,
                product_name_snapshot=prod_a.name,
                quantity=1,
                unit_price_vnd=50_000,
                line_total_vnd=50_000,
            )
            session.add(ext_item)
            session.flush()

        # Step 3: Run A attempts cleanup -> MUST raise RuntimeError (fail-closed)
        with pytest.raises(
            RuntimeError,
            match=(
                "Fail-closed cleanup: tracked product\\(s\\) "
                "still referenced by external OrderItem"
            ),
        ):
            ctx_a.cleanup()

        # Step 4: Verify transaction rollback: Run A entities exist (no partial delete)
        with Session(migrated_integration_engine) as session:
            assert session.get(Product, prod_a.id) is not None
            assert session.get(Inventory, prod_a.id) is not None
            assert session.get(Category, cat_a.id) is not None

        # Step 5: Clean up the external reference first
        with Session(migrated_integration_engine) as session, session.begin():
            if ext_order_id is not None:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id == ext_order_id)
                )
                session.execute(delete(Order).where(Order.id == ext_order_id))
            if ext_staff_id is not None:
                session.execute(delete(User).where(User.id == ext_staff_id))
            ext_order_id = None
            ext_staff_id = None

        # Step 6: Now Run A cleanup succeeds cleanly and removes everything
        ctx_a.cleanup()
        with Session(migrated_integration_engine) as session:
            assert session.get(Product, prod_a.id) is None
            assert session.get(Inventory, prod_a.id) is None
            assert session.get(Category, cat_a.id) is None

    finally:
        # Fallback safety in case of test assertion failure
        with Session(migrated_integration_engine) as session, session.begin():
            if ext_order_id is not None:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id == ext_order_id)
                )
                session.execute(delete(Order).where(Order.id == ext_order_id))
            if ext_staff_id is not None:
                session.execute(delete(User).where(User.id == ext_staff_id))
        ctx_a.cleanup()


# ==============================================================================
# TEST 5: SHARED ADMIN IMMUNITY DEFENSE-IN-DEPTH ON MYSQL
# ==============================================================================


def test_reconciliation_cleanup_shared_admin_immunity_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Bảo vệ Shared ADMIN & IdempotencyRecord: Ngay cả khi admin_id bị đưa
    nhầm vào ctx.user_ids, cleanup() TUYỆT ĐỐI KHÔNG xóa tài khoản Shared ADMIN
    (admin_slot == 1) và KHÔNG xóa bất kỳ IdempotencyRecord nào của Shared ADMIN.
    """
    admin_id = _ensure_shared_admin(migrated_integration_engine)
    unique_key_digest = uuid4().bytes + uuid4().bytes  # 32 bytes
    unique_req_digest = uuid4().bytes + uuid4().bytes  # 32 bytes
    now = datetime(2026, 11, 20, 10, 0, 0)
    op = "CHECKOUT"

    # Step 1: Create a valid IdempotencyRecord belonging to Shared ADMIN
    with (
        Session(migrated_integration_engine, expire_on_commit=False) as session,
        session.begin(),
    ):
        admin_idem = IdempotencyRecord(
            user_id=admin_id,
            operation=op,
            key_digest=unique_key_digest,
            request_digest=unique_req_digest,
            response_status=200,
            response_body={"ok": True},
            completed_at=now,
            created_at=now,
            expires_at=now,
        )
        session.add(admin_idem)

    try:
        ctx_adm = TestRunContext(migrated_integration_engine, "adm_imm")

        # Step 2: Deliberately put admin_id in user_ids to test defense-in-depth
        ctx_adm.user_ids.append(admin_id)

        # Step 3: cleanup() must NOT delete Shared Admin or IdempotencyRecord
        ctx_adm.cleanup()

        with Session(migrated_integration_engine) as session:
            # Shared ADMIN user is strictly preserved
            admin = session.scalar(select(User).where(User.admin_slot == 1))
            assert admin is not None
            assert admin.id == admin_id

            # Shared ADMIN IdempotencyRecord is untouched
            persisted_idem = session.get(
                IdempotencyRecord, (admin_id, op, unique_key_digest)
            )
            assert persisted_idem is not None
            assert persisted_idem.request_digest == unique_req_digest
    finally:
        # Step 4: Clean up test's IdempotencyRecord by exact composite key
        with (
            Session(migrated_integration_engine, expire_on_commit=False) as session,
            session.begin(),
        ):
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == admin_id,
                    IdempotencyRecord.operation == op,
                    IdempotencyRecord.key_digest == unique_key_digest,
                )
            )
