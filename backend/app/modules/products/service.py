"""Application service and transaction boundaries for Product management."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    DomainValidationError,
    DuplicateSkuError,
    ResourceNotFoundError,
)
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.repository import InventoryRepository, ProductRepository
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductListResponse,
    ProductRead,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)


def utc_now_naive() -> datetime:
    """Return the current UTC timestamp without timezone info for MySQL DATETIME(6)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _is_duplicate_sku_integrity_error(error: IntegrityError) -> bool:
    """Inspect a database IntegrityError to determine if it is a unique SKU violation."""
    message = str(getattr(error, "orig", error)).lower()
    return (
        "uq_products_sku" in message
        or "products.sku" in message
        or ("duplicate entry" in message and "sku" in message)
    )


class ProductService:
    """Coordinate Product use cases while owning every commit/rollback decision."""

    def __init__(
        self,
        products: ProductRepository | None = None,
        inventory: InventoryRepository | None = None,
    ) -> None:
        self.products = products or ProductRepository()
        self.inventory = inventory or InventoryRepository()

    def list_products(
        self, session: Session, *, page: int = 1, page_size: int = 20
    ) -> ProductListResponse:
        rows, total = self.products.list_with_inventory(
            session, page=page, page_size=page_size
        )
        items = [self._to_read_dto(product, inv) for product, inv in rows]
        return ProductListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_product(self, session: Session, product_id: int) -> ProductRead:
        pair = self.products.get_with_inventory(session, product_id)
        if pair is None:
            raise ResourceNotFoundError("Không tìm thấy sản phẩm.")
        product, inv = pair
        return self._to_read_dto(product, inv)

    def create(
        self, session: Session, data: ProductCreateRequest
    ) -> ProductRead:
        self._require_active_category(session, data.category_id)
        existing_sku = self.products.get_by_sku(session, data.sku)
        if existing_sku is not None:
            session.rollback()
            raise DuplicateSkuError()

        now = utc_now_naive()
        product = Product(
            category_id=data.category_id,
            sku=data.sku,
            name=data.name,
            status=CatalogStatus.ACTIVE.value,
            sale_price_vnd=data.sale_price_vnd,
            created_at=now,
            updated_at=now,
        )
        try:
            self.products.add(session, product)
            session.flush()
            inv = self.inventory.add_zero(session, product.id, now)
            session.commit()
        except IntegrityError as error:
            session.rollback()
            if _is_duplicate_sku_integrity_error(error):
                raise DuplicateSkuError() from error
            raise
        except Exception:
            session.rollback()
            raise

        return self._to_read_dto(product, inv)

    def update(
        self, session: Session, product_id: int, data: ProductUpdateRequest
    ) -> ProductRead:
        pair = self.products.get_with_inventory(session, product_id)
        if pair is None:
            session.rollback()
            raise ResourceNotFoundError("Không tìm thấy sản phẩm.")
        product, inv = pair

        updates = data.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            if value is None:
                session.rollback()
                raise DomainValidationError(
                    f"Trường '{field_name}' không được để trống."
                )

        if "category_id" in updates:
            self._require_active_category(session, updates["category_id"])

        if "sku" in updates and updates["sku"] != product.sku:
            existing_sku = self.products.get_by_sku(session, updates["sku"])
            if existing_sku is not None and existing_sku.id != product.id:
                session.rollback()
                raise DuplicateSkuError()

        if updates:
            for field_name, value in updates.items():
                setattr(product, field_name, value)
            product.updated_at = utc_now_naive()

        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            if _is_duplicate_sku_integrity_error(error):
                raise DuplicateSkuError() from error
            raise
        except Exception:
            session.rollback()
            raise

        return self._to_read_dto(product, inv)

    def update_status(
        self,
        session: Session,
        product_id: int,
        data: ProductStatusUpdateRequest,
    ) -> ProductRead:
        pair = self.products.get_with_inventory(session, product_id)
        if pair is None:
            session.rollback()
            raise ResourceNotFoundError("Không tìm thấy sản phẩm.")
        product, inv = pair

        if product.status != data.status.value:
            product.status = data.status.value
            product.updated_at = utc_now_naive()

        try:
            session.commit()
        except Exception:
            session.rollback()
            raise

        return self._to_read_dto(product, inv)

    def _require_active_category(self, session: Session, category_id: int) -> None:
        category = self.products.get_category(session, category_id)
        if category is None:
            session.rollback()
            raise ResourceNotFoundError("Không tìm thấy danh mục.")
        if category.status != CatalogStatus.ACTIVE.value:
            session.rollback()
            raise DomainValidationError(
                "Danh mục đã ngừng hoạt động, không thể gán cho sản phẩm."
            )

    @staticmethod
    def _to_read_dto(product: Product, inv: Inventory) -> ProductRead:
        return ProductRead(
            id=product.id,
            category_id=product.category_id,
            sku=product.sku,
            name=product.name,
            status=CatalogStatus(product.status),
            sale_price_vnd=product.sale_price_vnd,
            quantity=inv.quantity,
            stock_version=inv.stock_version,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

