"""FastAPI router for Category management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    get_current_active_user,
    require_active_admin,
)
from app.modules.auth.models import User
from app.modules.categories.models import CategoryStatus
from app.modules.categories.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryRead,
    CategoryStatusUpdate,
    CategoryUpdate,
)
from app.modules.categories.service import CategoryService

category_router = APIRouter(prefix="/categories", tags=["categories"])


def get_category_service() -> CategoryService:
    return CategoryService()


@category_router.get(
    "",
    response_model=CategoryListResponse,
    status_code=status.HTTP_200_OK,
)
def list_categories(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CategoryService, Depends(get_category_service)],
    page: Annotated[int, Query(ge=1, description="Trang cần lấy")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Số lượng mỗi trang")
    ] = 20,
    status: Annotated[
        CategoryStatus | None, Query(description="Lọc theo trạng thái")
    ] = None,
    search: Annotated[
        str | None, Query(max_length=120, description="Tìm theo tên")
    ] = None,
) -> CategoryListResponse:
    """Retrieve a paginated list of categories
    (accessible by active Staff and Admin)."""
    return service.list_categories(
        session,
        page=page,
        page_size=page_size,
        status=status.value if status else None,
        search=search,
    )


@category_router.get(
    "/{id}",
    response_model=CategoryRead,
    status_code=status.HTTP_200_OK,
)
def get_category(
    id: Annotated[int, Path(ge=1, description="Mã danh mục")],
    _current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryRead:
    """Retrieve details of a single category (accessible by active Staff and Admin)."""
    category = service.get_by_id(session, id)
    return CategoryRead.model_validate(category)


@category_router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryRead:
    """Create a new category (Admin only)."""
    category = service.create_category(session, data)
    return CategoryRead.model_validate(category)


@category_router.patch(
    "/{id}",
    response_model=CategoryRead,
    status_code=status.HTTP_200_OK,
)
def update_category(
    id: Annotated[int, Path(ge=1, description="Mã danh mục")],
    data: CategoryUpdate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryRead:
    """Partially update category details (Admin only)."""
    category = service.update_category(session, id, data)
    return CategoryRead.model_validate(category)


@category_router.patch(
    "/{id}/status",
    response_model=CategoryRead,
    status_code=status.HTTP_200_OK,
)
def update_category_status(
    id: Annotated[int, Path(ge=1, description="Mã danh mục")],
    data: CategoryStatusUpdate,
    _admin_user: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryRead:
    """Change category status (ACTIVE/INACTIVE, Admin only)."""
    category = service.update_category_status(session, id, data)
    return CategoryRead.model_validate(category)
