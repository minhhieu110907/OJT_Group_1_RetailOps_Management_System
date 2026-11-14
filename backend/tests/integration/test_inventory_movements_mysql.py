"""MySQL integration tests for Low-Stock alerts and Stock Movement history (T04A78E)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
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
from app.modules.inventory.service import InventoryQueryService
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import (
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from app.modules.sales.models import Order, OrderItem
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


@pytest.fixture(autouse=True)
def clean_test_rows(migrated_integration_engine: Engine) -> Iterator[None]:
    """Tear down all test rows created under TEST_PREFIX after each test."""
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
        session.execute(
            delete(User).where(
                User.admin_slot.is_(None),
                User.email_normalized.like(f"{TEST_PREFIX}%"),
            )
        )


def _get_or_create_admin(session: Session) -> User:
    """Retrieve existing seeded admin or create an active admin with admin_slot=1."""
    admin = session.scalar(select(User).where(User.admin_slot == 1))
    if admin is None:
        now = datetime.now(UTC).replace(tzinfo=None)
        admin = User(
            email_normalized=f"{TEST_PREFIX}admin@example.com",
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
        contact_name="Test Supplier",
        phone=f"+8490{uuid4().hex[:7]}",
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
        created_at=now,
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
        status="CONFIRMED",
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
        status="CONFIRMED",
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
        quantity_before=0,
        quantity_after=5,
        stock_version_after=1,
        occurred_at=t1,
    )
    session.add(m4)
    session.flush()

    session.commit()

    return {
        "admin": admin,
        "staff": staff,
        "category": category,
        "products": [p1, p2, p3, p4],
        "movements": [m1, m2, m3, m4],
        "adjustment": adjustment,
    }


def test_stock_movements_sorting_occurred_at_desc_id_desc(
    migrated_integration_engine: Engine,
) -> None:
    """Ensure movements are ordered by occurred_at DESC, id DESC."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()

        p1: Product = data["products"][0]  # type: ignore[index]
        page = service.list_stock_movements_admin(
            session=session,
            page=1,
            page_size=20,
            product_id=p1.id,
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

        p1: Product = data["products"][0]  # type: ignore[index]
        p2: Product = data["products"][1]  # type: ignore[index]

        # Filter by product_id
        page_p2 = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, product_id=p2.id
        )
        assert page_p2.total == 1
        assert page_p2.items[0].product_id == p2.id

        # Filter by kind = ADJUSTMENT
        page_adj = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, kind="ADJUSTMENT"
        )
        for item in page_adj.items:
            assert item.kind == "ADJUSTMENT"
            if item.product_id == p1.id:
                assert item.adjustment_reason == "Found damaged items during audit"

        # Filter by both product_id and kind
        page_p1_sale = service.list_stock_movements_admin(
            session=session, page=1, page_size=20, product_id=p1.id, kind="SALE"
        )
        assert page_p1_sale.total == 1
        assert page_p1_sale.items[0].kind == "SALE"
        assert page_p1_sale.items[0].product_id == p1.id


def test_stock_movements_rbac_staff_and_admin(
    migrated_integration_engine: Engine,
) -> None:
    """Verify field-level RBAC: STAFF hides audit and prices, ADMIN gets audit."""
    with Session(migrated_integration_engine) as session:
        data = _seed_test_dataset(session)
        service = InventoryQueryService()
        p1: Product = data["products"][0]  # type: ignore[index]

        # 1. STAFF query
        staff_page = service.list_stock_movements_staff(
            session=session, page=1, page_size=20, product_id=p1.id
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
            session=session, page=1, page_size=20, product_id=p1.id
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

        p1: Product = data["products"][0]  # qty=2, ACTIVE
        p2: Product = data["products"][1]  # qty=5, ACTIVE
        p3: Product = data["products"][2]  # qty=6, ACTIVE (excluded)
        p4: Product = data["products"][3]  # qty=1, INACTIVE (excluded)

        low_stock_page = service.get_low_stock(
            session=session,
            page=1,
            page_size=20,
            threshold=DEFAULT_LOW_STOCK_THRESHOLD,
        )

        assert isinstance(low_stock_page, LowStockPage)
        returned_ids = [item.product_id for item in low_stock_page.items]

        # P1 and P2 MUST be returned
        assert p1.id in returned_ids
        assert p2.id in returned_ids

        # P3 (qty=6 > 5) and P4 (INACTIVE) MUST NOT be returned
        assert p3.id not in returned_ids
        assert p4.id not in returned_ids

        # Verify sorting: quantity ASC, product_id ASC
        filtered_items = [
            item for item in low_stock_page.items if item.product_id in (p1.id, p2.id)
        ]
        assert len(filtered_items) == 2
        assert filtered_items[0].product_id == p1.id
        assert filtered_items[0].quantity == 2
        assert filtered_items[1].product_id == p2.id
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
        staff: User = data["staff"]  # type: ignore[index]

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

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user=staff, session_id=uuid4()
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
        p1_id = data["products"][0].id  # type: ignore[index]
        res_prod = await client.get(f"/api/v1/inventory/{p1_id}")
        assert res_prod.status_code == 200
        assert res_prod.json()["product_id"] == p1_id
