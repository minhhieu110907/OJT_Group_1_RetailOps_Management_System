"""MySQL integration tests for Low-Stock alerts and Stock Movement history (T04A78E)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import InvalidStateError
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_current_active_user,
    get_current_principal,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.inventory.models import (
    InventoryAdjustment,
    MovementKind,
    StockMovement,
)
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    LowStockPage,
    StockMovementAdminPage,
    StockMovementAdminRead,
    StockMovementPage,
    StockMovementRead,
)
from app.modules.inventory.service import InventoryQueryService, InventoryService
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import (
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from app.modules.sales.models import Order, OrderItem
from app.modules.sales.schemas import CheckoutLine
from app.modules.sales.service import CheckoutService, OrderService
from app.modules.suppliers.models import Supplier, SupplierStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration

TEST_PREFIX = "T04A78E_"

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


def _unique_token(suffix: str) -> str:
    return f"{TEST_PREFIX}{suffix}_{uuid4().hex[:8]}"


_created_admin_id: int | None = None


@pytest.fixture(autouse=True)
def clean_test_rows(migrated_integration_engine: Engine) -> Iterator[None]:
    """Tear down all test rows created under TEST_PREFIX after each test."""
    global _created_admin_id
    _created_admin_id = None
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{TEST_PREFIX}%"))
            )
        )
        if product_ids:
            session.execute(
                delete(StockMovement).where(StockMovement.product_id.in_(product_ids))
            )
            order_ids = list(
                session.scalars(
                    select(OrderItem.order_id).where(
                        OrderItem.product_id.in_(product_ids)
                    )
                )
            )
            if order_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.order_id.in_(order_ids))
                )
                session.execute(delete(Order).where(Order.id.in_(order_ids)))
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.product_id.in_(product_ids)
                )
            )
            session.execute(
                delete(InventoryAdjustment).where(
                    InventoryAdjustment.product_id.in_(product_ids)
                )
            )
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))

        receipt_ids = list(
            session.scalars(
                select(PurchaseReceipt.id)
                .join(Supplier, PurchaseReceipt.supplier_id == Supplier.id)
                .where(Supplier.name.like(f"{TEST_PREFIX}%"))
            )
        )
        if receipt_ids:
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id.in_(receipt_ids)
                )
            )
            session.execute(
                delete(PurchaseReceipt).where(PurchaseReceipt.id.in_(receipt_ids))
            )

        session.execute(delete(Supplier).where(Supplier.name.like(f"{TEST_PREFIX}%")))
        session.execute(delete(Category).where(Category.name.like(f"{TEST_PREFIX}%")))
        test_user_ids = list(
            session.scalars(
                select(User.id).where(
                    User.email_normalized.like(f"{TEST_PREFIX.lower()}%")
                )
            )
        )
        if test_user_ids:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.user_id.in_(test_user_ids)
                )
            )
        if _created_admin_id is not None:
            session.execute(delete(User).where(User.id == _created_admin_id))
            _created_admin_id = None
        session.execute(
            delete(User).where(
                User.admin_slot.is_(None),
                User.email_normalized.like(f"{TEST_PREFIX}%"),
            )
        )


def _get_or_create_admin(session: Session) -> User:
    """Retrieve existing seeded admin or create an active admin with admin_slot=1."""
    global _created_admin_id
    admin = session.scalar(select(User).where(User.admin_slot == 1))
    if admin is not None:
        return admin
    now = datetime.now(UTC).replace(tzinfo=None)
    admin = User(
        email_normalized=f"{TEST_PREFIX.lower()}admin@example.com",
        password_hash="$2b$04$test.hash.inventory.movements.admin",
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=1,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(admin)
    session.flush()
    _created_admin_id = int(admin.id)
    return admin


def _create_staff(session: Session, email_suffix: str) -> User:
    """Create an active staff user with admin_slot=None."""
    now = datetime.now(UTC).replace(tzinfo=None)
    staff = User(
        email_normalized=f"{TEST_PREFIX}{email_suffix}_{uuid4().hex[:8]}@example.com",
        password_hash="$2b$04$test.hash.inventory.movements.staff",
        role=UserRole.STAFF.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(staff)
    session.flush()
    return staff


def _create_category(session: Session) -> Category:
    now = datetime.now(UTC).replace(tzinfo=None)
    category = Category(
        name=_unique_token("CAT"),
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(category)
    session.flush()
    return category


def _create_supplier(session: Session) -> Supplier:
    now = datetime.now(UTC).replace(tzinfo=None)
    supplier = Supplier(
        name=_unique_token("SUP"),
        contact_email=f"{_unique_token('sup').lower()}@example.com",
        contact_phone=f"+8490{uuid4().hex[:7]}",
        status=SupplierStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add(supplier)
    session.flush()
    return supplier


def _create_product_with_inventory(
    session: Session,
    category_id: int,
    sku_suffix: str,
    quantity: int,
    status: CatalogStatus = CatalogStatus.ACTIVE,
) -> tuple[Product, Inventory]:
    now = datetime.now(UTC).replace(tzinfo=None)
    product = Product(
        sku=f"{TEST_PREFIX}{sku_suffix}",
        name=f"Product {sku_suffix}",
        category_id=category_id,
        status=status.value,
        sale_price_vnd=100_000,
        created_at=now,
        updated_at=now,
    )
    session.add(product)
    session.flush()

    inventory = Inventory(
        product_id=product.id,
        quantity=quantity,
        stock_version=1 if quantity > 0 else 0,
        first_stocked_at=now if quantity > 0 else None,
        updated_at=now,
    )
    session.add(inventory)
    session.flush()
    return product, inventory


def _seed_test_dataset(session: Session) -> dict[str, object]:
    """Seed comprehensive dataset with products, movements, and adjustments."""
    admin = _get_or_create_admin(session)
    staff = _create_staff(session, "staff")
    category = _create_category(session)
    supplier = _create_supplier(session)

    # Products with different stock and status
    p1, inv1 = _create_product_with_inventory(
        session, category.id, "P1_QTY2", quantity=2, status=CatalogStatus.ACTIVE
    )
    p2, inv2 = _create_product_with_inventory(
        session, category.id, "P2_QTY5", quantity=5, status=CatalogStatus.ACTIVE
    )
    p3, inv3 = _create_product_with_inventory(
        session, category.id, "P3_QTY6", quantity=6, status=CatalogStatus.ACTIVE
    )
    p4, inv4 = _create_product_with_inventory(
        session, category.id, "P4_INACT", quantity=1, status=CatalogStatus.INACTIVE
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    t1 = now - timedelta(hours=3)
    t2 = now - timedelta(hours=2)
    t3 = now - timedelta(hours=1)

    # 1. Purchase receipt + Item for PURCHASE_CONFIRM movement
    receipt = PurchaseReceipt(
        supplier_id=supplier.id,
        supplier_name_snapshot=supplier.name,
        status="CONFIRMED",
        draft_version=1,
        total_vnd=500_000,
        created_by=admin.id,
        closed_by=admin.id,
        created_at=t1,
        updated_at=t1,
        closed_at=t1,
    )
    session.add(receipt)
    session.flush()

    receipt_item = PurchaseReceiptItem(
        receipt_id=receipt.id,
        product_id=p1.id,
        sku_snapshot=p1.sku,
        product_name_snapshot=p1.name,
        quantity=10,
        unit_cost_vnd=50_000,
        line_total_vnd=500_000,
    )
    session.add(receipt_item)
    session.flush()

    m1 = StockMovement(
        product_id=p1.id,
        actor_id=admin.id,
        kind=MovementKind.PURCHASE_CONFIRM.value,
        receipt_id=receipt.id,
        sku_snapshot=p1.sku,
        quantity_before=0,
        quantity_after=10,
        stock_version_after=1,
        occurred_at=t1,
    )
    session.add(m1)
    session.flush()

    # 2. Order + OrderItem for SALE movement
    order = Order(
        status="COMPLETED",
        total_vnd=400_000,
        created_by=staff.id,
        sold_at=t2,
    )
    session.add(order)
    session.flush()

    order_item = OrderItem(
        order_id=order.id,
        product_id=p1.id,
        sku_snapshot=p1.sku,
        product_name_snapshot=p1.name,
        quantity=5,
        unit_price_vnd=80_000,
        line_total_vnd=400_000,
    )
    session.add(order_item)
    session.flush()

    m2 = StockMovement(
        product_id=p1.id,
        actor_id=staff.id,
        kind=MovementKind.SALE.value,
        order_id=order.id,
        sku_snapshot=p1.sku,
        quantity_before=10,
        quantity_after=5,
        stock_version_after=2,
        occurred_at=t2,
    )
    session.add(m2)
    session.flush()

    # 3. InventoryAdjustment for ADJUSTMENT movement
    adjustment = InventoryAdjustment(
        product_id=p1.id,
        actor_id=admin.id,
        reason="Found damaged items during audit",
        quantity_before=5,
        counted_quantity=2,
        version_before=2,
        created_at=t3,
    )
    session.add(adjustment)
    session.flush()

    m3 = StockMovement(
        product_id=p1.id,
        actor_id=admin.id,
        kind=MovementKind.ADJUSTMENT.value,
        adjustment_id=adjustment.id,
        sku_snapshot=p1.sku,
        quantity_before=5,
        quantity_after=2,
        stock_version_after=3,
        occurred_at=t3,
    )
    session.add(m3)
    session.flush()

    # 4. Movement on p2 for filter testing
    receipt2 = PurchaseReceipt(
        supplier_id=supplier.id,
        supplier_name_snapshot=supplier.name,
        status="CONFIRMED",
        draft_version=1,
        total_vnd=250_000,
        created_by=admin.id,
        closed_by=admin.id,
        created_at=t1,
        updated_at=t1,
        closed_at=t1,
    )
    session.add(receipt2)
    session.flush()

    receipt_item2 = PurchaseReceiptItem(
        receipt_id=receipt2.id,
        product_id=p2.id,
        sku_snapshot=p2.sku,
        product_name_snapshot=p2.name,
        quantity=5,
        unit_cost_vnd=50_000,
        line_total_vnd=250_000,
    )
    session.add(receipt_item2)
    session.flush()

    m4 = StockMovement(
        product_id=p2.id,
        actor_id=admin.id,
        kind=MovementKind.PURCHASE_CONFIRM.value,
        receipt_id=receipt2.id,
        sku_snapshot=p2.sku,
        quantity_before=0,
        quantity_after=5,
        stock_version_after=1,
        occurred_at=t1,
    )
    session.add(m4)
    session.flush()

    p1_id = int(p1.id)
    p2_id = int(p2.id)
    p3_id = int(p3.id)
    p4_id = int(p4.id)
    admin_id = int(admin.id)
    staff_id = int(staff.id)

    session.commit()

    return {
        "admin_id": admin_id,
        "staff_id": staff_id,
        "category_id": int(category.id),
        "p1_id": p1_id,
        "p2_id": p2_id,
        "p3_id": p3_id,
        "p4_id": p4_id,
    }


def test_stock_movements_sorting_occurred_at_desc_id_desc(
    migrated_integration_engine: Engine,
) -> None:
    """Ensure movements are ordered by occurred_at DESC, id DESC."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()

        p1_id = data["p1_id"]
        page = service.list_stock_movements_admin(
            session=session,
            page=1,
            page_size=20,
            product_id=p1_id,
        )

        assert isinstance(page, StockMovementAdminPage)
        assert page.total == 3
        assert len(page.items) == 3

        # Verify ordering: t3 (ADJUSTMENT) -> t2 (SALE) -> t1 (PURCHASE_CONFIRM)
        items = page.items
        assert items[0].kind == "ADJUSTMENT"
        assert items[1].kind == "SALE"
        assert items[2].kind == "PURCHASE_CONFIRM"
        assert items[0].occurred_at >= items[1].occurred_at
        assert items[1].occurred_at >= items[2].occurred_at


