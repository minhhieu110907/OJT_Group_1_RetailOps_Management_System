"""Application service managing Supplier use cases and transaction boundaries."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
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
        return SupplierListResponse(
            items=[SupplierRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def create_supplier(self, session: Session, data: SupplierCreate) -> Supplier:
        """Create a new supplier in ACTIVE status and commit atomically."""
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

        if "name" in data.model_fields_set and data.name is not None:
            supplier.name = data.name.strip()

        if "contact_email" in data.model_fields_set:
            supplier.contact_email = data.contact_email

        if "contact_phone" in data.model_fields_set:
            supplier.contact_phone = data.contact_phone

        supplier.updated_at = _utc_now_naive()
        try:
            session.flush()
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
