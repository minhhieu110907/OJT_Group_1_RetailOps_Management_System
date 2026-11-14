"""Unit tests for ReceiptDraftService."""

from datetime import UTC, date, datetime

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
from app.modules.purchasing.draft_service import VN_TZ, ReceiptDraftService
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import (
    MAX_SQL_INT,
    ReceiptLineInput,
)
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
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=items,
        )
        session.commit()

        assert created.status == "DRAFT"
        assert created.draft_version == 1
        assert created.supplier_id == supplier.id
        assert created.supplier_name_snapshot == supplier.name
        # 5 * 80k + 5 * 120k = 400k + 600k = 1_000_000
        assert created.total_vnd == 1_000_000
        assert len(created.items) == 2

        item_p1 = next(it for it in created.items if it.product_id == prod1.id)
        assert item_p1.quantity == 5
        assert item_p1.unit_cost_vnd == 80_000
        assert item_p1.line_total_vnd == 400_000
        assert item_p1.sku_snapshot == "SKU-CHAO-01"

        item_p2 = next(it for it in created.items if it.product_id == prod2.id)
        assert item_p2.quantity == 5
        assert item_p2.unit_cost_vnd == 120_000
        assert item_p2.line_total_vnd == 600_000


def test_create_draft_rejects_conflicting_product_cost():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        items = [
            ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=80_000),
            ReceiptLineInput(product_id=prod1.id, quantity=3, unit_cost_vnd=90_000),
        ]
        with pytest.raises(DomainValidationError) as exc_info:
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=items,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.details["code"] == "RECEIPT_ITEM_COST_CONFLICT"
        assert exc_info.value.details["product_id"] == prod1.id


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
        supplier, prod1, _ = seed_entities(session)

        # Nonexistent supplier
        with pytest.raises(ResourceNotFoundError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=99999,
                items=[
                    ReceiptLineInput(
                        product_id=prod1.id, quantity=1, unit_cost_vnd=50_000
                    )
                ],
            )

        # Nonexistent product
        with pytest.raises(ResourceNotFoundError):
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=[
                    ReceiptLineInput(product_id=99999, quantity=1, unit_cost_vnd=50_000)
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

        # Update items
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
        assert updated.total_vnd == 240_000  # 4 * 60k
        assert len(updated.items) == 1
        assert updated.items[0].product_id == prod2.id


def test_update_draft_rejects_empty_patch():
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
        initial_updated_at = created.updated_at

        # Empty PATCH (neither supplier_id nor items provided)
        with pytest.raises(DomainValidationError) as exc_info:
            service.update_draft(
                session,
                actor_id=1,
                receipt_id=created.id,
                expected_draft_version=1,
                supplier_id=None,
                items=None,
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.details["reason"] == "EMPTY_PATCH_FORBIDDEN"

        # Verify receipt invariants: version, updated_at, total, items are unchanged
        current = session.get(PurchaseReceipt, created.id)
        assert current.draft_version == 1
        assert current.updated_at == initial_updated_at
        assert current.total_vnd == 100_000
        current_items = list(
            session.scalars(
                select(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id == created.id
                )
            )
        )
        assert len(current_items) == 1


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
                items=[
                    ReceiptLineInput(
                        product_id=prod1.id, quantity=3, unit_cost_vnd=50_000
                    )
                ],
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
                items=[
                    ReceiptLineInput(
                        product_id=prod1.id, quantity=3, unit_cost_vnd=50_000
                    )
                ],
            )


def test_create_and_update_integer_bounds_and_overflow():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)

        # Merged quantity exceeds MAX_SQL_INT
        half_max = MAX_SQL_INT // 2 + 10
        items_merged_overflow = [
            ReceiptLineInput(product_id=prod1.id, quantity=half_max, unit_cost_vnd=1),
            ReceiptLineInput(product_id=prod1.id, quantity=half_max, unit_cost_vnd=1),
        ]
        with pytest.raises(DomainValidationError) as exc_info:
            service.create_draft(
                session,
                actor_id=1,
                supplier_id=supplier.id,
                items=items_merged_overflow,
            )
        assert exc_info.value.status_code == 422
        assert "vượt quá giới hạn SQL INT" in str(exc_info.value)

        # Valid boundary: quantity == MAX_SQL_INT, unit_cost_vnd == 1
        valid_boundary_items = [
            ReceiptLineInput(product_id=prod1.id, quantity=MAX_SQL_INT, unit_cost_vnd=1)
        ]
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=valid_boundary_items,
        )
        assert created.total_vnd == MAX_SQL_INT
        assert created.items[0].quantity == MAX_SQL_INT


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


