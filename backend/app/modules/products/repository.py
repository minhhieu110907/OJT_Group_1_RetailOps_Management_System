"""SQLAlchemy repositories for Product, Category lookup, and Inventory."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.products.models import Inventory, Product


class ProductRepository:
    """Database queries and persistence primitives for products."""

    def get_category(self, session: Session, category_id: int) -> Category | None:
        return session.scalar(select(Category).where(Category.id == category_id))

    def get_by_id(self, session: Session, product_id: int) -> Product | None:
        return session.scalar(select(Product).where(Product.id == product_id))

    def get_by_sku(self, session: Session, sku: str) -> Product | None:
        return session.scalar(select(Product).where(Product.sku == sku))

    def get_with_inventory(
        self, session: Session, product_id: int
    ) -> tuple[Product, Inventory] | None:
        row = session.execute(
            select(Product, Inventory)
            .join(Inventory, Inventory.product_id == Product.id)
            .where(Product.id == product_id)
        ).first()
        if row is None:
            return None
        return row[0], row[1]

    def list_with_inventory(
        self, session: Session, *, page: int, page_size: int
    ) -> tuple[list[tuple[Product, Inventory]], int]:
        total = session.scalar(select(func.count()).select_from(Product)) or 0
        offset = (page - 1) * page_size
        rows = session.execute(
            select(Product, Inventory)
            .join(Inventory, Inventory.product_id == Product.id)
            .order_by(Product.id.asc())
            .offset(offset)
            .limit(page_size)
        ).all()
        return [(row[0], row[1]) for row in rows], int(total)

    def add(self, session: Session, product: Product) -> Product:
        session.add(product)
        return product


class InventoryRepository:
    """Database persistence primitives for product inventory."""

    def add_zero(
        self, session: Session, product_id: int, now: datetime
    ) -> Inventory:
        inventory = Inventory(
            product_id=product_id,
            quantity=0,
            stock_version=0,
            first_stocked_at=None,
            updated_at=now,
        )
        session.add(inventory)
        return inventory

