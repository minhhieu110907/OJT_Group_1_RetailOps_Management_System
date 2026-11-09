"""Database repository for categories."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category


class CategoryRepository:
    """SQLAlchemy data access layer for categories."""

    def get_by_id(self, session: Session, category_id: int) -> Category | None:
        """Find a single category by its primary key ID."""
        return session.scalar(select(Category).where(Category.id == category_id))

    def list_paginated(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Category], int]:
        """Query paginated categories with optional status and name search filters."""
        base_query = select(Category)
        count_query = select(func.count(Category.id))

        if status:
            base_query = base_query.where(Category.status == status)
            count_query = count_query.where(Category.status == status)

        if search:
            trimmed = search.strip()
            if trimmed:
                pattern = f"%{trimmed}%"
                base_query = base_query.where(Category.name.ilike(pattern))
                count_query = count_query.where(Category.name.ilike(pattern))

        total = session.scalar(count_query) or 0

        # Stable ordering by id ASC
        base_query = (
            base_query.order_by(Category.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(session.scalars(base_query).all())
        return items, total

    def add(self, session: Session, category: Category) -> Category:
        """Add a category to the session and flush to generate ID without committing."""
        session.add(category)
        session.flush()
        return category
