"""Service layer for inventory read operations."""

from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.modules.inventory.repository import InventoryQueryRepository
from app.modules.inventory.schemas import InventoryPage, InventoryRead


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