def test_stock_movements_query_filters(
    migrated_integration_engine: Engine,
) -> None:
    """Verify stock movements filtering by product_id and kind."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()

        p1_id = data["p1_id"]
        p2_id = data["p2_id"]

        # Filter by product_id
        page_p2 = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, product_id=p2_id
        )
        assert page_p2.total == 1
        assert page_p2.items[0].product_id == p2_id

        # Filter by kind = ADJUSTMENT
        page_adj = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, kind="ADJUSTMENT"
        )
        for item in page_adj.items:
            assert item.kind == "ADJUSTMENT"
            if item.product_id == p1_id:
                assert item.adjustment_reason == "Found damaged items during audit"

        # Filter by both product_id and kind
        page_p1_sale = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, product_id=p1_id, kind="SALE"
        )
        assert page_p1_sale.total == 1
        assert page_p1_sale.items[0].kind == "SALE"
        assert page_p1_sale.items[0].product_id == p1_id


def test_stock_movements_rbac_staff_and_admin(
    migrated_integration_engine: Engine,
) -> None:
    """Verify field-level RBAC: STAFF hides audit and prices, ADMIN gets audit."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()
        p1_id = data["p1_id"]

        # 1. STAFF query
        staff_page = service.list_stock_movements_staff(
            session=session, page=1, page_size=20, product_id=p1_id
        )
        assert isinstance(staff_page, StockMovementPage)
        for item in staff_page.items:
            assert isinstance(item, StockMovementRead)
            item_dict = item.model_dump()
            assert "actor_id" not in item_dict
            assert "adjustment_reason" not in item_dict
            assert "sale_price_vnd" not in item_dict
            assert "cost_price_vnd" not in item_dict
            assert "unit_cost_vnd" not in item_dict

        # 2. ADMIN query
        admin_page = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, product_id=p1_id
        )
        assert isinstance(admin_page, StockMovementAdminPage)
        assert admin_page.total == 3

        # Find the adjustment movement in admin results
        adj_item = next(i for i in admin_page.items if i.kind == "ADJUSTMENT")
        assert isinstance(adj_item, StockMovementAdminRead)
        assert adj_item.actor_id is not None
        assert adj_item.adjustment_reason == "Found damaged items during audit"

        # Verify no price fields are exposed even to ADMIN
        admin_dict = adj_item.model_dump()
        assert "sale_price_vnd" not in admin_dict
        assert "cost_price_vnd" not in admin_dict
        assert "unit_cost_vnd" not in admin_dict