def test_cancel_draft_success():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, prod2 = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=5, unit_cost_vnd=40_000),
                ReceiptLineInput(product_id=prod2.id, quantity=3, unit_cost_vnd=60_000),
            ],
        )
        session.commit()
        receipt_id = created.id

    with Session(engine) as session:
        cancelled = service.cancel_draft(
            session,
            actor_id=1,
            receipt_id=receipt_id,
            expected_draft_version=1,
        )
        session.commit()

        assert cancelled.id == receipt_id
        assert cancelled.status == "CANCELLED"
        assert cancelled.draft_version == 2
        assert cancelled.closed_by == 1
        assert cancelled.closed_at is not None
        assert cancelled.total_vnd == 380_000
        assert len(cancelled.items) == 2

        # Verify DB directly
        db_receipt = session.get(PurchaseReceipt, receipt_id)
        assert db_receipt is not None
        assert db_receipt.status == "CANCELLED"
        assert db_receipt.draft_version == 2
        assert db_receipt.closed_by == 1
        assert db_receipt.closed_at is not None

        # Verify inventory was NOT mutated
        invs = list(session.scalars(select(Inventory).order_by(Inventory.product_id)))
        assert [i.quantity for i in invs] == [0, 0]
        assert [i.stock_version for i in invs] == [0, 0]


def test_cancel_draft_stale_version_raises_409():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=2, unit_cost_vnd=30_000)
            ],
        )
        session.commit()
        receipt_id = created.id

    with Session(engine) as session:
        with pytest.raises(ConflictError) as exc_info:
            service.cancel_draft(
                session,
                actor_id=1,
                receipt_id=receipt_id,
                expected_draft_version=99,
            )
        assert exc_info.value.code == "RECEIPT_VERSION_CONFLICT"
        assert exc_info.value.details["current_draft_version"] == 1
        assert exc_info.value.details["expected_draft_version"] == 99

        # Ensure still DRAFT
        current = session.get(PurchaseReceipt, receipt_id)
        assert current is not None
        assert current.status == "DRAFT"
        assert current.draft_version == 1


def test_cancel_draft_terminal_status_raises_409():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=10_000)
            ],
        )
        session.commit()
        receipt_id = created.id

        # Cancel once
        service.cancel_draft(
            session,
            actor_id=1,
            receipt_id=receipt_id,
            expected_draft_version=1,
        )
        session.commit()

        # Try to cancel again
        with pytest.raises(InvalidStateError) as exc_info:
            service.cancel_draft(
                session,
                actor_id=1,
                receipt_id=receipt_id,
                expected_draft_version=2,
            )
        assert "Không thể hủy phiếu nhập đã ở trạng thái CANCELLED" in str(
            exc_info.value
        )


def test_cancel_draft_not_found_raises_404():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        seed_entities(session)
        with pytest.raises(ResourceNotFoundError) as exc_info:
            service.cancel_draft(
                session,
                actor_id=1,
                receipt_id=999_999,
                expected_draft_version=1,
            )
        assert "không tồn tại" in str(exc_info.value)


