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
    """Seed initial categories idempotently using add/flush without committing.

    Checks if a category with the same name already exists in the session/database.
    Returns the number of newly added categories.

    Note:
        This seed procedure is designed to run sequentially (e.g. during deployment
        or application startup) and does not claim concurrency safety. In accordance
        with ERD V1.0, the categories table does not enforce a UNIQUE constraint
        on the name column. Transaction management (commit/rollback) is the
        responsibility of the caller (e.g. CLI main or service layer).
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
        session.flush()

    return created_count


def main() -> None:
    """CLI runner for categories seed; owns the transaction boundary."""
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        try:
            created = seed_categories(session)
            session.commit()
            print(f"Categories seed completed: {created} created")
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
