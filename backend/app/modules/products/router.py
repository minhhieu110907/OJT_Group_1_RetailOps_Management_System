"""HTTP boundary for Product catalog endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    get_current_active_user,
    require_active_admin,
)
from app.modules.auth.models import User
from app.modules.products.import_service import (
    MAX_CSV_FILE_BYTES,
    ProductImportService,
    extract_csv_upload,
)
from app.modules.products.models import CatalogStatus
from app.modules.products.schemas import (
    MAX_PRODUCT_SEARCH_LENGTH,
    ProductCreateRequest,
    ProductImportResponse,
    ProductListResponse,
    ProductRead,
    ProductSortOrder,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)
from app.modules.products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


def get_product_service() -> ProductService:
    """Provide the ProductService instance for FastAPI dependency injection."""
    return ProductService()


def get_product_import_service(
    product_service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductImportService:
    """Provide ProductImportService reusing the injected ProductService."""
    return ProductImportService(product_service=product_service)


@router.post(
    "/import/csv",
    response_model=ProductImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_products_csv(
    request: Request,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    import_service: Annotated[
        ProductImportService, Depends(get_product_import_service)
    ],
) -> ProductImportResponse:
    """Import products from CSV with row-by-row validation & partial success (Admin)."""
    max_wire_bytes = MAX_CSV_FILE_BYTES + 65_536
    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_wire_bytes:
            raise DomainValidationError(
                "Kích thước tệp CSV vượt quá giới hạn tối đa 2MB."
            )
        chunks.append(chunk)

    raw_bytes, filename = extract_csv_upload(
        b"".join(chunks), content_type=request.headers.get("content-type")
    )
    return import_service.import_csv(session, raw_bytes, filename=filename)


@router.get("", response_model=ProductListResponse, status_code=status.HTTP_200_OK)
def list_products(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ProductService, Depends(get_product_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=MAX_PRODUCT_SEARCH_LENGTH)] = None,
    category_id: Annotated[int | None, Query(ge=1)] = None,
    status: Annotated[CatalogStatus | None, Query()] = None,
    sort: Annotated[ProductSortOrder, Query()] = ProductSortOrder.CREATED_DESC,
) -> ProductListResponse:
    """List products with search, filter, sort, and current inventory balance."""
    return service.list_products(
        session,
        page=page,
        page_size=page_size,
        search=search,
        category_id=category_id,
        status=status,
        sort=sort,
    )


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
