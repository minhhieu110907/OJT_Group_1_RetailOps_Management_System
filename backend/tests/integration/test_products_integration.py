"""MySQL integration tests for Product API, transactions, constraints, and races."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DomainValidationError,
    DuplicateSkuError,
)
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.repository import InventoryRepository
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)
from app.modules.products.service import ProductService

pytestmark = pytest.mark.integration

SKU_PREFIX = "T3C9AEB-"
CATEGORY_PREFIX = "T3C9AEB_CAT_"


@pytest.fixture(autouse=True)
def clean_product_test_rows(
    migrated_integration_engine: Engine,
) -> None:
    """Ensure catalog tables exist and clean test rows after each test."""
    Category.__table__.create(bind=migrated_integration_engine, checkfirst=True)
    Product.__table__.create(bind=migrated_integration_engine, checkfirst=True)
    Inventory.__table__.create(bind=migrated_integration_engine, checkfirst=True)
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        product_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{SKU_PREFIX}%"))
            )
        )
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))
        session.execute(
            delete(Category).where(Category.name.like(f"{CATEGORY_PREFIX}%"))
        )


def add_category(
    session: Session, name_suffix: str, status: str = "ACTIVE"
) -> Category:
    now = datetime(2026, 11, 7, 10, 0)
    category = Category(
        name=f"{CATEGORY_PREFIX}{name_suffix}",
        status=status,
        created_at=now,
        updated_at=now,
    )
    session.add(category)
    session.commit()
    return category


def test_mysql_product_create_atomically_creates_zero_inventory(
    migrated_integration_engine: Engine,
) -> None:
    service = ProductService()
    with Session(migrated_integration_engine) as session:
        category = add_category(session, "DRINK", status="ACTIVE")
        created = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}ATOMIC-01",
                name="Nước cam ép",
                category_id=category.id,
                sale_price_vnd=25_000,
            ),
        )
        assert created.quantity == 0
        assert created.stock_version == 0

    with Session(migrated_integration_engine) as verify_session:
        inv = verify_session.scalar(
            select(Inventory).where(Inventory.product_id == created.id)
        )
        assert inv is not None
        assert inv.quantity == 0
        assert inv.stock_version == 0
        assert inv.first_stocked_at is None


def test_mysql_forced_inventory_failure_rolls_back_product_row(
    migrated_integration_engine: Engine,
) -> None:
    class FailingInventoryRepository(InventoryRepository):
        def add_zero(
            self, session: Session, product_id: int, now: datetime
        ) -> Inventory:
            raise RuntimeError("Forced inventory failure after product flush")

    service = ProductService(inventory=FailingInventoryRepository())
    sku = f"{SKU_PREFIX}ROLLBACK-01"
    with Session(migrated_integration_engine) as session:
        category = add_category(session, "ROLLBACK", status="ACTIVE")
        with pytest.raises(RuntimeError, match="Forced inventory failure"):
            service.create(
                session,
                ProductCreateRequest(
                    sku=sku,
                    name="Sản phẩm test rollback",
                    category_id=category.id,
                    sale_price_vnd=15_000,
                ),
            )

    with Session(migrated_integration_engine) as verify_session:
        orphan = verify_session.scalar(select(Product).where(Product.sku == sku))
        assert orphan is None


def test_mysql_concurrent_duplicate_sku_allows_only_one_product(
    migrated_integration_engine: Engine,
) -> None:
    service = ProductService()
    sku = f"{SKU_PREFIX}RACE-01"
    with Session(migrated_integration_engine) as setup_session:
        category = add_category(setup_session, "RACE", status="ACTIVE")
        category_id = category.id

    def worker(index: int) -> str:
        with Session(migrated_integration_engine) as worker_session:
            try:
                service.create(
                    worker_session,
                    ProductCreateRequest(
                        sku=sku,
                        name=f"Sản phẩm đua tranh {index}",
                        category_id=category_id,
                        sale_price_vnd=19_000,
                    ),
                )
                return "created"
            except DuplicateSkuError:
                return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))

    assert sorted(outcomes) == ["created", "duplicate"]
    with Session(migrated_integration_engine) as verify_session:
        products = list(
            verify_session.scalars(select(Product).where(Product.sku == sku))
        )
        assert len(products) == 1


def test_mysql_inactive_category_and_update_status_flow(
    migrated_integration_engine: Engine,
) -> None:
    service = ProductService()
    with Session(migrated_integration_engine) as session:
        active_cat = add_category(session, "ACTIVE", status="ACTIVE")
        inactive_cat = add_category(session, "INACTIVE", status="INACTIVE")

        with pytest.raises(DomainValidationError):
            service.create(
                session,
                ProductCreateRequest(
                    sku=f"{SKU_PREFIX}INACT-CAT",
                    name="Sản phẩm danh mục khóa",
                    category_id=inactive_cat.id,
                    sale_price_vnd=12_000,
                ),
            )

        created = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}FLOW-01",
                name="Sản phẩm chuẩn",
                category_id=active_cat.id,
                sale_price_vnd=12_000,
            ),
        )
        updated = service.update(
            session,
            created.id,
            ProductUpdateRequest(name="Sản phẩm đã sửa", sale_price_vnd=14_000),
        )
        assert updated.name == "Sản phẩm đã sửa"
        assert updated.sale_price_vnd == 14_000

        deactivated = service.update_status(
            session,
            created.id,
            ProductStatusUpdateRequest(status=CatalogStatus.INACTIVE),
        )
        assert deactivated.status == CatalogStatus.INACTIVE

        listed = service.list_products(session, page=1, page_size=20)
        assert listed.total >= 1

