"""MySQL integration tests for Product API, transactions, constraints, and races."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapper, Session

from app.core.exceptions import (
    DomainValidationError,
    DuplicateSkuError,
)
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.repository import InventoryRepository
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductSortOrder,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)
from app.modules.products.service import ProductService

pytestmark = pytest.mark.integration

SKU_PREFIX = "T3C9AEB-"
CATEGORY_PREFIX = "T3C9AEB_CAT_"


class ProductRowTracker:
    """Track and delete only rows inserted through the target test engine."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.category_ids: set[int] = set()
        self.product_ids: set[int] = set()
        self.inventory_product_ids: set[int] = set()
        self._active = False

    def _record_category_insert(
        self,
        _mapper: Mapper[Any],
        connection: Connection,
        target: Category,
    ) -> None:
        if connection.engine is self.engine and target.id is not None:
            self.category_ids.add(int(target.id))

    def _record_product_insert(
        self,
        _mapper: Mapper[Any],
        connection: Connection,
        target: Product,
    ) -> None:
        if connection.engine is self.engine and target.id is not None:
            self.product_ids.add(int(target.id))

    def _record_inventory_insert(
        self,
        _mapper: Mapper[Any],
        connection: Connection,
        target: Inventory,
    ) -> None:
        if connection.engine is self.engine and target.product_id is not None:
            self.inventory_product_ids.add(int(target.product_id))

    def start(self) -> "ProductRowTracker":
        if not self._active:
            event.listen(Category, "after_insert", self._record_category_insert)
            event.listen(Product, "after_insert", self._record_product_insert)
            event.listen(Inventory, "after_insert", self._record_inventory_insert)
            self._active = True
        return self

    def stop(self) -> None:
        if self._active:
            event.remove(Category, "after_insert", self._record_category_insert)
            event.remove(Product, "after_insert", self._record_product_insert)
            event.remove(Inventory, "after_insert", self._record_inventory_insert)
            self._active = False

    def cleanup(self) -> None:
        inventory_ids = self.inventory_product_ids | self.product_ids
        if not inventory_ids and not self.product_ids and not self.category_ids:
            return
        with Session(self.engine) as session, session.begin():
            if inventory_ids:
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(inventory_ids))
                )
            if self.product_ids:
                session.execute(delete(Product).where(Product.id.in_(self.product_ids)))
            if self.category_ids:
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )
        self.inventory_product_ids.clear()
        self.product_ids.clear()
        self.category_ids.clear()

    def __enter__(self) -> "ProductRowTracker":
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        try:
            self.stop()
        finally:
            self.cleanup()


@pytest.fixture(autouse=True)
def clean_product_test_rows(
    migrated_integration_engine: Engine,
) -> Iterator[ProductRowTracker]:
    """Delete only categories, products, and inventory created in current test."""
    with ProductRowTracker(migrated_integration_engine) as tracker:
        yield tracker


def unique_token(label: str) -> str:
    return f"{label}_{uuid4().hex[:8]}"


