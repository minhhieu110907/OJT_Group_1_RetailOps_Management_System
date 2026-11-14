"""Domain service for atomic Purchase Receipt confirmation (PUR-03 / ENG-02)."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.modules.idempotency import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
    validate_idempotency_key,
)
from app.modules.inventory.exceptions import InactiveProductStockError
from app.modules.inventory.models import ProductStatus
from app.modules.inventory.schemas import StockLine
from app.modules.inventory.service import InventoryService
from app.modules.purchasing.draft_service import utc_now_naive
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import ReceiptItemRead, ReceiptRead
from app.modules.suppliers.models import Supplier, SupplierStatus


class ReceiptConfirmationService:
    """Confirm DRAFT purchase receipts, increase stock, and log movements atomically."""

    def __init__(
        self,
        inventory: InventoryService | None = None,
        idempotency: IdempotencyExecutor | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._inventory = inventory or InventoryService()
        self._idempotency = idempotency or IdempotencyExecutor()
        self._clock = clock or utc_now_naive

    def confirm_receipt(
        self,
        session: Session,
        *,
        actor_id: int,
        receipt_id: int,
        expected_draft_version: int,
        idempotency_key: str,
    ) -> ReceiptRead:
        """Confirm a DRAFT purchase receipt within a single idempotent transaction."""
        clean_key = validate_idempotency_key(idempotency_key)

        def _command() -> CommandOutcome[dict[str, object]]:
            receipt = session.scalar(
                select(PurchaseReceipt)
                .where(PurchaseReceipt.id == receipt_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if receipt is None:
                raise ResourceNotFoundError(
                    f"Phiếu nhập ID {receipt_id} không tồn tại."
                )

            if receipt.draft_version != expected_draft_version:
                raise ConflictError(
                    code="RECEIPT_VERSION_CONFLICT",
                    message=(
                        f"Phiên bản nháp không khớp: kỳ vọng {expected_draft_version}, "
                        f"hiện tại là {receipt.draft_version}."
                    ),
                    details={
                        "receipt_id": receipt_id,
                        "current_draft_version": receipt.draft_version,
                        "expected_draft_version": expected_draft_version,
                    },
                )

            if receipt.status != "DRAFT":
                raise InvalidStateError(
                    f"Không thể xác nhận phiếu nhập đã ở trạng thái {receipt.status}."
                )

            supplier = session.get(Supplier, receipt.supplier_id)
            if supplier is None:
                raise ResourceNotFoundError(
                    f"Nhà cung cấp ID {receipt.supplier_id} không tồn tại."
                )
            if str(supplier.status) != SupplierStatus.ACTIVE:
                raise InvalidStateError(
                    f"Nhà cung cấp '{supplier.name}' đang ở trạng thái không hoạt động."
                )

            items = list(
                session.scalars(
                    select(PurchaseReceiptItem)
                    .where(PurchaseReceiptItem.receipt_id == receipt_id)
                    .order_by(PurchaseReceiptItem.product_id.asc())
                )
            )
            if not items:
                raise DomainValidationError(
                    "Phiếu nhập không có dòng sản phẩm nào để xác nhận."
                )

            for item in items:
                if (
                    item.quantity <= 0
                    or item.unit_cost_vnd < 0
                    or item.line_total_vnd != item.quantity * item.unit_cost_vnd
                ):
                    raise DomainValidationError(
                        f"Dòng sản phẩm ID {item.product_id} không hợp lệ."
                    )

            locks = self._inventory.lock_for_mutation(
                session,
                product_ids=[item.product_id for item in items],
            )
            for item in items:
                locked = locks.rows[item.product_id]
                if locked.status != ProductStatus.ACTIVE.value:
                    raise InactiveProductStockError(product_id=item.product_id)

            now = self._clock()
            supplier_name = receipt.supplier_name_snapshot or supplier.name
            stmt = (
                update(PurchaseReceipt)
                .where(
                    PurchaseReceipt.id == receipt_id,
                    PurchaseReceipt.draft_version == expected_draft_version,
                    PurchaseReceipt.status == "DRAFT",
                )
                .values(
                    status="CONFIRMED",
                    draft_version=PurchaseReceipt.draft_version + 1,
                    closed_by=actor_id,
                    closed_at=now,
                    updated_at=now,
                    supplier_name_snapshot=supplier_name,
                )
            )
            result = session.execute(stmt)
            if result.rowcount == 0:
                raise ConflictError(
                    code="RECEIPT_VERSION_CONFLICT",
                    message="Phiếu nhập đã được thay đổi. Vui lòng tải lại.",
                    details={"receipt_id": receipt_id},
                )

            self._inventory.increase_for_receipt(
                session,
                locks=locks,
                receipt_id=receipt_id,
                actor_id=actor_id,
                lines=[
                    StockLine(product_id=item.product_id, quantity=item.quantity)
                    for item in items
                ],
            )

            session.flush()
            session.refresh(receipt)
            receipt_read = ReceiptRead(
                id=receipt.id,
                supplier_id=receipt.supplier_id,
                supplier_name_snapshot=receipt.supplier_name_snapshot,
                status=receipt.status,
                draft_version=receipt.draft_version,
                total_vnd=receipt.total_vnd,
                created_by=receipt.created_by,
                closed_by=receipt.closed_by,
                created_at=receipt.created_at,
                updated_at=receipt.updated_at,
                closed_at=receipt.closed_at,
                items=[
                    ReceiptItemRead(
                        product_id=it.product_id,
                        sku_snapshot=it.sku_snapshot,
                        product_name_snapshot=it.product_name_snapshot,
                        quantity=it.quantity,
                        unit_cost_vnd=it.unit_cost_vnd,
                        line_total_vnd=it.line_total_vnd,
                    )
                    for it in items
                ],
            )
            return CommandOutcome(
                status_code=200,
                body=receipt_read.model_dump(mode="json"),
            )

        outcome = self._idempotency.execute(
            session,
            actor_id=actor_id,
            operation=IdempotencyOperation.CONFIRM_RECEIPT,
            idempotency_key=clean_key,
            request_identity={
                "operation": IdempotencyOperation.CONFIRM_RECEIPT.value,
                "resource_id": receipt_id,
                "body": {"expected_draft_version": expected_draft_version},
            },
            command=_command,
        )
        return ReceiptRead.model_validate(outcome.body)
