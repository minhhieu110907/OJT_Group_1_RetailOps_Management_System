"""Application service managing Category use cases and transaction boundaries."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.modules.categories.models import Category, CategoryStatus
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategoryStatusUpdate,
    CategoryUpdate,
)


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CategoryService:
    """Coordinate Category use cases while owning every commit/rollback decision."""

    def __init__(self, repository: CategoryRepository | None = None) -> None:
        self.repository = repository or CategoryRepository()

    def get_by_id(self, session: Session, category_id: int) -> Category:
        """Fetch a category by ID or raise ResourceNotFoundError."""
        category = self.repository.get_by_id(session, category_id)
        if category is None:
            raise ResourceNotFoundError(
                f"Không tìm thấy danh mục với mã {category_id}."
            )
        return category

    def list_categories(
        self,
        session: Session,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> CategoryListResponse:
        """List categories paginated and convert to response envelope."""
        items, total = self.repository.list_paginated(
            session, page=page, page_size=page_size, status=status, search=search
        )
        return CategoryListResponse(
            items=[CategoryRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def create_category(self, session: Session, data: CategoryCreate) -> Category:
        """Create a new category in ACTIVE status and commit atomically."""
        now = _utc_now_naive()
        category = Category(
            name=data.name.strip(),
            description=data.description,
            status=CategoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        try:
            self.repository.add(session, category)
            session.commit()
            return category
        except Exception:
            session.rollback()
            raise

    def update_category(
        self, session: Session, category_id: int, data: CategoryUpdate
    ) -> Category:
        """Partially update category fields and commit atomically."""
        category = self.get_by_id(session, category_id)

        if "name" in data.model_fields_set and data.name is not None:
            category.name = data.name.strip()

        if "description" in data.model_fields_set:
            category.description = data.description

        category.updated_at = _utc_now_naive()
        try:
            session.flush()
            session.commit()
            return category
        except Exception:
            session.rollback()
            raise

    def update_category_status(
        self, session: Session, category_id: int, data: CategoryStatusUpdate
    ) -> Category:
        """Update category status (ACTIVE/INACTIVE) and commit atomically."""
        category = self.get_by_id(session, category_id)
        category.status = data.status.value
        category.updated_at = _utc_now_naive()
        try:
            session.flush()
            session.commit()
            return category
        except Exception:
            session.rollback()
            raise
