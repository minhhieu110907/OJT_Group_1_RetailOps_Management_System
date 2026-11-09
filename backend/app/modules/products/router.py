"""HTTP boundary for Product catalog endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    get_current_active_user,
    require_active_admin,
)
from app.modules.auth.models import User
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductListResponse,
    ProductRead,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)
from app.modules.products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


def get_product_service() -> ProductService:
    """Provide the ProductService instance for FastAPI dependency injection."""
    return ProductService()


@router.get("", response_model=ProductListResponse, status_code=status.HTTP_200_OK)
def list_products(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductListResponse:
    """List products with current inventory balance (ACTIVE Admin/Staff)."""
    return service.list_products(session, page=page, page_size=page_size)


@router.get(
    "/{product_id}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
)
def get_product(
    product_id: Annotated[int, Path(ge=1)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductRead:
    """Retrieve a single product with current inventory balance (ACTIVE Admin/Staff)."""
    return service.get_product(session, product_id)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductRead:
    """Create a product and its zero-stock inventory atomically (Admin only)."""
    return service.create(session, payload)


@router.patch(
    "/{product_id}",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
)
def update_product(
    product_id: Annotated[int, Path(ge=1)],
    payload: ProductUpdateRequest,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductRead:
    """Update whitelisted product fields without altering stock (Admin only)."""
    return service.update(session, product_id, payload)


@router.patch(
    "/{product_id}/status",
    response_model=ProductRead,
    status_code=status.HTTP_200_OK,
)
def update_product_status(
    product_id: Annotated[int, Path(ge=1)],
    payload: ProductStatusUpdateRequest,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductRead:
    """Activate or deactivate a product while preserving stock (Admin only)."""
    return service.update_status(session, product_id, payload)
