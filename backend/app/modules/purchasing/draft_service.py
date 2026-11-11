"""Domain service for Purchase Receipt draft creation and updates."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.modules.products.models import CatalogStatus, Product
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.purchasing.schemas import (
    ReceiptItemRead,
    ReceiptLineInput,
    ReceiptRead,
)
from app.modules.suppliers.models import Supplier, SupplierStatus


def utc_now_naive() -> datetime:
    """Return the current UTC timestamp without timezone info for MySQL DATETIME(6)."""
    return datetime.now(UTC).replace(tzinfo=None)


class ReceiptDraftService:
    """Manages draft lifecycle: creation, item normalization, conflict, and update."""

    def _process_items(
        self, session: Session, items: Sequence[ReceiptLineInput]
    ) -> tuple[list[dict[str, Any]], int]:
        """Validate, merge identical lines, detect cost conflicts, and snapshot."""
        if not items:
            raise DomainValidationError("Danh sách sản phẩm không được rỗng.")

        product_costs: dict[int, int] = {}
        product_quantities: dict[int, int] = {}

        for item in items:
            pid = item.product_id
            cost = item.unit_cost_vnd
            if pid in product_costs and product_costs[pid] != cost:
                raise ConflictError(
                    code="RECEIPT_ITEM_COST_CONFLICT",
                    message=(
                        f"Sản phẩm ID {pid} có nhiều đơn giá khác nhau trong "
                        f"cùng một phiếu ({product_costs[pid]} và {cost})."
                    ),
                    details={
                        "product_id": pid,
                        "existing_unit_cost_vnd": product_costs[pid],
                        "conflicting_unit_cost_vnd": cost,
                    },
                )
            product_costs[pid] = cost
            product_quantities[pid] = product_quantities.get(pid, 0) + item.quantity

        product_ids = list(product_quantities.keys())
        products = list(
            session.scalars(select(Product).where(Product.id.in_(product_ids)))
        )
        products_by_id = {p.id: p for p in products}

        for pid in product_ids:
            if pid not in products_by_id:
                raise ResourceNotFoundError(f"Sản phẩm ID {pid} không tồn tại.")
            prod = products_by_id[pid]
            if str(prod.status) != CatalogStatus.ACTIVE:
                raise DomainValidationError(
                    f"Sản phẩm '{prod.name}' (ID {pid}) đang ở trạng thái "
                    "không hoạt động."
                )

        processed_lines: list[dict[str, Any]] = []
        total_vnd = 0
        for pid in product_ids:
            prod = products_by_id[pid]
            qty = product_quantities[pid]
            cost = product_costs[pid]
            line_total = qty * cost
            total_vnd += line_total
            processed_lines.append(
                {
                    "product_id": pid,
                    "sku_snapshot": prod.sku,
                    "product_name_snapshot": prod.name,
                    "quantity": qty,
                    "unit_cost_vnd": cost,
                    "line_total_vnd": line_total,
                }
            )

        return processed_lines, total_vnd

    def _to_receipt_read(
        self, receipt: PurchaseReceipt, items: Sequence[PurchaseReceiptItem]
    ) -> ReceiptRead:
        """Convert ORM entities to ReceiptRead response DTO."""
        return ReceiptRead(
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

    def create_draft(
        self,
        session: Session,
        *,
        actor_id: int,
        supplier_id: int,
        items: Sequence[ReceiptLineInput],
    ) -> ReceiptRead:
        """Create a new purchase receipt in DRAFT status without mutating inventory."""
        supplier = session.get(Supplier, supplier_id)
        if supplier is None:
            raise ResourceNotFoundError(
                f"Nhà cung cấp ID {supplier_id} không tồn tại."
            )
        if str(supplier.status) != SupplierStatus.ACTIVE:
            raise DomainValidationError(
                f"Nhà cung cấp '{supplier.name}' đang ở trạng thái không hoạt động."
            )

        lines, total_vnd = self._process_items(session, items)
        now = utc_now_naive()

        receipt = PurchaseReceipt(
            supplier_id=supplier_id,
            supplier_name_snapshot=supplier.name,
            status="DRAFT",
            draft_version=1,
            total_vnd=total_vnd,
            created_by=actor_id,
            closed_by=None,
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        session.add(receipt)
        session.flush()

        item_rows: list[PurchaseReceiptItem] = []
        for line in lines:
            item_row = PurchaseReceiptItem(
                receipt_id=receipt.id,
                product_id=line["product_id"],
                sku_snapshot=line["sku_snapshot"],
                product_name_snapshot=line["product_name_snapshot"],
                quantity=line["quantity"],
                unit_cost_vnd=line["unit_cost_vnd"],
                line_total_vnd=line["line_total_vnd"],
            )
            session.add(item_row)
            item_rows.append(item_row)

        session.flush()
        return self._to_receipt_read(receipt, item_rows)

    def update_draft(
        self,
        session: Session,
        *,
        actor_id: int,
        receipt_id: int,
        expected_draft_version: int,
        supplier_id: int | None = None,
        items: Sequence[ReceiptLineInput] | None = None,
    ) -> ReceiptRead:
        """Update a DRAFT purchase receipt with optimistic version check."""
        receipt = session.get(PurchaseReceipt, receipt_id)
        if receipt is None:
            raise ResourceNotFoundError(f"Phiếu nhập ID {receipt_id} không tồn tại.")

        if receipt.status != "DRAFT":
            raise InvalidStateError(
                f"Không thể chỉnh sửa phiếu nhập đã ở trạng thái {receipt.status}."
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

        if supplier_id is not None:
            supplier = session.get(Supplier, supplier_id)
            if supplier is None:
                raise ResourceNotFoundError(
                    f"Nhà cung cấp ID {supplier_id} không tồn tại."
                )
            if str(supplier.status) != SupplierStatus.ACTIVE:
                raise DomainValidationError(
                    f"Nhà cung cấp '{supplier.name}' đang ở trạng thái không hoạt động."
                )
            receipt.supplier_id = supplier_id
            receipt.supplier_name_snapshot = supplier.name

        if items is not None:
            lines, total_vnd = self._process_items(session, items)
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id == receipt.id
                )
            )
            item_rows: list[PurchaseReceiptItem] = []
            for line in lines:
                item_row = PurchaseReceiptItem(
                    receipt_id=receipt.id,
                    product_id=line["product_id"],
                    sku_snapshot=line["sku_snapshot"],
                    product_name_snapshot=line["product_name_snapshot"],
                    quantity=line["quantity"],
                    unit_cost_vnd=line["unit_cost_vnd"],
                    line_total_vnd=line["line_total_vnd"],
                )
                session.add(item_row)
                item_rows.append(item_row)
            receipt.total_vnd = total_vnd
        else:
            item_rows = list(
                session.scalars(
                    select(PurchaseReceiptItem)
                    .where(PurchaseReceiptItem.receipt_id == receipt.id)
                    .order_by(PurchaseReceiptItem.product_id)
                )
            )

        receipt.draft_version += 1
        receipt.updated_at = utc_now_naive()
        session.flush()
        return self._to_receipt_read(receipt, item_rows)

    def get_receipt(self, session: Session, receipt_id: int) -> ReceiptRead:
        """Fetch a purchase receipt by ID with its line items."""
        receipt = session.get(PurchaseReceipt, receipt_id)
        if receipt is None:
            raise ResourceNotFoundError(f"Phiếu nhập ID {receipt_id} không tồn tại.")

        items = list(
            session.scalars(
                select(PurchaseReceiptItem)
                .where(PurchaseReceiptItem.receipt_id == receipt_id)
                .order_by(PurchaseReceiptItem.product_id)
            )
        )
        return self._to_receipt_read(receipt, items)
