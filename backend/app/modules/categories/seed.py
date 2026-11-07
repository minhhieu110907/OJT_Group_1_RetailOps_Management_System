"""Seed initial categories safely and idempotently."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category, CategoryStatus

DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {"name": "Đồ uống"},
    {"name": "Bánh kẹo & Đồ ăn vặt"},
    {"name": "Thực phẩm đóng hộp"},
    {"name": "Hóa mỹ phẩm & Tẩy rửa"},
    {"name": "Đồ gia dụng tiện ích"},
]


def seed_categories(
    session: Session,
    categories_data: list[dict[str, Any]] | None = None,
) -> int:
    """Seed initial categories idempotently.

    Checks if a category with the same name already exists.
    Returns the number of newly created categories.
    """
    items = categories_data if categories_data is not None else DEFAULT_CATEGORIES
    created_count = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    for item in items:
        name = str(item["name"]).strip()
        existing = session.scalar(select(Category).where(Category.name == name))
        if existing is not None:
            continue

        category = Category(
            name=name,
            status=item.get("status", CategoryStatus.ACTIVE),
            created_at=now,
            updated_at=now,
        )
        session.add(category)
        created_count += 1

    if created_count > 0:
        session.commit()

    return created_count


def main() -> None:
    """CLI runner for categories seed."""
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        created = seed_categories(session)
    print(f"Categories seed completed: {created} created")


if __name__ == "__main__":
    main()

