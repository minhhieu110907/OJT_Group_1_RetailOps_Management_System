"""HTTP endpoints for inventory queries."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.inventory.schemas import InventoryPage, InventoryRead
from app.modules.inventory.service import InventoryQueryService

router = APIRouter(prefix="/inventory", tags=["inventory"])


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
    status: Annotated[Literal["ACTIVE", "INACTIVE"] | None, Query()] = None,
    in_stock: Annotated[bool | None, Query()] = None,
) -> InventoryPage:
    """List inventory items with filters and pagination for active ADMIN and STAFF."""
    return service.list_inventory(
        session=session,
        page=page,
        page_size=page_size,
        category_id=category_id,
        status=status,
        in_stock=in_stock,
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
