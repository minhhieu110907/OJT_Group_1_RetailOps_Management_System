"""Application service managing Supplier use cases and transaction boundaries."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError, ResourceNotFoundError
from app.modules.categories.models import CategoryStatus
from app.modules.suppliers.models import Supplier, SupplierStatus
from app.modules.suppliers.repository import SupplierRepository
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierStatusUpdate,
    SupplierUpdate,
)


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SupplierService:
    """Coordinate Supplier use cases while owning every commit/rollback decision."""

    def __init__(self, repository: SupplierRepository | None = None) -> None:
        self.repository = repository or SupplierRepository()

    def get_by_id(self, session: Session, supplier_id: int) -> Supplier:
        """Fetch a supplier by ID or raise ResourceNotFoundError."""
        supplier = self.repository.get_by_id(session, supplier_id)
        if supplier is None:
            raise ResourceNotFoundError(
                f"Không tìm thấy nhà cung cấp với mã {supplier_id}."
            )
        return supplier

    def list_suppliers(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> SupplierListResponse:
        """List suppliers paginated and convert to response envelope."""
        items, total = self.repository.list_paginated(
            session, page=page, page_size=page_size, status=status, search=search
        )
        # One batched query for every supplier on the page (no N+1).
        category_map = self.repository.get_category_ids_map(
            session, [item.id for item in items]
        )
        return SupplierListResponse(
            items=[self._build_read(item, category_map[item.id]) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _build_read(supplier: Supplier, category_ids: list[int]) -> SupplierRead:
        return SupplierRead(
            id=supplier.id,
            name=supplier.name,
            contact_email=supplier.contact_email,
            contact_phone=supplier.contact_phone,
            status=supplier.status,
            category_ids=category_ids,
            created_at=supplier.created_at,
            updated_at=supplier.updated_at,
        )

    def to_read(self, session: Session, supplier: Supplier) -> SupplierRead:
        """Serialize one supplier together with its category ids."""
        category_map = self.repository.get_category_ids_map(session, [supplier.id])
        return self._build_read(supplier, category_map[supplier.id])

    def _validate_category_ids(
        self,
        session: Session,
        category_ids: list[int],
        already_linked: set[int] | None = None,
    ) -> None:
        """Fail closed when a category id is unknown or newly assigned while INACTIVE.

        Rule: every id must exist (404). A category that is INACTIVE cannot be
        newly linked (422, mirrors PROD-02 for products), but a link that already
        exists is grandfathered so re-sending the current list or editing other
        supplier fields never fails because a category was deactivated later.
        """
        if not category_ids:
            return
        statuses = self.repository.get_category_statuses(session, category_ids)
        missing = [cid for cid in category_ids if cid not in statuses]
        if missing:
            session.rollback()
            raise ResourceNotFoundError(
                "Không tìm thấy danh mục.",
                details={"missing_category_ids": missing},
            )
        grandfathered = already_linked or set()
        inactive = [
            cid
            for cid in category_ids
            if statuses[cid] != CategoryStatus.ACTIVE.value and cid not in grandfathered
        ]
        if inactive:
            session.rollback()
            raise DomainValidationError(
                "Danh mục đã ngừng hoạt động, không thể gán cho nhà cung cấp.",
                details={"inactive_category_ids": inactive},
            )

    def create_supplier(self, session: Session, data: SupplierCreate) -> Supplier:
        """Create a new supplier in ACTIVE status and commit atomically."""
        category_ids = list(dict.fromkeys(data.category_ids))
        self._validate_category_ids(session, category_ids)
        now = _utc_now_naive()
        supplier = Supplier(
            name=data.name.strip(),
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        try:
            self.repository.add(session, supplier)
            if category_ids:
                self.repository.replace_category_links(
                    session, supplier.id, category_ids
                )
            session.commit()
            return supplier
        except Exception:
            session.rollback()
            raise

    def update_supplier(
        self, session: Session, supplier_id: int, data: SupplierUpdate
    ) -> Supplier:
        """Update supplier fields and commit.
        (supporting explicit null to clear contact fields)"""
        supplier = self.get_by_id(session, supplier_id)

        # category_ids: omitted/None keeps links; [] clears; a list replaces them.
        new_category_ids: list[int] | None = None
        if data.category_ids is not None:
            new_category_ids = list(dict.fromkeys(data.category_ids))
            current_ids = set(
                self.repository.get_category_ids_map(session, [supplier.id])[
                    supplier.id
                ]
            )
            self._validate_category_ids(
                session, new_category_ids, already_linked=current_ids
            )

        if "name" in data.model_fields_set and data.name is not None:
            supplier.name = data.name.strip()

        if "contact_email" in data.model_fields_set:
            supplier.contact_email = data.contact_email

        if "contact_phone" in data.model_fields_set:
            supplier.contact_phone = data.contact_phone

        supplier.updated_at = _utc_now_naive()
        try:
            session.flush()
            if new_category_ids is not None:
                self.repository.replace_category_links(
                    session, supplier.id, new_category_ids
                )
            session.commit()
            return supplier
        except Exception:
            session.rollback()
            raise

    def update_supplier_status(
        self, session: Session, supplier_id: int, data: SupplierStatusUpdate
    ) -> Supplier:
        """Update supplier status (ACTIVE/INACTIVE) and commit atomically."""
        supplier = self.get_by_id(session, supplier_id)
        supplier.status = data.status.value
        supplier.updated_at = _utc_now_naive()
        try:
            session.flush()
            session.commit()
            return supplier
        except Exception:
            session.rollback()
            raise
