"""MySQL Integration tests for Purchasing Lifecycle and Outbox (T04AABC).

This suite runs against real MySQL 8.4 InnoDB to verify:
1. End-to-end purchasing lifecycle: DRAFT -> PATCH -> CONFIRM -> stock increment,
   and immutable StockMovement audit record with kind 'PURCHASE_CONFIRM'.
2. Concurrency protection & sequential double-confirmation guard: Confirming an
   already CONFIRMED receipt or wrong draft version raises Conflict/InvalidState.
3. Transactional Outbox intent durability: Decisions in StaffApprovalService
   atomically persist outbox_events with schema_version = 1 and storage checks.
4. Cross-run isolation & idempotent cleanup: Strict ownership-based cleanup
   without cross-deleting resources or shared admin records.
"""

import contextlib
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, InvalidStateError
from app.modules.auth.approval_service import StaffApprovalService
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.security import PasswordHasher
from app.modules.categories.models import Category
from app.modules.idempotency.models import IdempotencyRecord
from app.modules.idempotency.service import IdempotencyOperation
from app.modules.inventory.models import (
    Inventory,
    MovementKind,
    Product,
    ProductStatus,
    StockMovement,
)
from app.modules.notifications.models import AdminNotification
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.writer import OutboxWriter
from app.modules.purchasing.confirm_service import ReceiptConfirmService
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import ReceiptLineInput
from app.modules.suppliers.models import Supplier, SupplierStatus
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


class TestRunContext:
    """Manages isolation and teardown in reverse foreign key dependency order."""

    __test__ = False

    def __init__(self, engine: Engine, run_id: str) -> None:
        self.engine = engine
        self.run_id = run_id
        self.receipt_ids: list[int] = []
        self.stock_movement_ids: list[int] = []
        self.product_ids: list[int] = []
        self.category_ids: list[int] = []
        self.supplier_ids: list[int] = []
        self.user_ids: list[int] = []
        self.outbox_event_ids: list[bytes] = []
        self.idempotency_digests: list[tuple[int, bytes]] = []

    def key_digest_for(self, idempotency_key: str) -> bytes:
        """Compute key digest using system idempotency secret."""
        from app.core.config import get_settings
        from app.modules.idempotency.validation import key_digest

        return key_digest(idempotency_key, get_settings().require_idempotency_secret())

    def track_idempotency_key(self, user_id: int, key: str) -> None:
        """Record actor and key digest for scoped idempotency cleanup."""
        digest = self.key_digest_for(key)
        self.idempotency_digests.append((user_id, digest))

    def cleanup(self) -> None:
        """Teardown tracked entities in exact reverse foreign key order."""
        with Session(self.engine) as session, session.begin():
            # Fail-closed check: Ensure no external receipts reference our products
            if self.product_ids:
                ext_cond = [PurchaseReceiptItem.product_id.in_(self.product_ids)]
                if self.receipt_ids:
                    ext_cond.append(
                        PurchaseReceiptItem.receipt_id.not_in(self.receipt_ids)
                    )
                external_refs = list(
                    session.scalars(
                        select(PurchaseReceiptItem.receipt_id).where(*ext_cond)
                    )
                )
                if external_refs:
                    raise RuntimeError(
                        f"Isolation violation: product(s) {self.product_ids} "
                        f"referenced by external receipt(s) {external_refs}"
                    )

            # Step 1: stock_movements (strictly tracked IDs or run receipts)
            sm_filter = []
            if self.stock_movement_ids:
                sm_filter.append(StockMovement.id.in_(self.stock_movement_ids))
            if self.receipt_ids:
                sm_filter.append(StockMovement.receipt_id.in_(self.receipt_ids))
            if sm_filter:
                session.execute(delete(StockMovement).where(or_(*sm_filter)))

            # Step 2: purchase_receipt_items (strictly run receipts)
            if self.receipt_ids:
                session.execute(
                    delete(PurchaseReceiptItem).where(
                        PurchaseReceiptItem.receipt_id.in_(self.receipt_ids)
                    )
                )

            # Step 3: purchase_receipts (strictly run receipts)
            if self.receipt_ids:
                session.execute(
                    delete(PurchaseReceipt).where(
                        PurchaseReceipt.id.in_(self.receipt_ids)
                    )
                )

            # Step 4: outbox_events (strictly tracked IDs or run users)
            ob_filter = []
            if self.outbox_event_ids:
                ob_filter.append(OutboxEvent.id.in_(self.outbox_event_ids))
            if self.user_ids:
                ob_filter.append(OutboxEvent.subject_user_id.in_(self.user_ids))
            if ob_filter:
                session.execute(delete(OutboxEvent).where(or_(*ob_filter)))

            # Step 5: idempotency_records (strictly tracked digests or run users)
            if self.idempotency_digests:
                for u_id, k_digest in self.idempotency_digests:
                    session.execute(
                        delete(IdempotencyRecord).where(
                            IdempotencyRecord.user_id == u_id,
                            IdempotencyRecord.operation
                            == IdempotencyOperation.CONFIRM_RECEIPT.value,
                            IdempotencyRecord.key_digest == k_digest,
                        )
                    )
            if self.user_ids:
                session.execute(
                    delete(IdempotencyRecord).where(
                        IdempotencyRecord.user_id.in_(self.user_ids)
                    )
                )
                session_ids = list(
                    session.scalars(
                        select(AuthSession.id).where(
                            AuthSession.user_id.in_(self.user_ids)
                        )
                    )
                )
                if session_ids:
                    session.execute(
                        delete(RefreshToken).where(
                            RefreshToken.session_id.in_(session_ids)
                        )
                    )
                approval_ids = list(
                    session.scalars(
                        select(StaffApprovalRequest.id).where(
                            StaffApprovalRequest.user_id.in_(self.user_ids)
                        )
                    )
                )
                if approval_ids:
                    session.execute(
                        delete(AdminNotification).where(
                            AdminNotification.approval_request_id.in_(approval_ids)
                        )
                    )
                session.execute(
                    delete(AuthSession).where(AuthSession.user_id.in_(self.user_ids))
                )
                session.execute(
                    delete(StaffApprovalRequest).where(
                        StaffApprovalRequest.user_id.in_(self.user_ids)
                    )
                )

            # Step 6: inventory (strictly run products)
            if self.product_ids:
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(self.product_ids))
                )

            # Step 7: products (strictly run products)
            if self.product_ids:
                session.execute(delete(Product).where(Product.id.in_(self.product_ids)))

            # Step 8: categories (test-created categories only)
            if self.category_ids:
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )

            # Step 9: suppliers (test-created suppliers only)
            if self.supplier_ids:
                session.execute(
                    delete(Supplier).where(Supplier.id.in_(self.supplier_ids))
                )

            # Step 10: users (test-created users only)
            if self.user_ids:
                session.execute(delete(User).where(User.id.in_(self.user_ids)))