def add_category(
    session: Session, name_suffix: str, status: str = "ACTIVE"
) -> Category:
    now = datetime(2026, 11, 7, 10, 0)
    category = Category(
        name=f"{CATEGORY_PREFIX}{unique_token(name_suffix)}",
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
    sku = f"{SKU_PREFIX}{unique_token('ATOMIC')}"
    with Session(migrated_integration_engine) as session:
        category = add_category(session, "DRINK", status="ACTIVE")
        created = service.create(
            session,
            ProductCreateRequest(
                sku=sku,
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
    sku = f"{SKU_PREFIX}{unique_token('ROLLBACK')}"
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
    preexisting_sku = f"{SKU_PREFIX}{unique_token('PRE_RACE')}"
    race_sku = f"{SKU_PREFIX}{unique_token('RACE')}"

    with Session(migrated_integration_engine) as setup_session:
        preexisting_category = add_category(
            setup_session, "PRE_RACE_CAT", status="ACTIVE"
        )
        preexisting_product = service.create(
            setup_session,
            ProductCreateRequest(
                sku=preexisting_sku,
                name="Sản phẩm có sẵn trước race",
                category_id=preexisting_category.id,
                sale_price_vnd=21_000,
            ),
        )
        preexisting_product_id = preexisting_product.id
        preexisting_category_id = preexisting_category.id

    with ProductRowTracker(migrated_integration_engine):
        with Session(migrated_integration_engine) as race_setup_session:
            race_category = add_category(
                race_setup_session, "RACE_CAT", status="ACTIVE"
            )
            race_category_id = race_category.id

        def worker(index: int) -> str:
            with Session(migrated_integration_engine) as worker_session:
                try:
                    service.create(
                        worker_session,
                        ProductCreateRequest(
                            sku=race_sku,
                            name=f"Sản phẩm đua tranh {index}",
                            category_id=race_category_id,
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
                verify_session.scalars(select(Product).where(Product.sku == race_sku))
            )
            assert len(products) == 1

    with Session(migrated_integration_engine) as after_cleanup_session:
        assert (
            after_cleanup_session.scalar(select(Product).where(Product.sku == race_sku))
            is None
        )
        assert after_cleanup_session.get(Product, preexisting_product_id) is not None
        assert after_cleanup_session.get(Category, preexisting_category_id) is not None


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
                    sku=f"{SKU_PREFIX}{unique_token('INACT')}",
                    name="Sản phẩm danh mục khóa",
                    category_id=inactive_cat.id,
                    sale_price_vnd=12_000,
                ),
            )

        created = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{unique_token('FLOW')}",
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


def test_mysql_cleanup_preserves_preexisting_category_and_product(
    migrated_integration_engine: Engine,
) -> None:
    """Verify Scenarios 1, 2, and 3: exact ID cleanup preserves preexisting data."""
    service = ProductService()
    with Session(migrated_integration_engine) as outer_session:
        preexisting_category = add_category(
            outer_session, "PREEXISTING_CAT", status="ACTIVE"
        )
        preexisting_product = service.create(
            outer_session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{unique_token('PREEXISTING_PROD')}",
                name="Sản phẩm tồn tại trước test",
                category_id=preexisting_category.id,
                sale_price_vnd=30_000,
            ),
        )
        preexisting_category_id = preexisting_category.id
        preexisting_product_id = preexisting_product.id

    with (
        ProductRowTracker(migrated_integration_engine),
        Session(migrated_integration_engine) as inner_session,
    ):
        inner_category = add_category(inner_session, "INNER_CAT", status="ACTIVE")
        inner_product = service.create(
            inner_session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{unique_token('INNER_PROD')}",
                name="Sản phẩm tạo trong phạm vi test",
                category_id=inner_category.id,
                sale_price_vnd=18_000,
            ),
        )
        inner_category_id = inner_category.id
        inner_product_id = inner_product.id

    with Session(migrated_integration_engine) as verify_session:
        assert verify_session.get(Category, inner_category_id) is None
        assert verify_session.get(Product, inner_product_id) is None
        assert (
            verify_session.scalar(
                select(Inventory).where(Inventory.product_id == inner_product_id)
            )
            is None
        )

        kept_category = verify_session.get(Category, preexisting_category_id)
        kept_product = verify_session.get(Product, preexisting_product_id)
        kept_inventory = verify_session.scalar(
            select(Inventory).where(Inventory.product_id == preexisting_product_id)
        )
        assert kept_category is not None
        assert kept_product is not None
        assert kept_inventory is not None


def test_mysql_cleanup_deletes_committed_rows_when_test_fails(
    migrated_integration_engine: Engine,
) -> None:
    """Verify Scenario 4: forced exception after commits still cleans up test rows."""
    service = ProductService()
    with Session(migrated_integration_engine) as outer_session:
        preexisting_category = add_category(
            outer_session, "SAFE_OUTER_CAT", status="ACTIVE"
        )
        preexisting_category_id = preexisting_category.id

    committed_category_id: int | None = None
    committed_product_id: int | None = None

    with (
        pytest.raises(RuntimeError, match="Simulated mid-test failure"),
        ProductRowTracker(migrated_integration_engine),
    ):
        with Session(migrated_integration_engine) as first_session:
            inner_category = add_category(
                first_session, "FAIL_INNER_CAT", status="ACTIVE"
            )
            committed_category_id = inner_category.id

        with Session(migrated_integration_engine) as second_session:
            inner_product = service.create(
                second_session,
                ProductCreateRequest(
                    sku=f"{SKU_PREFIX}{unique_token('FAIL_INNER_PROD')}",
                    name="Sản phẩm đã commit trước khi test lỗi",
                    category_id=committed_category_id,
                    sale_price_vnd=22_000,
                ),
            )
            committed_product_id = inner_product.id

        raise RuntimeError("Simulated mid-test failure")

    assert committed_category_id is not None
    assert committed_product_id is not None

    with Session(migrated_integration_engine) as verify_session:
        assert verify_session.get(Category, committed_category_id) is None
        assert verify_session.get(Product, committed_product_id) is None
        assert (
            verify_session.scalar(
                select(Inventory).where(Inventory.product_id == committed_product_id)
            )
            is None
        )
        assert verify_session.get(Category, preexisting_category_id) is not None