def test_inventory_low_stock_filters_and_ordering(
    migrated_integration_engine: Engine,
) -> None:
    """Verify /inventory/low-stock only returns active products with qty <= 5."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()

        p1_id = data["p1_id"]  # qty=2, ACTIVE
        p2_id = data["p2_id"]  # qty=5, ACTIVE
        p3_id = data["p3_id"]  # qty=6, ACTIVE (excluded)
        p4_id = data["p4_id"]  # qty=1, INACTIVE (excluded)

        low_stock_page = service.get_low_stock(
            session=session,
            page=1,
            page_size=20,
            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        )

        assert isinstance(low_stock_page, LowStockPage)
        returned_ids = [item.product_id for item in low_stock_page.items]

        # P1 and P2 MUST be returned
        assert p1_id in returned_ids
        assert p2_id in returned_ids

        # P3 (qty=6 > 5) and P4 (INACTIVE) MUST NOT be returned
        assert p3_id not in returned_ids
        assert p4_id not in returned_ids

        # Verify sorting: quantity ASC, product_id ASC
        filtered_items = [
            item for item in low_stock_page.items if item.product_id in (p1_id, p2_id)
        ]
        assert len(filtered_items) == 2
        assert filtered_items[0].product_id == p1_id
        assert filtered_items[0].quantity == 2
        assert filtered_items[1].product_id == p2_id
        assert filtered_items[1].quantity == 5

        # Verify each item threshold is 5
        for item in filtered_items:
            assert item.threshold == DEFAULT_LOW_STOCK_THRESHOLD


@pytest.mark.anyio
async def test_inventory_low_stock_route_precedence(
    migrated_integration_engine: Engine,
) -> None:
    """Verify GET /inventory/low-stock resolves correctly without 422 collision."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        staff_id = data["staff_id"]
        p1_id = data["p1_id"]

    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        cors_origins="http://127.0.0.1:5173",
    )
    app = create_app(settings)

    def override_get_db() -> Iterator[Session]:
        with Session(migrated_integration_engine) as s:
            yield s

    now = datetime.now(UTC).replace(tzinfo=None)
    mock_staff = User(
        id=staff_id,
        email_normalized="mock_staff@example.com",
        password_hash="$2b$04$test.mock.staff.hash",
        role=UserRole.STAFF.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_active_user] = lambda: mock_staff
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user=mock_staff, session_id=uuid4()
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Low-stock endpoint returns 200 (not 422 from {product_id} integer parser)
        res = await client.get("/api/v1/inventory/low-stock")
        assert res.status_code == 200
        body = res.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] >= 2

        # 2. Product ID endpoint still functions correctly
        res_prod = await client.get(f"/api/v1/inventory/{p1_id}")
        assert res_prod.status_code == 200
        assert res_prod.json()["product_id"] == p1_id


