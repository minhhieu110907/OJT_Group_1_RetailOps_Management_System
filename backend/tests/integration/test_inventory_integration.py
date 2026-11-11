"""MySQL integration tests for Inventory Query API, persistence, and safety."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapper, Session

from app.core.exceptions import ResourceNotFoundError
from app.modules.categories.models import Category
from app.modules.inventory.schemas import InventoryPage, InventoryRead
from app.modules.inventory.service import InventoryQueryService
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.schemas import ProductCreateRequest
from app.modules.products.service import ProductService

pytestmark = pytest.mark.integration

SKU_PREFIX = "T04A6BD-"
CATEGORY_PREFIX = "T04A6BD_CAT_"


class InventoryTestRowTracker:
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

    def start(self) -> "InventoryTestRowTracker":
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

    def __enter__(self) -> "InventoryTestRowTracker":
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
def clean_inventory_test_rows(
    migrated_integration_engine: Engine,
) -> Iterator[InventoryTestRowTracker]:
    """Delete only categories, products, and inventory created in current test."""
    with InventoryTestRowTracker(migrated_integration_engine) as tracker:
        yield tracker


def unique_token(label: str) -> str:
    return f"{label}_{uuid4().hex[:8]}"


def add_category(
    session: Session, name_suffix: str, status: str = "ACTIVE"
) -> Category:
    now = datetime(2026, 11, 11, 10, 0)
    category = Category(
        name=f"{CATEGORY_PREFIX}{unique_token(name_suffix)}",
        status=status,
        created_at=now,
        updated_at=now,
    )
    session.add(category)
    session.commit()
    return category


def test_mysql_case1_newly_created_product_has_zero_stock(
    migrated_integration_engine: Engine,
) -> None:
    """Case 1: Newly created product has qty=0, version=0, first_stocked=None."""
    product_service = ProductService()
    inventory_service = InventoryQueryService()
    run_tag = unique_token("CASE1")

    with Session(migrated_integration_engine) as session:
        category = add_category(session, f"{run_tag}_CAT", status="ACTIVE")

        product = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}",
                name=f"{run_tag} Test Product",
                category_id=category.id,
                sale_price_vnd=50_000,
            ),
        )

        detail = inventory_service.get_inventory(session, product.id)
        assert isinstance(detail, InventoryRead)
        assert detail.product_id == product.id
        assert detail.sku == f"{SKU_PREFIX}{run_tag}"
        assert detail.name == f"{run_tag} Test Product"
        assert detail.category_id == category.id
        assert detail.status == "ACTIVE"
        assert detail.quantity == 0
        assert detail.stock_version == 0
        assert detail.first_stocked_at is None

        page = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=category.id
        )
        assert isinstance(page, InventoryPage)
        assert page.total == 1
        assert len(page.items) == 1
        assert page.items[0].product_id == product.id
        assert page.items[0].quantity == 0


def test_mysql_case2_persisted_stock_mutation_reflection(
    migrated_integration_engine: Engine,
) -> None:
    """Case 2: Persisted inventory mutation is accurately reflected by query API.

    Note on dependency gating:
    Full Stock Movement E2E requires T04A653 (Inventory Mutation Service by Dương).
    Because T04A653 is not yet merged, this test verifies persistence & query accuracy
    using a committed InnoDB update adhering to ck_inventory_qty_version_first_stocked.
    """
    product_service = ProductService()
    inventory_service = InventoryQueryService()
    run_tag = unique_token("CASE2")

    with Session(migrated_integration_engine) as session:
        category = add_category(session, f"{run_tag}_CAT", status="ACTIVE")

        product = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}",
                name=f"{run_tag} Mutation Test",
                category_id=category.id,
                sale_price_vnd=75_000,
            ),
        )

        first_stocked = datetime(2026, 11, 11, 11, 0, 0)
        inv = session.execute(
            select(Inventory).where(Inventory.product_id == product.id)
        ).scalar_one()
        inv.quantity = 15
        inv.stock_version = 1
        inv.first_stocked_at = first_stocked
        session.commit()

        detail = inventory_service.get_inventory(session, product.id)
        assert detail.quantity == 15
        assert detail.stock_version == 1
        assert detail.first_stocked_at == first_stocked

        page = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=category.id, in_stock=True
        )
        assert page.total == 1
        assert page.items[0].quantity == 15
        assert page.items[0].stock_version == 1


def test_mysql_case3_no_internal_cost_or_price_leakage(
    migrated_integration_engine: Engine,
) -> None:
    """Case 3: Ensure responses NEVER expose cost_price or price fields."""
    product_service = ProductService()
    inventory_service = InventoryQueryService()
    run_tag = unique_token("CASE3")

    with Session(migrated_integration_engine) as session:
        category = add_category(session, f"{run_tag}_CAT", status="ACTIVE")

        product = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}",
                name=f"{run_tag} Leakage Test",
                category_id=category.id,
                sale_price_vnd=99_000,
            ),
        )

        detail = inventory_service.get_inventory(session, product.id)
        detail_dict = detail.model_dump()
        forbidden_fields = {
            "cost_price",
            "cost_price_vnd",
            "unit_cost_vnd",
            "sale_price_vnd",
            "reason",
        }
        for field in forbidden_fields:
            assert field not in detail_dict

        allowed_fields = {
            "product_id",
            "sku",
            "name",
            "category_id",
            "status",
            "quantity",
            "stock_version",
            "first_stocked_at",
        }
        assert set(detail_dict.keys()) == allowed_fields

        page = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=category.id
        )
        for item in page.items:
            item_dict = item.model_dump()
            for field in forbidden_fields:
                assert field not in item_dict
            assert set(item_dict.keys()) == allowed_fields


def test_mysql_case4_filtering_pagination_and_stable_sorting(
    migrated_integration_engine: Engine,
) -> None:
    """Case 4: Multi-filter combinations, stable sorting, and pagination."""
    product_service = ProductService()
    inventory_service = InventoryQueryService()
    run_tag = unique_token("CASE4")

    with Session(migrated_integration_engine) as session:
        cat_a = add_category(session, f"{run_tag}_A", status="ACTIVE")
        cat_b = add_category(session, f"{run_tag}_B", status="ACTIVE")

        # P1: Cat A, ACTIVE, in_stock=True (qty=30)
        p1 = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-1",
                name=f"{run_tag} Prod 1",
                category_id=cat_a.id,
                sale_price_vnd=10_000,
            ),
        )
        inv1 = session.execute(
            select(Inventory).where(Inventory.product_id == p1.id)
        ).scalar_one()
        inv1.quantity = 30
        inv1.stock_version = 1
        inv1.first_stocked_at = datetime(2026, 11, 11, 10, 0, 0)

        # P2: Cat A, ACTIVE, in_stock=False (qty=0)
        p2 = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-2",
                name=f"{run_tag} Prod 2",
                category_id=cat_a.id,
                sale_price_vnd=20_000,
            ),
        )

        # P3: Cat B, ACTIVE, in_stock=True (qty=10)
        p3 = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-3",
                name=f"{run_tag} Prod 3",
                category_id=cat_b.id,
                sale_price_vnd=30_000,
            ),
        )
        inv3 = session.execute(
            select(Inventory).where(Inventory.product_id == p3.id)
        ).scalar_one()
        inv3.quantity = 10
        inv3.stock_version = 1
        inv3.first_stocked_at = datetime(2026, 11, 11, 10, 5, 0)

        # P4: Cat B, INACTIVE, in_stock=False (qty=0)
        p4 = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}-4",
                name=f"{run_tag} Prod 4",
                category_id=cat_b.id,
                sale_price_vnd=40_000,
            ),
        )
        p4_obj = session.execute(
            select(Product).where(Product.id == p4.id)
        ).scalar_one()
        p4_obj.status = CatalogStatus.INACTIVE.value
        session.commit()

        # 1. Filter by category
        page_cat_a = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=cat_a.id
        )
        assert page_cat_a.total == 2
        assert [item.product_id for item in page_cat_a.items] == [p1.id, p2.id]

        # 2. Filter by status
        page_active = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=cat_b.id, status="ACTIVE"
        )
        assert page_active.total == 1
        assert page_active.items[0].product_id == p3.id

        page_inactive = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=cat_b.id, status="INACTIVE"
        )
        assert page_inactive.total == 1
        assert page_inactive.items[0].product_id == p4.id

        # 3. Filter in_stock=true vs in_stock=false
        page_in_stock = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=cat_a.id, in_stock=True
        )
        assert page_in_stock.total == 1
        assert page_in_stock.items[0].product_id == p1.id

        page_out_stock = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=cat_a.id, in_stock=False
        )
        assert page_out_stock.total == 1
        assert page_out_stock.items[0].product_id == p2.id

        # 4. Out-of-range pagination returns empty items and accurate total
        page_empty = inventory_service.list_inventory(
            session, page=999, page_size=10, category_id=cat_a.id
        )
        assert page_empty.total == 2
        assert page_empty.page == 999
        assert page_empty.items == []

        # 5. Nonexistent product detail raises 404
        with pytest.raises(ResourceNotFoundError):
            inventory_service.get_inventory(session, 999_999_999)


def test_mysql_case5_read_only_invariant_causes_no_mutations(
    migrated_integration_engine: Engine,
) -> None:
    """Case 5: Read-only queries must NOT cause side-effects or commit mutations."""
    product_service = ProductService()
    inventory_service = InventoryQueryService()
    run_tag = unique_token("CASE5")

    with Session(migrated_integration_engine) as session:
        category = add_category(session, f"{run_tag}_CAT", status="ACTIVE")

        product = product_service.create(
            session,
            ProductCreateRequest(
                sku=f"{SKU_PREFIX}{run_tag}",
                name=f"{run_tag} Read Only Test",
                category_id=category.id,
                sale_price_vnd=50_000,
            ),
        )

        before_inv = session.execute(
            select(
                Inventory.quantity,
                Inventory.stock_version,
                Inventory.updated_at,
            ).where(Inventory.product_id == product.id)
        ).one()

        # Perform read operations
        _ = inventory_service.get_inventory(session, product.id)
        _ = inventory_service.list_inventory(
            session, page=1, page_size=20, category_id=category.id
        )

        after_inv = session.execute(
            select(
                Inventory.quantity,
                Inventory.stock_version,
                Inventory.updated_at,
            ).where(Inventory.product_id == product.id)
        ).one()

        assert before_inv.quantity == after_inv.quantity
        assert before_inv.stock_version == after_inv.stock_version
        assert before_inv.updated_at == after_inv.updated_at