def test_list_receipts_filters_and_pagination():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, prod2 = seed_entities(session)
        now = datetime.now(UTC).replace(tzinfo=None)
        supplier2 = Supplier(
            name="Nhà cung cấp Phụ",
            contact_email="sup2@example.com",
            contact_phone="0987654321",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(supplier2)
        session.flush()

        # Create 3 receipts:
        # r1: supplier 1, DRAFT
        r1 = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=10_000)
            ],
        )
        # r2: supplier 1, CANCELLED
        r2 = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod2.id, quantity=2, unit_cost_vnd=20_000)
            ],
        )
        service.cancel_draft(
            session,
            actor_id=1,
            receipt_id=r2.id,
            expected_draft_version=1,
        )
        # r3: supplier 2, DRAFT
        r3 = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier2.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=3, unit_cost_vnd=30_000)
            ],
        )
        session.commit()

        # Test pagination: page=1, page_size=2
        page1 = service.list_receipts(session, page=1, page_size=2)
        assert page1.total == 3
        assert page1.page == 1
        assert page1.page_size == 2
        assert len(page1.items) == 2
        assert page1.items[0].id == r3.id
        assert page1.items[1].id == r2.id

        # Page 2
        page2 = service.list_receipts(session, page=2, page_size=2)
        assert page2.total == 3
        assert page2.page == 2
        assert len(page2.items) == 1
        assert page2.items[0].id == r1.id

        # Test status filter: CANCELLED
        cancelled_page = service.list_receipts(session, status="CANCELLED")
        assert cancelled_page.total == 1
        assert cancelled_page.items[0].id == r2.id
        assert cancelled_page.items[0].status == "CANCELLED"

        # Test status filter: DRAFT
        draft_page = service.list_receipts(session, status="DRAFT")
        assert draft_page.total == 2
        assert {item.id for item in draft_page.items} == {r1.id, r3.id}

        # Test supplier_id filter
        sup2_page = service.list_receipts(session, supplier_id=supplier2.id)
        assert sup2_page.total == 1
        assert sup2_page.items[0].id == r3.id

        # Test date filter matching today (Vietnam business time)
        today_vn = datetime.now(VN_TZ).date()
        date_page = service.list_receipts(session, from_date=today_vn, to_date=today_vn)
        assert date_page.total == 3
        assert len(date_page.items) == 3

        # Test date filter in the past
        past_date = date(2020, 1, 1)
        past_page = service.list_receipts(
            session, from_date=past_date, to_date=past_date
        )
        assert past_page.total == 0


def test_list_receipts_validation_errors():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        seed_entities(session)

        # from_date > to_date
        with pytest.raises(DomainValidationError) as exc1:
            service.list_receipts(
                session, from_date=date(2026, 12, 1), to_date=date(2026, 11, 1)
            )
        assert "from_date phải nhỏ hơn hoặc bằng to_date" in str(exc1.value)

        # Invalid status
        with pytest.raises(DomainValidationError) as exc2:
            service.list_receipts(session, status="INVALID_STATUS")
        assert "không hợp lệ" in str(exc2.value)

        # Invalid page
        with pytest.raises(DomainValidationError):
            service.list_receipts(session, page=0)

        # Invalid page_size
        with pytest.raises(DomainValidationError):
            service.list_receipts(session, page_size=101)


def test_get_receipt_success_and_not_found():
    engine = make_test_engine()
    service = ReceiptDraftService()

    with Session(engine) as session:
        supplier, prod1, _ = seed_entities(session)
        created = service.create_draft(
            session,
            actor_id=1,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=4, unit_cost_vnd=25_000)
            ],
        )
        session.commit()

        # Success
        fetched = service.get_receipt(session, receipt_id=created.id)
        assert fetched.id == created.id
        assert fetched.supplier_id == supplier.id
        assert fetched.total_vnd == 100_000
        assert len(fetched.items) == 1
        assert fetched.items[0].product_id == prod1.id

        # Not found
        with pytest.raises(ResourceNotFoundError) as exc_info:
            service.get_receipt(session, receipt_id=987_654)
        assert "không tồn tại" in str(exc_info.value)