def test_stock_movements_order_cancel_restores_stock_and_creates_movement(
    migrated_integration_engine: Engine,
) -> None:
    """Verify order cancellation restores stock and records ORDER_CANCEL (PR #52)."""
    now = datetime.now(UTC)
    now_unaware = now.replace(tzinfo=None)

    with Session(migrated_integration_engine) as session, session.begin():
        staff = User(
            email_normalized=f"{TEST_PREFIX.lower()}staff_cancel_{uuid4().hex[:6]}@example.com",
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
        staff_id = int(staff.id)

        category = Category(
            name=_unique_token("CancelCat"),
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(category)
        session.flush()

        product = Product(
            sku=_unique_token("CAN-SKU"),
            name="Cancel Test Product",
            category_id=category.id,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=50_000,
            created_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(product)
        session.flush()
        product_id = int(product.id)
        product_sku = str(product.sku)

        # Initial inventory: quantity=10, stock_version=1
        inv = Inventory(
            product_id=product_id,
            quantity=10,
            stock_version=1,
            first_stocked_at=now_unaware,
            updated_at=now_unaware,
        )
        session.add(inv)

    inv_mutation_service = InventoryService()
    checkout_service = CheckoutService(
        inv_mutation_service,
        clock=lambda: now,
    )
    order_service = OrderService(
        inv_mutation_service,
        clock=lambda: now + timedelta(minutes=2),
    )

    # 1. Complete an order for quantity=3
    checkout_key = f"{TEST_PREFIX}checkout_key_{uuid4().hex[:6]}"
    with Session(migrated_integration_engine) as session:
        order = checkout_service.checkout(
            session,
            actor_id=staff_id,
            idempotency_key=checkout_key,
            items=[
                CheckoutLine(
                    product_id=product_id,
                    quantity=3,
                    viewed_unit_price_vnd=50_000,
                )
            ],
        )
        order_id = int(order.id)

    # Verify inventory after sale: quantity=7, stock_version=2
    with Session(migrated_integration_engine) as session:
        inv_after_sale = session.get(Inventory, product_id)
        assert inv_after_sale is not None
        assert inv_after_sale.quantity == 7
        assert inv_after_sale.stock_version == 2

    # 2. Cancel order via OrderService
    cancel_key = f"{TEST_PREFIX}cancel_key_{uuid4().hex[:6]}"
    with Session(migrated_integration_engine) as session:
        cancelled_order = order_service.cancel(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Customer requested order cancellation",
            idempotency_key=cancel_key,
        )
        assert cancelled_order.status == "CANCELLED"
        assert cancelled_order.cancelled_by == staff_id
        assert cancelled_order.cancel_reason == "Customer requested order cancellation"

    # 3. Verify stock is restored precisely: quantity_after (10) > quantity_before (7)
    with Session(migrated_integration_engine) as session:
        inv_after_cancel = session.get(Inventory, product_id)
        assert inv_after_cancel is not None
        assert inv_after_cancel.quantity == 10
        assert inv_after_cancel.stock_version == 3

        # Verify stock_movements table directly
        movements = list(
            session.scalars(
                select(StockMovement)
                .where(StockMovement.product_id == product_id)
                .order_by(StockMovement.id.asc())
            )
        )
        assert len(movements) == 2

        sale_mv = movements[0]
        assert sale_mv.kind == MovementKind.SALE.value
        assert sale_mv.quantity_before == 10
        assert sale_mv.quantity_after == 7
        assert sale_mv.stock_version_after == 2
        assert sale_mv.order_id == order_id

        cancel_mv = movements[1]
        assert cancel_mv.kind == MovementKind.ORDER_CANCEL.value
        assert cancel_mv.quantity_before == 7
        assert cancel_mv.quantity_after == 10
        assert cancel_mv.stock_version_after == 3
        assert cancel_mv.order_id == order_id
        assert cancel_mv.sku_snapshot == product_sku

    # 4. Check query service projections and filtering (GET /stock-movements query)
    query_service = InventoryQueryService()
    with Session(migrated_integration_engine) as session:
        # Filter kind=ORDER_CANCEL for admin
        cancel_page = query_service.list_stock_movements_admin(
            session=session,
            page=1,
            page_size=20,
            product_id=product_id,
            kind="ORDER_CANCEL",
        )
        assert cancel_page.total == 1
        assert len(cancel_page.items) == 1
        mv_admin = cancel_page.items[0]
        assert isinstance(mv_admin, StockMovementAdminRead)
        assert mv_admin.kind == "ORDER_CANCEL"
        assert mv_admin.reference_id == order_id
        assert mv_admin.actor_id == staff_id
        assert mv_admin.quantity_before == 7
        assert mv_admin.quantity_after == 10
        assert mv_admin.stock_version_after == 3
        assert not hasattr(mv_admin, "cost_price_vnd")
        assert not hasattr(mv_admin, "unit_price")

        # Staff projection: actor_id and adjustment_reason are forbidden/omitted
        staff_page = query_service.list_stock_movements_staff(
            session=session,
            page=1,
            page_size=20,
            product_id=product_id,
            kind="ORDER_CANCEL",
        )
        assert staff_page.total == 1
        mv_staff = staff_page.items[0]
        assert isinstance(mv_staff, StockMovementRead)
        assert mv_staff.kind == "ORDER_CANCEL"
        assert mv_staff.reference_id == order_id
        assert mv_staff.quantity_before == 7
        assert mv_staff.quantity_after == 10
        assert not hasattr(mv_staff, "actor_id")
        assert not hasattr(mv_staff, "adjustment_reason")
        assert not hasattr(mv_staff, "cost_price_vnd")

    # 5. Idempotency verification: replay cancel with same key
    with Session(migrated_integration_engine) as session:
        replayed = order_service.cancel(
            session,
            actor_id=staff_id,
            actor_role="STAFF",
            order_id=order_id,
            reason="Customer requested order cancellation",
            idempotency_key=cancel_key,
        )
        assert replayed.status == "CANCELLED"
        # Verify no double stock restore
        inv_recheck = session.get(Inventory, product_id)
        assert inv_recheck is not None and inv_recheck.quantity == 10
        cancel_mv_count = session.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.product_id == product_id,
                StockMovement.kind == "ORDER_CANCEL",
            )
        )
        assert cancel_mv_count == 1

    # 6. Conflict verification: cancel with different key raises InvalidStateError
    diff_key = f"{TEST_PREFIX}cancel_key_diff_{uuid4().hex[:6]}"
    with Session(migrated_integration_engine) as session:
        with pytest.raises(InvalidStateError):
            order_service.cancel(
                session,
                actor_id=staff_id,
                actor_role="STAFF",
                order_id=order_id,
                reason="Duplicate cancel attempt",
                idempotency_key=diff_key,
            )
        # Quantity still 10, movements still 1
        inv_final = session.get(Inventory, product_id)
        assert inv_final is not None and inv_final.quantity == 10
        cancel_mv_count_final = session.scalar(
            select(func.count(StockMovement.id)).where(
                StockMovement.product_id == product_id,
                StockMovement.kind == "ORDER_CANCEL",
            )
        )
        assert cancel_mv_count_final == 1
