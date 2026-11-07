"""Seed initial suppliers safely and idempotently."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.suppliers.models import Supplier, SupplierStatus

DEFAULT_SUPPLIERS: list[dict[str, Any]] = [
    {
        "name": "Công ty TNHH Phân phối Nước giải khát Việt",
        "contact_email": "contact@beverages-vn.example.com",
        "contact_phone": "0901234567",
    },
    {
        "name": "Công ty Cổ phần Thực phẩm An Toàn",
        "contact_email": "info@safefood.example.com",
        "contact_phone": "0912345678",
    },
    {
        "name": "Đại lý Phân phối Hàng gia dụng Miền Bắc",
        "contact_email": "giadung@daily.example.com",
        "contact_phone": "0987654321",
    },
]


def seed_suppliers(
    session: Session,
    suppliers_data: list[dict[str, Any]] | None = None,
) -> int:
    """Seed initial suppliers idempotently using add/flush without committing.

    Checks if a supplier with the same name already exists in the session/database.
    Returns the number of newly added suppliers.

    Note:
        This seed procedure is designed to run sequentially (e.g. during deployment
        or application startup) and does not claim concurrency safety. In accordance
        with ERD V1.0, the suppliers table does not enforce a UNIQUE constraint
        on the name column. Transaction management (commit/rollback) is the
        responsibility of the caller (e.g. CLI main or service layer).
    """
    items = suppliers_data if suppliers_data is not None else DEFAULT_SUPPLIERS
    created_count = 0
    now = datetime.now(UTC).replace(tzinfo=None)

    for item in items:
        name = str(item["name"]).strip()
        existing = session.scalar(select(Supplier).where(Supplier.name == name))
        if existing is not None:
            continue

        supplier = Supplier(
            name=name,
            contact_email=item.get("contact_email"),
            contact_phone=item.get("contact_phone"),
            status=item.get("status", SupplierStatus.ACTIVE),
            created_at=now,
            updated_at=now,
        )
        session.add(supplier)
        created_count += 1

    if created_count > 0:
        session.flush()

    return created_count


def main() -> None:
    """CLI runner for suppliers seed; owns the transaction boundary."""
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        try:
            created = seed_suppliers(session)
            session.commit()
            print(f"Suppliers seed completed: {created} created")
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