def test_mysql_product_search_filter_sort_and_pagination_stability(
    migrated_integration_engine: Engine,
) -> None:
    """Verify MySQL 8 query behavior: search, filters, sorts, and tie-breakers."""
    service = ProductService()
    run_tag = unique_token("QRY")

    with Session(migrated_integration_engine) as session:
        cat_a = add_category(session, f"{run_tag}_CAT_A", status="ACTIVE")
        cat_b = add_category(session, f"{run_tag}_CAT_B", status="ACTIVE")

        # Create products in cat_a and cat_b, with duplicate names for tie-breaker
        p1 = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-ALPHA",
                name=f"{run_tag} Cà phê rang xay",
                category_id=cat_a.id,
                sale_price_vnd=40_000,
            ),
        )
        p2 = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-BETA",
                name=f"{run_tag} Cà phê rang xay",
                category_id=cat_a.id,
                sale_price_vnd=42_000,
            ),
        )
        p3 = service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-GAMMA",
                name=f"{run_tag} Trà Ô Long",
                category_id=cat_b.id,
                sale_price_vnd=28_000,
            ),
        )
        service.update_status(
            session,
            p3.id,
            ProductStatusUpdateRequest(status=CatalogStatus.INACTIVE),
        )

        # 1. Case-insensitive search on ascii_bin SKU in MySQL
        lower_sku_query = f"{run_tag}-alpha".lower()
        sku_res = service.list_products(session, search=lower_sku_query)
        assert sku_res.total == 1
        assert sku_res.items[0].id == p1.id

        # 2. Case-insensitive search on Vietnamese product name
        name_res = service.list_products(
            session,
            search=f"{run_tag} cà PHÊ",
            sort=ProductSortOrder.NAME_ASC,
        )
        assert name_res.total == 2
        assert [item.id for item in name_res.items] == [p1.id, p2.id]

        # 3. name_desc uses id DESC tie-breaker when names are identical
        name_desc_res = service.list_products(
            session,
            search=f"{run_tag} Cà phê",
            sort=ProductSortOrder.NAME_DESC,
        )
        assert [item.id for item in name_desc_res.items] == [p2.id, p1.id]

        # 4. sku_asc and sku_desc
        sku_asc_res = service.list_products(
            session,
            search=run_tag,
            sort=ProductSortOrder.SKU_ASC,
        )
        assert [item.id for item in sku_asc_res.items] == [p1.id, p2.id, p3.id]

        sku_desc_res = service.list_products(
            session,
            search=run_tag,
            sort=ProductSortOrder.SKU_DESC,
        )
        assert [item.id for item in sku_desc_res.items] == [p3.id, p2.id, p1.id]

        # 5. Filter by category_id and status
        cat_a_active = service.list_products(
            session,
            search=run_tag,
            category_id=cat_a.id,
            status=CatalogStatus.ACTIVE,
            sort=ProductSortOrder.CREATED_DESC,
        )
        assert cat_a_active.total == 2
        assert [item.id for item in cat_a_active.items] == [p2.id, p1.id]

        inactive_only = service.list_products(
            session,
            search=run_tag,
            status=CatalogStatus.INACTIVE,
        )
        assert inactive_only.total == 1
        assert inactive_only.items[0].id == p3.id

        # 6. Multi-page pagination stability (page_size=1 across 3 items)
        paged_ids: list[int] = []
        for page_num in (1, 2, 3):
            page_res = service.list_products(
                session,
                page=page_num,
                page_size=1,
                search=run_tag,
                sort=ProductSortOrder.NAME_ASC,
            )
            assert page_res.total == 3
            assert len(page_res.items) == 1
            paged_ids.append(page_res.items[0].id)
        assert paged_ids == [p1.id, p2.id, p3.id]
