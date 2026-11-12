"""Domain service for Purchase Receipt draft creation and updates."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
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
    MAX_SQL_BIGINT,
    MAX_SQL_INT,
    ReceiptItemRead,
    ReceiptLineInput,
    ReceiptPage,
    ReceiptRead,
)
from app.modules.suppliers.models import Supplier, SupplierStatus

VN_TZ = timezone(timedelta(hours=7))
ALLOWED_RECEIPT_STATUSES = {"DRAFT", "CONFIRMED", "CANCELLED"}


def utc_now_naive() -> datetime:
    """Return current UTC timestamp without timezone info for MySQL DATETIME(6)."""
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
                raise DomainValidationError(
                    f"Sản phẩm ID {pid} có nhiều đơn giá khác nhau trong "
                    f"cùng một phiếu ({product_costs[pid]} và {cost}).",
                    details={
                        "code": "RECEIPT_ITEM_COST_CONFLICT",
                        "product_id": pid,
                        "existing_unit_cost_vnd": product_costs[pid],
                        "conflicting_unit_cost_vnd": cost,
                    },
                )
            product_costs[pid] = cost
            new_qty = product_quantities.get(pid, 0) + item.quantity
            if new_qty > MAX_SQL_INT:
                raise DomainValidationError(
                    f"Tổng số lượng sản phẩm ID {pid} sau khi gộp "
                    f"vượt quá giới hạn SQL INT ({MAX_SQL_INT}).",
                    details={
                        "product_id": pid,
                        "quantity": new_qty,
                        "max": MAX_SQL_INT,
                    },
                )
            product_quantities[pid] = new_qty

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
            if line_total > MAX_SQL_BIGINT:
                raise DomainValidationError(
                    f"Thành tiền của sản phẩm ID {pid} vượt quá "
                    f"giới hạn BIGINT ({MAX_SQL_BIGINT}).",
                    details={
                        "product_id": pid,
                        "line_total_vnd": line_total,
                        "max": MAX_SQL_BIGINT,
                    },
                )
            total_vnd += line_total
            if total_vnd > MAX_SQL_BIGINT:
                raise DomainValidationError(
                    f"Tổng giá trị phiếu nhập vượt quá "
                    f"giới hạn BIGINT ({MAX_SQL_BIGINT}).",
                    details={
                        "total_vnd": total_vnd,
                        "max": MAX_SQL_BIGINT,
                    },
                )
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
            raise ResourceNotFoundError(f"Nhà cung cấp ID {supplier_id} không tồn tại.")
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
        if supplier_id is None and items is None:
            raise DomainValidationError(
                "Yêu cầu cập nhật phải chứa ít nhất một trong hai trường: "
                "'supplier_id' hoặc 'items'.",
                details={"reason": "EMPTY_PATCH_FORBIDDEN"},
            )

        receipt = session.scalar(
            select(PurchaseReceipt)
            .where(PurchaseReceipt.id == receipt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
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

        new_supplier_id = receipt.supplier_id
        new_supplier_name = receipt.supplier_name_snapshot
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
            new_supplier_id = supplier_id
            new_supplier_name = supplier.name

        new_total_vnd = receipt.total_vnd
        item_rows: list[PurchaseReceiptItem] = []
        if items is not None:
            lines, new_total_vnd = self._process_items(session, items)
            for line in lines:
                item_rows.append(
                    PurchaseReceiptItem(
                        receipt_id=receipt.id,
                        product_id=line["product_id"],
                        sku_snapshot=line["sku_snapshot"],
                        product_name_snapshot=line["product_name_snapshot"],
                        quantity=line["quantity"],
                        unit_cost_vnd=line["unit_cost_vnd"],
                        line_total_vnd=line["line_total_vnd"],
                    )
                )

        now = utc_now_naive()
        stmt = (
            update(PurchaseReceipt)
            .where(
                PurchaseReceipt.id == receipt_id,
                PurchaseReceipt.draft_version == expected_draft_version,
                PurchaseReceipt.status == "DRAFT",
            )
            .values(
                draft_version=expected_draft_version + 1,
                updated_at=now,
                total_vnd=new_total_vnd,
                supplier_id=new_supplier_id,
                supplier_name_snapshot=new_supplier_name,
            )
        )
        result = session.execute(stmt)
        if result.rowcount == 0:
            current = session.scalar(
                select(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id)
            )
            if current is None:
                raise ResourceNotFoundError(
                    f"Phiếu nhập ID {receipt_id} không tồn tại."
                )
            if current.status != "DRAFT":
                raise InvalidStateError(
                    f"Không thể chỉnh sửa phiếu nhập đã ở trạng thái {current.status}."
                )
            raise ConflictError(
                code="RECEIPT_VERSION_CONFLICT",
                message=(
                    f"Phiên bản nháp không khớp: kỳ vọng {expected_draft_version}, "
                    f"hiện tại là {current.draft_version}."
                ),
                details={
                    "receipt_id": receipt_id,
                    "current_draft_version": current.draft_version,
                    "expected_draft_version": expected_draft_version,
                },
            )

        if items is not None:
            session.execute(
                delete(PurchaseReceiptItem).where(
                    PurchaseReceiptItem.receipt_id == receipt.id
                )
            )
            session.add_all(item_rows)
        else:
            item_rows = list(
                session.scalars(
                    select(PurchaseReceiptItem)
                    .where(PurchaseReceiptItem.receipt_id == receipt.id)
                    .order_by(PurchaseReceiptItem.product_id)
                )
            )

        session.flush()
        session.refresh(receipt)
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

    def cancel_draft(
        self,
        session: Session,
        *,
        actor_id: int,
        receipt_id: int,
        expected_draft_version: int,
    ) -> ReceiptRead:
        """Cancel a DRAFT purchase receipt with optimistic locking (no stock change)."""
        receipt = session.scalar(
            select(PurchaseReceipt)
            .where(PurchaseReceipt.id == receipt_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if receipt is None:
            raise ResourceNotFoundError(f"Phiếu nhập ID {receipt_id} không tồn tại.")

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
                f"Không thể hủy phiếu nhập đã ở trạng thái {receipt.status}."
            )

        now = utc_now_naive()
        supplier_name = receipt.supplier_name_snapshot
        if not supplier_name:
            sup = session.get(Supplier, receipt.supplier_id)
            supplier_name = sup.name if sup else "Unknown Supplier"

        stmt = (
            update(PurchaseReceipt)
            .where(
                PurchaseReceipt.id == receipt_id,
                PurchaseReceipt.draft_version == expected_draft_version,
                PurchaseReceipt.status == "DRAFT",
            )
            .values(
                status="CANCELLED",
                draft_version=PurchaseReceipt.draft_version + 1,
                closed_by=actor_id,
                closed_at=now,
                updated_at=now,
                supplier_name_snapshot=supplier_name,
            )
        )
        result = session.execute(stmt)
        if result.rowcount == 0:
            current = session.scalar(
                select(PurchaseReceipt).where(PurchaseReceipt.id == receipt_id)
            )
            if current is None:
                raise ResourceNotFoundError(
                    f"Phiếu nhập ID {receipt_id} không tồn tại."
                )
            if current.draft_version != expected_draft_version:
                raise ConflictError(
                    code="RECEIPT_VERSION_CONFLICT",
                    message=(
                        f"Phiên bản nháp không khớp: kỳ vọng {expected_draft_version}, "
                        f"hiện tại là {current.draft_version}."
                    ),
                    details={
                        "receipt_id": receipt_id,
                        "current_draft_version": current.draft_version,
                        "expected_draft_version": expected_draft_version,
                    },
                )
            if current.status != "DRAFT":
                raise ConflictError(
                    code="RECEIPT_VERSION_CONFLICT",
                    message=(
                        f"Không thể hủy phiếu nhập đã ở trạng thái {current.status}."
                    ),
                    details={
                        "receipt_id": receipt_id,
                        "status": current.status,
                    },
                )
            raise ConflictError(
                code="RECEIPT_VERSION_CONFLICT",
                message=(
                    f"Phiên bản nháp không khớp: kỳ vọng {expected_draft_version}, "
                    f"hiện tại là {current.draft_version}."
                ),
                details={
                    "receipt_id": receipt_id,
                    "current_draft_version": current.draft_version,
                    "expected_draft_version": expected_draft_version,
                },
            )

        session.flush()
        session.refresh(receipt)

        items = list(
            session.scalars(
                select(PurchaseReceiptItem)
                .where(PurchaseReceiptItem.receipt_id == receipt_id)
                .order_by(PurchaseReceiptItem.product_id)
            )
        )
        return self._to_receipt_read(receipt, items)

    def list_receipts(
        self,
        session: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        supplier_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> ReceiptPage:
        """List purchase receipts with pagination and filtering."""
        if page < 1:
            raise DomainValidationError("Trang (page) phải lớn hơn hoặc bằng 1.")
        if page_size < 1 or page_size > 100:
            raise DomainValidationError(
                "Kích thước trang (page_size) phải từ 1 đến 100."
            )

        base_query = select(PurchaseReceipt)

        if status is not None:
            normalized_status = status.strip().upper()
            if normalized_status not in ALLOWED_RECEIPT_STATUSES:
                raise DomainValidationError(
                    f"Trạng thái '{status}' không hợp lệ. "
                    f"Chỉ chấp nhận: {', '.join(sorted(ALLOWED_RECEIPT_STATUSES))}."
                )
            base_query = base_query.where(PurchaseReceipt.status == normalized_status)

        if supplier_id is not None:
            if supplier_id <= 0:
                raise DomainValidationError("supplier_id phải lớn hơn 0.")
            base_query = base_query.where(PurchaseReceipt.supplier_id == supplier_id)

        if from_date is not None and isinstance(from_date, datetime):
            from_date = from_date.date()
        if to_date is not None and isinstance(to_date, datetime):
            to_date = to_date.date()

        if from_date is not None and to_date is not None and from_date > to_date:
            raise DomainValidationError("from_date phải nhỏ hơn hoặc bằng to_date.")

        if from_date is not None:
            start_utc = (
                datetime(
                    from_date.year,
                    from_date.month,
                    from_date.day,
                    0,
                    0,
                    0,
                    tzinfo=VN_TZ,
                )
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            base_query = base_query.where(PurchaseReceipt.created_at >= start_utc)

        if to_date is not None:
            end_local = datetime(
                to_date.year,
                to_date.month,
                to_date.day,
                0,
                0,
                0,
                tzinfo=VN_TZ,
            ) + timedelta(days=1)
            end_utc = end_local.astimezone(UTC).replace(tzinfo=None)
            base_query = base_query.where(PurchaseReceipt.created_at < end_utc)

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = session.scalar(count_stmt) or 0

        offset = (page - 1) * page_size
        data_stmt = (
            base_query.order_by(
                PurchaseReceipt.created_at.desc(), PurchaseReceipt.id.desc()
            )
            .offset(offset)
            .limit(page_size)
        )
        receipts = list(session.scalars(data_stmt))

        if receipts:
            receipt_ids = [r.id for r in receipts]
            items = list(
                session.scalars(
                    select(PurchaseReceiptItem)
                    .where(PurchaseReceiptItem.receipt_id.in_(receipt_ids))
                    .order_by(
                        PurchaseReceiptItem.receipt_id,
                        PurchaseReceiptItem.product_id,
                    )
                )
            )
            items_by_receipt: dict[int, list[PurchaseReceiptItem]] = {}
            for it in items:
                items_by_receipt.setdefault(it.receipt_id, []).append(it)
            receipt_reads = [
                self._to_receipt_read(r, items_by_receipt.get(r.id, []))
                for r in receipts
            ]
        else:
            receipt_reads = []

        return ReceiptPage(
            items=receipt_reads,
            total=total,
            page=page,
            page_size=page_size,
        )
