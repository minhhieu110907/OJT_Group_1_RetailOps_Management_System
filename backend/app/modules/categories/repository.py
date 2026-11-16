"""Database repository for categories."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.products.models import Product


class CategoryRepository:
    """SQLAlchemy data access layer for categories."""

    def get_by_id(
        self, session: Session, category_id: int
    ) -> tuple[Category, int] | None:
        """Find a single category by its primary key ID."""
        product_counts = (
            select(Product.category_id, func.count(Product.id).label("product_count"))
            .group_by(Product.category_id)
            .subquery()
        )
        return session.execute(
            select(Category, func.coalesce(product_counts.c.product_count, 0))
            .outerjoin(product_counts, product_counts.c.category_id == Category.id)
            .where(Category.id == category_id)
        ).one_or_none()

    def list_paginated(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[tuple[Category, int]], int]:
        """Query paginated categories with optional status and name search filters."""
        product_counts = (
            select(Product.category_id, func.count(Product.id).label("product_count"))
            .group_by(Product.category_id)
            .subquery()
        )
        base_query = select(
            Category, func.coalesce(product_counts.c.product_count, 0)
        ).outerjoin(product_counts, product_counts.c.category_id == Category.id)
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
        items = [
            (category, int(count)) for category, count in session.execute(base_query)
        ]
        return items, total

    def product_count(self, session: Session, category_id: int) -> int:
        return int(
            session.scalar(
                select(func.count(Product.id)).where(Product.category_id == category_id)
            )
            or 0
        )

    def add(self, session: Session, category: Category) -> Category:
        """Add a category to the session and flush to generate ID without committing."""
        session.add(category)
        session.flush()
        return category
