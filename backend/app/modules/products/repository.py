"""SQLAlchemy repositories for Product, Category lookup, and Inventory."""

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, UnaryExpression, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.schemas import ProductSortOrder

_SORT_ORDER_MAP: dict[ProductSortOrder, tuple[UnaryExpression[Any], ...]] = {
    ProductSortOrder.NAME_ASC: (Product.name.asc(), Product.id.asc()),
    ProductSortOrder.NAME_DESC: (Product.name.desc(), Product.id.desc()),
    ProductSortOrder.SKU_ASC: (Product.sku.asc(), Product.id.asc()),
    ProductSortOrder.SKU_DESC: (Product.sku.desc(), Product.id.desc()),
    ProductSortOrder.CREATED_DESC: (
        Product.created_at.desc(),
        Product.id.desc(),
    ),
}


def _escape_like_pattern(term: str) -> str:
    """Escape SQL LIKE wildcard characters so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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

    @staticmethod
    def _build_filter_predicates(
        *,
        search: str | None = None,
        category_id: int | None = None,
        status: CatalogStatus | str | None = None,
    ) -> list[ColumnElement[bool]]:
        predicates: list[ColumnElement[bool]] = []
        if category_id is not None:
            predicates.append(Product.category_id == category_id)
        if status is not None:
            status_value = status.value if isinstance(status, CatalogStatus) else status
            predicates.append(Product.status == status_value)
        if search is not None:
            trimmed = search.strip()
            if trimmed:
                escaped = _escape_like_pattern(trimmed)
                pattern = f"%{escaped}%"
                predicates.append(
                    or_(
                        Product.name.ilike(pattern, escape="\\"),
                        Product.sku.ilike(pattern, escape="\\"),
                    )
                )
        return predicates

    def list_with_inventory(
        self,
        session: Session,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        category_id: int | None = None,
        status: CatalogStatus | str | None = None,
        sort: ProductSortOrder = ProductSortOrder.CREATED_DESC,
    ) -> tuple[list[tuple[Product, Inventory]], int]:
        if sort not in _SORT_ORDER_MAP:
            raise DomainValidationError("Tham số sắp xếp không hợp lệ.")

        predicates = self._build_filter_predicates(
            search=search,
            category_id=category_id,
            status=status,
        )

        count_stmt = select(func.count(Product.id)).select_from(Product)
        if predicates:
            count_stmt = count_stmt.where(*predicates)
        total = int(session.scalar(count_stmt) or 0)

        offset = (page - 1) * page_size
        order_by_clauses = _SORT_ORDER_MAP[sort]
        items_stmt = (
            select(Product, Inventory)
            .join(Inventory, Inventory.product_id == Product.id)
            .where(*predicates)
            .order_by(*order_by_clauses)
            .offset(offset)
            .limit(page_size)
        )
        rows = session.execute(items_stmt).all()
        return [(row[0], row[1]) for row in rows], total

    def add(self, session: Session, product: Product) -> Product:
        session.add(product)
        return product


class InventoryRepository:
    """Database persistence primitives for product inventory."""

    def add_zero(self, session: Session, product_id: int, now: datetime) -> Inventory:
        inventory = Inventory(
            product_id=product_id,
            quantity=0,
            stock_version=0,
            first_stocked_at=None,
            updated_at=now,
        )
        session.add(inventory)
        return inventory
