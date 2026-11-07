"""FastAPI router for Supplier management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User
from app.modules.suppliers.models import SupplierStatus
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierListResponse,
    SupplierRead,
    SupplierStatusUpdate,
    SupplierUpdate,
)
from app.modules.suppliers.service import SupplierService

supplier_router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def get_supplier_service() -> SupplierService:
    return SupplierService()


@supplier_router.get(
    "",
    response_model=SupplierListResponse,
    status_code=status.HTTP_200_OK,
)
def list_suppliers(
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SupplierService, Depends(get_supplier_service)],
    page: Annotated[int, Query(ge=1, description="Trang cần lấy")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Số lượng mỗi trang")
    ] = 20,
    status: Annotated[
        SupplierStatus | None, Query(description="Lọc theo trạng thái")
    ] = None,
    search: Annotated[
        str | None, Query(max_length=160, description="Tìm theo tên")
    ] = None,
) -> SupplierListResponse:
    """Retrieve a paginated list of suppliers (Admin only)."""
    return service.list_suppliers(
        session,
        page=page,
        page_size=page_size,
        status=status.value if status else None,
        search=search,
    )


@supplier_router.get(
    "/{id}",
    response_model=SupplierRead,
    status_code=status.HTTP_200_OK,
)
def get_supplier(
    id: Annotated[int, Path(ge=1, description="Mã nhà cung cấp")],
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SupplierService, Depends(get_supplier_service)],
) -> SupplierRead:
    """Retrieve details of a single supplier (Admin only)."""
    supplier = service.get_by_id(session, id)
    return SupplierRead.model_validate(supplier)


@supplier_router.post(
    "",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    data: SupplierCreate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SupplierService, Depends(get_supplier_service)],
) -> SupplierRead:
    """Create a new supplier (Admin only)."""
    supplier = service.create_supplier(session, data)
    return SupplierRead.model_validate(supplier)


@supplier_router.patch(
    "/{id}",
    response_model=SupplierRead,
    status_code=status.HTTP_200_OK,
)
def update_supplier(
    id: Annotated[int, Path(ge=1, description="Mã nhà cung cấp")],
    data: SupplierUpdate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SupplierService, Depends(get_supplier_service)],
) -> SupplierRead:
    """Update supplier information (Admin only)
    supports explicit null to clear contact fields."""
    supplier = service.update_supplier(session, id, data)
    return SupplierRead.model_validate(supplier)


@supplier_router.patch(
    "/{id}/status",
    response_model=SupplierRead,
    status_code=status.HTTP_200_OK,
)
def update_supplier_status(
    id: Annotated[int, Path(ge=1, description="Mã nhà cung cấp")],
    data: SupplierStatusUpdate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SupplierService, Depends(get_supplier_service)],
) -> SupplierRead:
    """Change supplier status (ACTIVE/INACTIVE, Admin only)."""
    supplier = service.update_supplier_status(session, id, data)
    return SupplierRead.model_validate(supplier)