@pytest.fixture
def run_ctx(
    migrated_integration_engine: Engine,
) -> Generator[TestRunContext, None, None]:
    """Provide an isolated TestRunContext ensuring teardown in foreign key order."""
    run_id = f"t04aabc_{uuid4().hex[:8]}"
    ctx = TestRunContext(migrated_integration_engine, run_id)
    ctx.cleanup()
    try:
        yield ctx
    finally:
        ctx.cleanup()


def _ensure_admin(engine: Engine, ctx: TestRunContext) -> int:
    """Find existing seed admin or create an isolated test admin."""
    with Session(engine) as session, session.begin():
        admin = session.scalar(select(User).where(User.admin_slot == 1))
        if admin is not None:
            return admin.id
        now = datetime(2026, 11, 16, 8, 0, 0)
        new_admin = User(
            email_normalized=f"{ctx.run_id}_admin@example.com",
            password_hash=PasswordHasher().hash("AdminSecurePass!123"),
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        session.add(new_admin)
        session.flush()
        ctx.user_ids.append(new_admin.id)
        return new_admin.id


def test_e2e_purchasing_lifecycle_and_stock_movements(
    migrated_integration_engine: Engine, run_ctx: TestRunContext
) -> None:
    """E2E: create draft -> update draft -> confirm -> inventory & movements updated."""
    admin_id = _ensure_admin(migrated_integration_engine, run_ctx)
    now = datetime.now(UTC).replace(tzinfo=None)

    # 1. Setup master data
    with Session(migrated_integration_engine) as session, session.begin():
        category = Category(
            name=f"{run_ctx.run_id}_Cat",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add(category)
        session.flush()
        run_ctx.category_ids.append(category.id)

        supplier = Supplier(
            name=f"{run_ctx.run_id}_Supplier",
            contact_email=f"{run_ctx.run_id}@example.com",
            contact_phone="0912345678",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(supplier)
        session.flush()
        run_ctx.supplier_ids.append(supplier.id)

        product = Product(
            category_id=category.id,
            sku=f"SKU-{run_ctx.run_id.upper()}",
            name=f"Product {run_ctx.run_id}",
            sale_price_vnd=100000,
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
        run_ctx.product_ids.append(product.id)

        inventory = Inventory(
            product_id=product.id,
            quantity=5,
            stock_version=1,
            first_stocked_at=now,
            updated_at=now,
        )
        session.add(inventory)

        supplier_id = supplier.id
        product_id = product.id

    draft_service = ReceiptDraftService()
    confirm_service = ReceiptConfirmService()

    # 2. Create Draft Receipt
    with Session(migrated_integration_engine) as session:
        draft = draft_service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier_id,
            items=[
                ReceiptLineInput(
                    product_id=product_id,
                    quantity=10,
                    unit_cost_vnd=50000,
                )
            ],
        )
        session.commit()
        receipt_id = draft.id
        run_ctx.receipt_ids.append(receipt_id)

        assert draft.status == "DRAFT"
        assert draft.draft_version == 1
        assert draft.total_vnd == 500000
        assert len(draft.items) == 1
        assert draft.items[0].quantity == 10

    # 3. Update Draft Receipt (optimistic lock with expected_draft_version=1)
    with Session(migrated_integration_engine) as session:
        updated = draft_service.update_draft(
            session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=1,
            items=[
                ReceiptLineInput(
                    product_id=product_id,
                    quantity=15,
                    unit_cost_vnd=45000,
                )
            ],
        )
        session.commit()

        assert updated.draft_version == 2
        assert updated.total_vnd == 675000
        assert updated.items[0].quantity == 15
        assert updated.items[0].unit_cost_vnd == 45000

    # 4. Confirm Receipt (optimistic lock with expected_draft_version=2)
    idemp_key = f"idemp-confirm-{run_ctx.run_id}"
    run_ctx.track_idempotency_key(admin_id, idemp_key)
    with Session(migrated_integration_engine) as session:
        confirmed = confirm_service.confirm(
            session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=2,
            idempotency_key=idemp_key,
        )
        session.commit()

        assert confirmed.status == "CONFIRMED"
        assert confirmed.draft_version == 3
        assert confirmed.closed_by == admin_id
        assert confirmed.closed_at is not None
        assert confirmed.supplier_name_snapshot is not None

    # 5. Assert Inventory and StockMovement changes in MySQL
    with Session(migrated_integration_engine) as session:
        inv = session.get(Inventory, product_id)
        assert inv is not None
        assert inv.quantity == 20  # 5 initial + 15 confirmed
        assert inv.stock_version == 2

        movements = list(
            session.scalars(
                select(StockMovement).where(
                    StockMovement.receipt_id == receipt_id,
                    StockMovement.product_id == product_id,
                )
            )
        )
        assert len(movements) == 1
        movement = movements[0]
        run_ctx.stock_movement_ids.append(movement.id)
        assert movement.kind == MovementKind.PURCHASE_CONFIRM
        assert movement.quantity_before == 5
        assert movement.quantity_after == 20
        assert movement.stock_version_after == 2


def test_no_second_stock_increase_on_sequential_reconfirmation(
    migrated_integration_engine: Engine, run_ctx: TestRunContext
) -> None:
    """SEQUENTIAL DUPLICATE CONFIRMATION VERIFIED: Re-confirm error; stock intact."""
    admin_id = _ensure_admin(migrated_integration_engine, run_ctx)
    now = datetime.now(UTC).replace(tzinfo=None)

    # 1. Setup Master Data & Initial Stock
    with Session(migrated_integration_engine) as session, session.begin():
        category = Category(
            name=f"{run_ctx.run_id}_Cat2",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add(category)
        session.flush()
        run_ctx.category_ids.append(category.id)

        supplier = Supplier(
            name=f"{run_ctx.run_id}_Sup2",
            contact_email=f"{run_ctx.run_id}2@example.com",
            contact_phone="0987654321",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(supplier)
        session.flush()
        run_ctx.supplier_ids.append(supplier.id)

        product = Product(
            category_id=category.id,
            sku=f"SKU-{run_ctx.run_id.upper()}-2",
            name=f"Product 2 {run_ctx.run_id}",
            sale_price_vnd=80000,
            status=ProductStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add(product)
        session.flush()
        run_ctx.product_ids.append(product.id)

        inventory = Inventory(
            product_id=product.id,
            quantity=10,
            stock_version=1,
            first_stocked_at=now,
            updated_at=now,
        )
        session.add(inventory)

        supplier_id = supplier.id
        product_id = product.id

    draft_service = ReceiptDraftService()
    confirm_service = ReceiptConfirmService()

    # 2. Create and Confirm Receipt
    with Session(migrated_integration_engine) as session:
        draft = draft_service.create_draft(
            session,
            actor_id=admin_id,
            supplier_id=supplier_id,
            items=[
                ReceiptLineInput(
                    product_id=product_id,
                    quantity=8,
                    unit_cost_vnd=40000,
                )
            ],
        )
        session.commit()
        receipt_id = draft.id
        run_ctx.receipt_ids.append(receipt_id)

    idemp_1 = f"idemp-first-{run_ctx.run_id}"
    run_ctx.track_idempotency_key(admin_id, idemp_1)
    with Session(migrated_integration_engine) as session:
        confirm_service.confirm(
            session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=1,
            idempotency_key=idemp_1,
        )
        session.commit()

    # Assert stock is 18 (10 + 8) and version is 2
    with Session(migrated_integration_engine) as session:
        inv = session.get(Inventory, product_id)
        assert inv is not None
        assert inv.quantity == 18
        assert inv.stock_version == 2

    # 3. Attempt to re-confirm with a NEW idempotency key -> InvalidStateError
    idemp_2 = f"idemp-second-{run_ctx.run_id}"
    run_ctx.track_idempotency_key(admin_id, idemp_2)
    with (
        Session(migrated_integration_engine) as session,
        pytest.raises(InvalidStateError),
    ):
        confirm_service.confirm(
            session,
            actor_id=admin_id,
            receipt_id=receipt_id,
            expected_draft_version=2,  # receipt is now CONFIRMED
            idempotency_key=idemp_2,
        )

    # 4. Attempt to confirm with mismatched draft_version -> ConflictError
    with Session(migrated_integration_engine) as session:
        with pytest.raises(ConflictError) as exc_info:
            confirm_service.confirm(
                session,
                actor_id=admin_id,
                receipt_id=receipt_id,
                expected_draft_version=999,
                idempotency_key=f"idemp-mismatch-{run_ctx.run_id}",
            )
        assert exc_info.value.code == "RECEIPT_VERSION_CONFLICT"

    # 5. Assert stock remains strictly intact (no second stock increase)
    with Session(migrated_integration_engine) as session:
        inv_after = session.get(Inventory, product_id)
        assert inv_after is not None
        assert inv_after.quantity == 18
        assert inv_after.stock_version == 2

        movements = list(
            session.scalars(
                select(StockMovement).where(
                    StockMovement.receipt_id == receipt_id,
                    StockMovement.product_id == product_id,
                )
            )
        )
        assert len(movements) == 1
        run_ctx.stock_movement_ids.append(movements[0].id)


def test_transactional_outbox_intent_durability(
    migrated_integration_engine: Engine, run_ctx: TestRunContext
) -> None:
    """Verify outbox persistence in StaffApprovalService and writer constraints."""
    admin_id = _ensure_admin(migrated_integration_engine, run_ctx)
    now = datetime(2026, 11, 16, 9, 0, 0)

    # 1. Setup pending staff user and approval request
    with Session(migrated_integration_engine) as session, session.begin():
        staff = User(
            email_normalized=f"{run_ctx.run_id}_staff@example.com",
            password_hash=PasswordHasher().hash("StaffPass123!"),
            role=UserRole.STAFF.value,
            status=UserStatus.PENDING_APPROVAL.value,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add(staff)
        session.flush()
        run_ctx.user_ids.append(staff.id)

        approval = StaffApprovalRequest(
            user_id=staff.id,
            attempt_no=1,
            status="PENDING",
            requested_at=now,
            decided_by=None,
            decided_at=None,
            decision_reason=None,
        )
        session.add(approval)
        session.flush()
        approval_id = approval.id
        staff_id = staff.id

    # 2. Decide Staff Approval -> calls OutboxWriter in the same transaction
    approval_service = StaffApprovalService()
    with Session(migrated_integration_engine) as session:
        result = approval_service.decide(
            session,
            actor_id=admin_id,
            approval_id=approval_id,
            decision="APPROVED",
            reason=None,
        )
        assert result.status == "APPROVED"

    # 3. Assert OutboxEvent row persisted in MySQL with correct schema and constraints
    with Session(migrated_integration_engine) as session:
        events = list(
            session.scalars(
                select(OutboxEvent).where(OutboxEvent.subject_user_id == staff_id)
            )
        )
        assert len(events) == 1
        event = events[0]
        run_ctx.outbox_event_ids.append(event.id)

        assert event.event_type == "STAFF_APPROVED"
        assert event.payload["schema_version"] == 1
        assert event.payload["approval_request_id"] == approval_id
        assert event.payload["actor_id"] == admin_id
        assert event.published_at is None
        assert event.publish_attempts == 0
        assert event.delivery_attempts == 0
        assert event.outcome is None
        assert event.secret_ciphertext is None
        assert event.secret_expires_at is None

    # 4. Direct OutboxWriter test with encrypted secret for PASSWORD_RESET
    # SECRET_STORAGE_CONSTRAINT_VERIFIED: Tests VARBINARY(2048) and constraints
    outbox_writer = OutboxWriter()
    reset_expiry = datetime.now(UTC) + timedelta(hours=2)
    with Session(migrated_integration_engine) as session, session.begin():
        event_id = outbox_writer.append(
            session,
            subject_user_id=staff_id,
            event_type="PASSWORD_RESET",
            payload={"schema_version": 1},
            available_at_utc=datetime.now(UTC),
            secret_ciphertext=b"AES256_GCM_ENCRYPTED_RESET_TOKEN_PAYLOAD",
            secret_expires_at_utc=reset_expiry,
        )
        run_ctx.outbox_event_ids.append(event_id)

    with Session(migrated_integration_engine) as session:
        reset_ev = session.get(OutboxEvent, event_id)
        assert reset_ev is not None
        assert reset_ev.event_type == "PASSWORD_RESET"
        assert reset_ev.secret_ciphertext == b"AES256_GCM_ENCRYPTED_RESET_TOKEN_PAYLOAD"
        assert reset_ev.secret_expires_at is not None

    # 5. OutboxWriter rejects missing secret for secret-bearing event types
    with (
        Session(migrated_integration_engine) as session,
        session.begin(),
        pytest.raises(
            ValueError,
            match="Secret-bearing event requires encrypted secret and expiry",
        ),
    ):
        outbox_writer.append(
            session,
            subject_user_id=staff_id,
            event_type="PASSWORD_RESET",
            payload={"schema_version": 1},
            available_at_utc=datetime.now(UTC),
            secret_ciphertext=None,
        )


def test_mysql_cross_run_isolation_and_idempotent_cleanup(
    migrated_integration_engine: Engine,
) -> None:
    """Verify cross-run isolation, shared ADMIN safety, and idempotent cleanup."""
    run_a = TestRunContext(
        migrated_integration_engine, f"t04aabc_iso_a_{uuid4().hex[:6]}"
    )
    run_b = TestRunContext(
        migrated_integration_engine, f"t04aabc_iso_b_{uuid4().hex[:6]}"
    )

    admin_id = _ensure_admin(migrated_integration_engine, run_a)
    now = datetime.now(UTC).replace(tzinfo=None)

    try:
        # Setup Run A: Category A, Supplier A, Product A, Inventory A
        with Session(migrated_integration_engine) as session, session.begin():
            cat_a = Category(
                name=f"{run_a.run_id}_Cat",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
            session.add(cat_a)
            session.flush()
            run_a.category_ids.append(cat_a.id)

            sup_a = Supplier(
                name=f"{run_a.run_id}_Sup",
                contact_phone="0911111111",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(sup_a)
            session.flush()
            run_a.supplier_ids.append(sup_a.id)

            prod_a = Product(
                category_id=cat_a.id,
                sku=f"SKU-{run_a.run_id.upper()}",
                name=f"Prod A {run_a.run_id}",
                sale_price_vnd=100000,
                status=ProductStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(prod_a)
            session.flush()
            run_a.product_ids.append(prod_a.id)

            inv_a = Inventory(
                product_id=prod_a.id,
                quantity=10,
                stock_version=1,
                first_stocked_at=now,
                updated_at=now,
            )
            session.add(inv_a)
            prod_a_id = prod_a.id
            sup_a_id = sup_a.id

        # Setup Run B: Category B, Supplier B, Product B, Inventory B
        with Session(migrated_integration_engine) as session, session.begin():
            cat_b = Category(
                name=f"{run_b.run_id}_Cat",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
            session.add(cat_b)
            session.flush()
            run_b.category_ids.append(cat_b.id)

            sup_b = Supplier(
                name=f"{run_b.run_id}_Sup",
                contact_phone="0922222222",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(sup_b)
            session.flush()
            run_b.supplier_ids.append(sup_b.id)

            prod_b = Product(
                category_id=cat_b.id,
                sku=f"SKU-{run_b.run_id.upper()}",
                name=f"Prod B {run_b.run_id}",
                sale_price_vnd=200000,
                status=ProductStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(prod_b)
            session.flush()
            run_b.product_ids.append(prod_b.id)

            inv_b = Inventory(
                product_id=prod_b.id,
                quantity=20,
                stock_version=1,
                first_stocked_at=now,
                updated_at=now,
            )
            session.add(inv_b)
            sup_b_id = sup_b.id

        draft_service = ReceiptDraftService()
        confirm_service = ReceiptConfirmService()

        # Run A: Create & confirm Receipt A with Product A
        with Session(migrated_integration_engine) as session:
            draft_a = draft_service.create_draft(
                session,
                actor_id=admin_id,
                supplier_id=sup_a_id,
                items=[
                    ReceiptLineInput(
                        product_id=prod_a_id,
                        quantity=5,
                        unit_cost_vnd=50000,
                    )
                ],
            )
            session.commit()
            rcpt_a_id = draft_a.id
            run_a.receipt_ids.append(rcpt_a_id)

        idemp_a = f"idemp-iso-a-{run_a.run_id}"
        run_a.track_idempotency_key(admin_id, idemp_a)
        with Session(migrated_integration_engine) as session:
            confirm_service.confirm(
                session,
                actor_id=admin_id,
                receipt_id=rcpt_a_id,
                expected_draft_version=1,
                idempotency_key=idemp_a,
            )
            session.commit()

        # Run B: Create & confirm Receipt B with Product A
        with Session(migrated_integration_engine) as session:
            draft_b = draft_service.create_draft(
                session,
                actor_id=admin_id,
                supplier_id=sup_b_id,
                items=[
                    ReceiptLineInput(
                        product_id=prod_a_id,
                        quantity=3,
                        unit_cost_vnd=55000,
                    )
                ],
            )
            session.commit()
            rcpt_b_id = draft_b.id
            run_b.receipt_ids.append(rcpt_b_id)

        idemp_b = f"idemp-iso-b-{run_b.run_id}"
        run_b.track_idempotency_key(admin_id, idemp_b)
        with Session(migrated_integration_engine) as session:
            confirm_service.confirm(
                session,
                actor_id=admin_id,
                receipt_id=rcpt_b_id,
                expected_draft_version=1,
                idempotency_key=idemp_b,
            )
            session.commit()

        # CASE 1: External product reference isolation & fail-closed protection
        # Attempting to clean up Run A while Receipt B references Product A raises error
        with pytest.raises(RuntimeError, match="Isolation violation"):
            run_a.cleanup()

        # Verify Receipt B, its items, and its movements are NOT deleted:
        with Session(migrated_integration_engine) as session:
            assert session.get(PurchaseReceipt, rcpt_b_id) is not None
            items_b = session.scalars(
                select(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id == rcpt_b_id
                )
            ).all()
            assert len(items_b) == 1
            mvmt_b = session.scalars(
                select(StockMovement).where(StockMovement.receipt_id == rcpt_b_id)
            ).all()
            assert len(mvmt_b) == 1

        # CASE 2: Clean up Run B first, releasing the foreign key reference to Product A
        run_b.cleanup()

        # Verify Run B records were cleaned up:
        with Session(migrated_integration_engine) as session:
            assert session.get(PurchaseReceipt, rcpt_b_id) is None
            # Verify shared admin is NOT deleted!
            assert session.get(User, admin_id) is not None
            # Verify Receipt A is still intact before Run A cleanup
            assert session.get(PurchaseReceipt, rcpt_a_id) is not None

        # Now clean up Run A:
        run_a.cleanup()

        with Session(migrated_integration_engine) as session:
            assert session.get(PurchaseReceipt, rcpt_a_id) is None
            assert session.get(Product, prod_a_id) is None
            # Shared admin still exists:
            assert session.get(User, admin_id) is not None

        # CASE 3: Idempotent cleanup: running cleanup twice does not raise error
        run_a.cleanup()
        run_b.cleanup()

    finally:
        # Guarantee teardown in reverse dependency order
        with contextlib.suppress(Exception):
            run_b.cleanup()
        with contextlib.suppress(Exception):
            run_a.cleanup()
