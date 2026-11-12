"""MySQL integration tests for Purchase Receipt draft lifecycle and concurrency."""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    InvalidStateError,
)
from app.db.base import Base
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import ReceiptLineInput
from app.modules.suppliers.models import Supplier, SupplierStatus

pytestmark = pytest.mark.integration

RECEIPT_TEST_PREFIX = "T04A6D7_"


def unique_token(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:8]}"


def get_or_create_test_admin(session: Session) -> User:
    admin = session.scalar(select(User).where(User.admin_slot == 1))
    if admin is None:
        now = datetime.now(UTC).replace(tzinfo=None)
        admin = User(
            email_normalized=f"{RECEIPT_TEST_PREFIX}admin@example.com",
            password_hash="$2b$04$sentinel.receipt.admin.hash.do.not.mutate",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            admin_slot=1,
            last_reapplied_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin)
        session.flush()
    return admin


@pytest.fixture(autouse=True)
def setup_and_teardown_receipt_tables(
    migrated_integration_engine: Engine,
) -> Iterator[None]:
    """Ensure purchase receipt tables exist and clean up test rows after each test."""
    Base.metadata.create_all(
        migrated_integration_engine,
        tables=[PurchaseReceipt.__table__, PurchaseReceiptItem.__table__],
    )
    with Session(migrated_integration_engine) as session, session.begin():
        get_or_create_test_admin(session)
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        # Clean up receipts created in test
        receipt_ids = list(
            session.scalars(
                select(PurchaseReceipt.id)
                .join(Supplier, PurchaseReceipt.supplier_id == Supplier.id)
                .where(Supplier.name.like(f"{RECEIPT_TEST_PREFIX}%"))
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
        prod_ids = list(
            session.scalars(
                select(Product.id).where(Product.sku.like(f"{RECEIPT_TEST_PREFIX}%"))
            )
        )
        if prod_ids:
            session.execute(delete(Inventory).where(Inventory.product_id.in_(prod_ids)))
            session.execute(delete(Product).where(Product.id.in_(prod_ids)))
        session.execute(
            delete(Supplier).where(Supplier.name.like(f"{RECEIPT_TEST_PREFIX}%"))
        )
        session.execute(
            delete(Category).where(Category.name.like(f"{RECEIPT_TEST_PREFIX}%"))
        )
        session.execute(
            delete(User).where(User.email_normalized.like(f"{RECEIPT_TEST_PREFIX}%"))
        )


def seed_mysql_entities(
    session: Session,
) -> tuple[int, Supplier, Product, Product, Inventory]:
    admin = get_or_create_test_admin(session)
    admin_id = admin.id
    now = datetime.now(UTC).replace(tzinfo=None)
    category = Category(
        name=unique_token(f"{RECEIPT_TEST_PREFIX}CAT_"),
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(category)
    session.flush()

    supplier = Supplier(
        name=unique_token(f"{RECEIPT_TEST_PREFIX}SUP_"),
        contact_email="mysql_sup@example.com",
        contact_phone="0911223344",
        status=SupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    session.add(supplier)
    session.flush()

    prod1 = Product(
        category_id=category.id,
        sku=unique_token(f"{RECEIPT_TEST_PREFIX}SKU1_"),
        name="Sản phẩm MySQL 1",
        status=CatalogStatus.ACTIVE,
        sale_price_vnd=100_000,
        created_at=now,
        updated_at=now,
    )
    prod2 = Product(
        category_id=category.id,
        sku=unique_token(f"{RECEIPT_TEST_PREFIX}SKU2_"),
        name="Sản phẩm MySQL 2",
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
    return admin_id, supplier, prod1, prod2, inv1


def test_mysql_create_draft_atomically_merges_items_without_inventory_mutation(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, prod2, inv1 = seed_mysql_entities(session)
        supplier_id = supplier.id
        prod1_id = prod1.id
        prod2_id = prod2.id

    with Session(migrated_integration_engine) as action_session:
        created = service.create_draft(
            action_session,
            actor_id=admin_id,
            supplier_id=supplier_id,
            items=[
                ReceiptLineInput(product_id=prod1_id, quantity=3, unit_cost_vnd=60_000),
                ReceiptLineInput(product_id=prod2_id, quantity=2, unit_cost_vnd=90_000),
                ReceiptLineInput(product_id=prod1_id, quantity=2, unit_cost_vnd=60_000),
            ],
        )
        action_session.commit()
        receipt_id = created.id

    with Session(migrated_integration_engine) as verify_session:
        db_receipt = verify_session.get(PurchaseReceipt, receipt_id)
        assert db_receipt is not None
        assert db_receipt.status == "DRAFT"
        assert db_receipt.draft_version == 1
        assert db_receipt.total_vnd == 480_000  # 5 * 60k + 2 * 90k = 480k

        items = list(
            verify_session.scalars(
                select(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id == receipt_id
                )
            )
        )
        assert len(items) == 2
        item1 = next(it for it in items if it.product_id == prod1_id)
        assert item1.quantity == 5
        assert item1.unit_cost_vnd == 60_000
        assert item1.line_total_vnd == 300_000

        # Verify inventory unchanged
        inv_check = verify_session.scalar(
            select(Inventory).where(Inventory.product_id == prod1_id)
        )
        assert inv_check is not None
        assert inv_check.quantity == 0
        assert inv_check.stock_version == 0


def test_mysql_cost_conflict_rolls_back_without_orphan_receipt(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, _, _ = seed_mysql_entities(session)
        supplier_id = supplier.id
        prod1_id = prod1.id

    with Session(migrated_integration_engine) as action_session:
        with pytest.raises(DomainValidationError) as exc_info:
            service.create_draft(
                action_session,
                actor_id=admin_id,
                supplier_id=supplier_id,
                items=[
                    ReceiptLineInput(
                        product_id=prod1_id, quantity=2, unit_cost_vnd=50_000
                    ),
                    ReceiptLineInput(
                        product_id=prod1_id, quantity=3, unit_cost_vnd=55_000
                    ),
                ],
            )
        assert exc_info.value.details.get("code") == "RECEIPT_ITEM_COST_CONFLICT"
        action_session.rollback()

    with Session(migrated_integration_engine) as verify_session:
        orphan = verify_session.scalar(
            select(PurchaseReceipt).where(PurchaseReceipt.supplier_id == supplier_id)
        )
        assert orphan is None


def test_mysql_concurrent_update_optimistic_locking_only_one_wins(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, prod2, _ = seed_mysql_entities(session)
        created = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=40_000)
            ],
        )
        session.commit()
        receipt_id = created.id
        prod2_id = prod2.id

    barrier = threading.Barrier(2)

    def worker(worker_id: int) -> str:
        barrier.wait()
        with Session(migrated_integration_engine) as worker_session:
            try:
                service.update_draft(
                    worker_session,
                    actor_id=admin_id,
                    receipt_id=receipt_id,
                    expected_draft_version=1,
                    items=[
                        ReceiptLineInput(
                            product_id=prod2_id,
                            quantity=worker_id + 1,
                            unit_cost_vnd=70_000,
                        )
                    ],
                )
                worker_session.commit()
                return "success"
            except ConflictError as e:
                worker_session.rollback()
                if e.code == "RECEIPT_VERSION_CONFLICT":
                    return "version_conflict"
                return "other_conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))

    # In optimistic locking, exactly one worker must succeed, and one must get conflict
    assert sorted(outcomes) == ["success", "version_conflict"]

    with Session(migrated_integration_engine) as verify_session:
        receipt = verify_session.get(PurchaseReceipt, receipt_id)
        assert receipt is not None
        assert receipt.draft_version == 2


def test_mysql_cancel_draft_without_inventory_mutation(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, prod2, _ = seed_mysql_entities(session)
        created = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=4, unit_cost_vnd=50_000),
                ReceiptLineInput(product_id=prod2.id, quantity=2, unit_cost_vnd=80_000),
            ],
        )
        session.commit()
        receipt_id = created.id

    with Session(migrated_integration_engine) as action_session:
        cancelled = service.cancel_draft(
            action_session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=1,
        )
        action_session.commit()
        assert cancelled.status == "CANCELLED"
        assert cancelled.draft_version == 2
        assert cancelled.closed_by == admin_id
        assert cancelled.closed_at is not None

    with Session(migrated_integration_engine) as verify_session:
        db_receipt = verify_session.get(PurchaseReceipt, receipt_id)
        assert db_receipt is not None
        assert db_receipt.status == "CANCELLED"
        assert db_receipt.draft_version == 2
        assert db_receipt.closed_by == admin_id
        assert db_receipt.closed_at is not None
        assert db_receipt.total_vnd == 360_000

        # Verify inventory unchanged
        inv1 = verify_session.scalar(
            select(Inventory).where(Inventory.product_id == prod1.id)
        )
        assert inv1 is not None
        assert inv1.quantity == 0
        assert inv1.stock_version == 0

        inv2 = verify_session.scalar(
            select(Inventory).where(Inventory.product_id == prod2.id)
        )
        assert inv2 is not None
        assert inv2.quantity == 0
        assert inv2.stock_version == 0


def test_mysql_cancel_draft_concurrent_optimistic_locking_only_one_wins(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, _, _ = seed_mysql_entities(session)
        created = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=50_000)
            ],
        )
        session.commit()
        receipt_id = created.id

    barrier = threading.Barrier(2)

    def worker(_worker_id: int) -> str:
        barrier.wait()
        with Session(migrated_integration_engine) as worker_session:
            try:
                service.cancel_draft(
                    worker_session,
                    actor_id=admin_id,
                    receipt_id=receipt_id,
                    expected_draft_version=1,
                )
                worker_session.commit()
                return "success"
            except ConflictError as e:
                worker_session.rollback()
                if e.code == "RECEIPT_VERSION_CONFLICT":
                    return "version_conflict"
                return "other_conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(worker, range(2)))

    assert sorted(outcomes) == ["success", "version_conflict"]

    with Session(migrated_integration_engine) as verify_session:
        receipt = verify_session.get(PurchaseReceipt, receipt_id)
        assert receipt is not None
        assert receipt.status == "CANCELLED"
        assert receipt.draft_version == 2


def test_mysql_cancel_draft_terminal_immutable(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, _, _ = seed_mysql_entities(session)
        created = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=20_000)
            ],
        )
        session.commit()
        receipt_id = created.id

    with Session(migrated_integration_engine) as action_session:
        service.cancel_draft(
            action_session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=1,
        )
        action_session.commit()

    with Session(migrated_integration_engine) as action_session:
        with pytest.raises(InvalidStateError) as exc_info:
            service.cancel_draft(
                action_session,
                actor_id=admin_id,
                receipt_id=receipt_id,
                expected_draft_version=2,
            )
        assert "CANCELLED" in str(exc_info.value)


def test_mysql_list_and_get_receipts(
    migrated_integration_engine: Engine,
) -> None:
    service = ReceiptDraftService()
    with Session(migrated_integration_engine) as session:
        admin_id, supplier, prod1, prod2, _ = seed_mysql_entities(session)

        r1 = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod1.id, quantity=1, unit_cost_vnd=10_000)
            ],
        )
        r2 = service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier.id,
            items=[
                ReceiptLineInput(product_id=prod2.id, quantity=2, unit_cost_vnd=20_000)
            ],
        )
        service.cancel_draft(
            session,
            actor_id=admin_id,
            receipt_id=r2.id,
            expected_draft_version=1,
        )
        session.commit()

        # Query list on MySQL
        page = service.list_receipts(session, supplier_id=supplier.id)
        assert page.total >= 2
        returned_ids = [it.id for it in page.items]
        assert r1.id in returned_ids
        assert r2.id in returned_ids

        # Query get single
        single = service.get_receipt(session, receipt_id=r1.id)
        assert single.id == r1.id
        assert single.status == "DRAFT"
        assert len(single.items) == 1
        assert single.items[0].product_id == prod1.id
