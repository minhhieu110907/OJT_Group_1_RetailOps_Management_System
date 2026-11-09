"""Database repository for suppliers."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.suppliers.models import Supplier


class SupplierRepository:
    """SQLAlchemy data access layer for suppliers."""

    def get_by_id(self, session: Session, supplier_id: int) -> Supplier | None:
        """Find a single supplier by primary key ID."""
        return session.scalar(select(Supplier).where(Supplier.id == supplier_id))

    def list_paginated(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Supplier], int]:
        """Query paginated suppliers with optional status and name search filters."""
        base_query = select(Supplier)
        count_query = select(func.count(Supplier.id))

        if status:
            base_query = base_query.where(Supplier.status == status)
            count_query = count_query.where(Supplier.status == status)

        if search:
            trimmed = search.strip()
            if trimmed:
                pattern = f"%{trimmed}%"
                base_query = base_query.where(Supplier.name.ilike(pattern))
                count_query = count_query.where(Supplier.name.ilike(pattern))

        total = session.scalar(count_query) or 0

        # Stable ordering by id ASC
        base_query = (
            base_query.order_by(Supplier.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(session.scalars(base_query).all())
        return items, total

    def add(self, session: Session, supplier: Supplier) -> Supplier:
        """Add a supplier to the session and flush to generate ID without committing."""
        session.add(supplier)
        session.flush()
        return supplier
