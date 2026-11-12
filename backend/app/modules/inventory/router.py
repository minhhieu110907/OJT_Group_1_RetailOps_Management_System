"""HTTP endpoints for inventory queries, low-stock alerts, and stock movements."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User, UserRole
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    InventoryPage,
    InventoryRead,
    LowStockPage,
    StockMovementAdminPage,
    StockMovementKind,
    StockMovementPage,
)
from app.modules.inventory.service import InventoryQueryService

router = APIRouter(prefix="/inventory", tags=["inventory"])
stock_movements_router = APIRouter(prefix="/stock-movements", tags=["inventory"])


def get_inventory_service() -> InventoryQueryService:
    """FastAPI dependency for obtaining an InventoryQueryService instance."""
    return InventoryQueryService()


@router.get("", response_model=InventoryPage, status_code=status.HTTP_200_OK)
def list_inventory(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[InventoryQueryService, Depends(get_inventory_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    category_id: Annotated[int | None, Query(ge=1)] = None,
    status_filter: Annotated[
        Literal["ACTIVE", "INACTIVE"] | None, Query(alias="status")
    ] = None,
    in_stock: Annotated[bool | None, Query()] = None,
) -> InventoryPage:
    """List inventory items with filters and pagination for active ADMIN and STAFF."""
    return service.list_inventory(
        session=session,
        page=page,
        page_size=page_size,
        category_id=category_id,
        status=status_filter,
        in_stock=in_stock,
    )


# CRITICAL ROUTE ORDER (ROUTE-01):
# /inventory/low-stock MUST be registered BEFORE /inventory/{product_id}
# to prevent FastAPI from matching "low-stock" as an integer product_id.
@router.get(
    "/low-stock",
    response_model=LowStockPage,
    status_code=status.HTTP_200_OK,
)
def get_low_stock(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[InventoryQueryService, Depends(get_inventory_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    threshold: Annotated[
        int, Query(ge=1, description="Ngưỡng cảnh báo tồn kho thấp")
    ] = DEFAULT_LOW_STOCK_THRESHOLD,
) -> LowStockPage:
    """Retrieve products with inventory balance at or below the low-stock threshold."""
    return service.get_low_stock(
        session=session,
        page=page,
        page_size=page_size,
        threshold=threshold,
    )


@router.get(
    "/{product_id}",
    response_model=InventoryRead,
    status_code=status.HTTP_200_OK,
)
def get_inventory(
    product_id: Annotated[int, Path(ge=1, description="Mã định danh sản phẩm")],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[InventoryQueryService, Depends(get_inventory_service)],
) -> InventoryRead:
    """Retrieve current inventory balance for a single product."""
    return service.get_inventory(session=session, product_id=product_id)


@stock_movements_router.get(
    "",
    response_model=StockMovementAdminPage | StockMovementPage,
    status_code=status.HTTP_200_OK,
)
def list_stock_movements(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[InventoryQueryService, Depends(get_inventory_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    product_id: Annotated[int | None, Query(ge=1)] = None,
    kind: Annotated[StockMovementKind | None, Query()] = None,
) -> StockMovementAdminPage | StockMovementPage:
    """List stock movement audit trail with role-based field filtering."""
    is_admin = (
        _current_user.role == UserRole.ADMIN or str(_current_user.role) == "ADMIN"
    )
    if is_admin:
        return service.list_stock_movements_admin(
            session=session,
            page=page,
            page_size=page_size,
            product_id=product_id,
            kind=kind,
        )
    return service.list_stock_movements_staff(
        session=session,
        page=page,
        page_size=page_size,
        product_id=product_id,
        kind=kind,
    )
