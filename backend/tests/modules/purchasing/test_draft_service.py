"""Unit tests for ReceiptDraftService."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.db.base import Base
from app.modules.auth.models import User
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import ReceiptLineInput
from app.modules.suppliers.models import Supplier, SupplierStatus


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


def make_test_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _rec):
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Supplier.__table__,
            Product.__table__,
            Inventory.__table__,
            PurchaseReceipt.__table__,
            PurchaseReceiptItem.__table__,
        ],
    )
    return engine


def seed_entities(session: Session) -> tuple[Supplier, Product, Product]:
    now = datetime.now(UTC).replace(tzinfo=None)
    category = Category(
        name="Đồ gia dụng",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(category)
    session.flush()

    supplier = Supplier(
        name="Nhà phân phối An Bình",
        contact_email="anbinh@example.com",
        contact_phone="0912345678",
        status=SupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    session.add(supplier)
    session.flush()

    prod1 = Product(
        category_id=category.id,
        sku="SKU-CHAO-01",
        name="Chảo chống dính 26cm",
        status=CatalogStatus.ACTIVE,
        sale_price_vnd=150_000,
        created_at=now,
        updated_at=now,
    )
    prod2 = Product(
        category_id=category.id,
        sku="SKU-NOI-01",
        name="Nồi inox 20cm",
        status=CatalogStatus.ACTIVE,
        sale_price_vnd=200_000,
        created_at=now,
        updated_at=now,
    )
    session.add_all([prod1, prod2])
    session.flush()

    inv1 = Inventory(
        product_id=prod1.id,
        quantity=0,
        stock_version=0,
        first_stocked_at=None,
        updated_at=now,
    )
    inv2 = Inventory(
        product_id=prod2.id,
        quantity=0,
        stock_version=0,
        first_stocked_at=None,
        updated_at=now,
    )
    session.add_all([inv1, inv2])
    session.commit()
    return supplier, prod1, prod2


def test_create_draft_success_merges_identical_product_cost():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, prod2 = seed_entities(session)
        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=3, unit_cost_vnd=80_000),
            ReceiptLineInput(product_id=prod2.id, quantity=5, unit_cost_vnd=120_000),
            ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=80_000),
        ]
        receipt = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=items,
        )
        session.commit()

        assert receipt.status == "DRAFT"
        assert receipt.draft_version == 1
        assert receipt.supplier_id == supplier.id
        assert receipt.supplier_name_snapshot == supplier.name
        assert len(receipt.items) == 2

        # prod1 merged quantity: 3 + 2 = 5; line total: 5 * 80_000 = 400_000
        item1 = next(it for it in receipt.items if it.product_id == prod1.id)
        assert item1.quantity == 5
        assert item1.unit_cost_vnd == 80_000
        assert item1.line_total_vnd == 400_000
        assert item1.sku_snapshot == prod1.sku
        assert item1.product_name_snapshot == prod1.name

        # prod2: 5 * 120_000 = 600_000
        item2 = next(it for it in receipt.items if it.product_id == prod2.id)
        assert item2.quantity == 5
        assert item2.unit_cost_vnd == 120_000
        assert item2.line_total_vnd == 600_000

        assert receipt.total_vnd == 1_000_000


def test_create_draft_rejects_conflicting_product_cost():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=80_000),
            ReceiptLineInput(product_id=prod1.id, quantity=3, unit_cost_vnd=90_000),
        ]
        with pytest.raises(ConflictError) as exc_info:
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=items,
            )
        assert exc_info.value.code == "RECEIPT_ITEM_COST_CONFLICT"
        assert exc_info.value.status_code == 409


def test_create_draft_rejects_inactive_supplier():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        supplier.status = SupplierStatus.INACTIVE
        session.commit()

        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=50_000)
        ]
        with pytest.raises(DomainValidationError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=items,
            )


def test_create_draft_rejects_inactive_product():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        prod1.status = CatalogStatus.INACTIVE
        session.commit()

        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=50_000)
        ]
        with pytest.raises(DomainValidationError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=items,
            )


def test_create_draft_rejects_nonexistent_supplier_and_product():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        _, prod1, _ = seed_entities(session)
        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=50_000)
        ]
        with pytest.raises(ResourceNotFoundError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=999_999,
                items=items,
            )

        with pytest.raises(ResourceNotFoundError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=1,
                items=[
                    ReceiptLineInput(
                        product_id=999_999, quantity=1, unit_cost_vnd=50_000
                    )
                ],
            )


def test_update_draft_increments_version_and_updates_items():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, prod2 = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=50_000)
            ],
        )
        session.commit()
        assert created.draft_version == 1
        assert created.total_vnd == 100_000

        updated = service.update_draft(
            session,
            actor_id=1,
            receipt_id=created.id,
            expected_draft_version=1,
            items=[
                ReceiptLineInput(product_id=prod2.id, quantity=4, unit_cost_vnd=60_000)
            ],
        )
        session.commit()

        assert updated.draft_version == 2
        assert updated.total_vnd == 240_000
        assert len(updated.items) == 1
        assert updated.items[0].product_id == prod2.id
        assert updated.items[0].quantity == 4


def test_update_draft_stale_version_conflict():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=50_000)
            ],
        )
        session.commit()

        with pytest.raises(ConflictError) as exc_info:
            service.update_draft(
                session,
                actor_id=1,
                receipt_id=created.id,
                expected_draft_version=99,
                items=None,
            )
        assert exc_info.value.code == "RECEIPT_VERSION_CONFLICT"
        assert exc_info.value.status_code == 409


def test_update_draft_rejects_non_draft_status():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=50_000)
            ],
        )
        receipt_row = session.get(PurchaseReceipt, created.id)
        receipt_row.status = "CONFIRMED"
        receipt_row.closed_by = 1
        receipt_row.closed_at = datetime.now(UTC).replace(tzinfo=None)
        session.commit()

        with pytest.raises(InvalidStateError):
            service.update_draft(
                session,
                actor_id=1,
                receipt_id=created.id,
                expected_draft_version=1,
                items=None,
            )


def test_draft_operations_do_not_mutate_inventory():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, prod2 = seed_entities(session)

        # Before draft
        inv_before = list(
            session.scalars(select(Inventory).order_by(Inventory.product_id))
        )
        assert [i.quantity for i in inv_before] == [0, 0]
        assert [i.stock_version for i in inv_before] == [0, 0]

        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(
                    product_id=prod1.id, quantity=10, unit_cost_vnd=50_000
                ),
                ReceiptLineInput(
                    product_id=prod2.id, quantity=20, unit_cost_vnd=80_000
                ),
            ],
        )
        session.commit()

        # After create draft
        inv_after_create = list(
            session.scalars(select(Inventory).order_by(Inventory.product_id))
        )
        assert [i.quantity for i in inv_after_create] == [0, 0]
        assert [i.stock_version for i in inv_after_create] == [0, 0]

        service.update_draft(
            session,
            actor_id=1,
            receipt_id=created.id,
            expected_draft_version=1,
            items=[
                ReceiptLineInput(
                    product_id=prod1.id, quantity=100, unit_cost_vnd=50_000
                )
            ],
        )
        session.commit()

        # After update draft
        inv_after_update = list(
            session.scalars(select(Inventory).order_by(Inventory.product_id))
        )
        assert [i.quantity for i in inv_after_update] == [0, 0]
        assert [i.stock_version for i in inv_after_update] == [0, 0]
