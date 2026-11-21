"""Database repository for suppliers."""

from collections.abc import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.suppliers.models import Supplier, SupplierCategory


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

    # ------------------------------------------------------------------
    # supplier_categories
    # ------------------------------------------------------------------
    def get_category_ids_map(
        self, session: Session, supplier_ids: Sequence[int]
    ) -> dict[int, list[int]]:
        """Load category ids for many suppliers in ONE query (no N+1).

        Every requested supplier id is present in the result; suppliers without
        links map to ``[]``. Category ids are sorted ascending for stable output.
        """
        result: dict[int, list[int]] = {supplier_id: [] for supplier_id in supplier_ids}
        if not result:
            return result
        rows = session.execute(
            select(SupplierCategory.supplier_id, SupplierCategory.category_id)
            .where(SupplierCategory.supplier_id.in_(list(result)))
            .order_by(SupplierCategory.supplier_id, SupplierCategory.category_id)
        ).all()
        for supplier_id, category_id in rows:
            result[supplier_id].append(category_id)
        return result

    def get_category_statuses(
        self, session: Session, category_ids: Iterable[int]
    ) -> dict[int, str]:
        """Return ``{category_id: status}`` for the ids that exist."""
        ids = list(category_ids)
        if not ids:
            return {}
        rows = session.execute(
            select(Category.id, Category.status).where(Category.id.in_(ids))
        ).all()
        return {category_id: status for category_id, status in rows}

    def replace_category_links(
        self, session: Session, supplier_id: int, category_ids: Sequence[int]
    ) -> None:
        """Make the supplier's links equal ``category_ids`` (diff-based, flush only)."""
        desired = set(category_ids)
        current = set(
            session.scalars(
                select(SupplierCategory.category_id).where(
                    SupplierCategory.supplier_id == supplier_id
                )
            ).all()
        )
        to_remove = current - desired
        if to_remove:
            session.execute(
                delete(SupplierCategory).where(
                    SupplierCategory.supplier_id == supplier_id,
                    SupplierCategory.category_id.in_(to_remove),
                )
            )
        for category_id in sorted(desired - current):
            session.add(
                SupplierCategory(supplier_id=supplier_id, category_id=category_id)
            )
        session.flush()
