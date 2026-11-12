"""Service layer for inventory read operations."""

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.modules.inventory.repository import InventoryQueryRepository
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    InventoryPage,
    InventoryRead,
    LowStockItem,
    LowStockPage,
    StockMovementAdminPage,
    StockMovementAdminRead,
    StockMovementPage,
    StockMovementRead,
)


class InventoryQueryService:
    """Orchestrates inventory read queries and builds response DTOs."""

    def __init__(self, repository: InventoryQueryRepository | None = None) -> None:
        self._repository = repository or InventoryQueryRepository()

    def list_inventory(
        self,
        session: Session,
        page: int,
        page_size: int,
        category_id: int | None = None,
        status: str | None = None,
        in_stock: bool | None = None,
    ) -> InventoryPage:
        """Fetch paginated inventory items and return as InventoryPage."""
        items, total = self._repository.list_inventory(
            session=session,
            page=page,
            page_size=page_size,
            category_id=category_id,
            status=status,
            in_stock=in_stock,
        )
        return InventoryPage(
            items=[InventoryRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_inventory(self, session: Session, product_id: int) -> InventoryRead:
        """Fetch inventory item by product ID or raise ResourceNotFoundError."""
        item = self._repository.get_by_product_id(
            session=session, product_id=product_id
        )
        if item is None:
            raise ResourceNotFoundError(
                "Không tìm thấy thông tin tồn kho cho sản phẩm yêu cầu."
            )
        return InventoryRead.model_validate(item)

    def get_low_stock(
        self,
        session: Session,
        page: int,
        page_size: int,
        threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
    ) -> LowStockPage:
        """Fetch active products with inventory quantity <= threshold."""
        items, total = self._repository.list_low_stock(
            session=session,
            page=page,
            page_size=page_size,
            threshold=threshold,
        )
        return LowStockPage(
            items=[LowStockItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements_admin(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
    ) -> StockMovementAdminPage:
        """Fetch audited stock movement history for ADMIN."""
        items, total = self._repository.list_stock_movements(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
        return StockMovementAdminPage(
            items=[StockMovementAdminRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements_staff(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
    ) -> StockMovementPage:
        """Fetch safe public stock movement history for STAFF."""
        items, total = self._repository.list_stock_movements(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
        staff_items: list[StockMovementRead] = []
        for item in items:
            item_data = {
                "id": item["id"],
                "product_id": item["product_id"],
                "sku": item["sku"],
                "kind": item["kind"],
                "quantity_before": item["quantity_before"],
                "quantity_after": item["quantity_after"],
                "stock_version_after": item["stock_version_after"],
                "reference_id": item["reference_id"],
                "occurred_at": item["occurred_at"],
            }
            staff_items.append(StockMovementRead.model_validate(item_data))

        return StockMovementPage(
            items=staff_items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_stock_movements(
        self,
        session: Session,
        page: int,
        page_size: int,
        product_id: int | None = None,
        kind: str | None = None,
        is_admin: bool = False,
    ) -> StockMovementPage | StockMovementAdminPage:
        """Fetch stock movement history with role-appropriate projection."""
        if is_admin:
            return self.list_stock_movements_admin(
                session=session,
                page=page,
                page_size=page_size,
                product_id=product_id,
                kind=kind,
            )
        return self.list_stock_movements_staff(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
