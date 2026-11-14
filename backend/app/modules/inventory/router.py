"""HTTP endpoints for inventory queries, low-stock, movements, and mutations."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import commit_session, get_db_session
from app.modules.auth.dependencies import (
    get_current_active_user,
    require_active_admin,
)
from app.modules.auth.models import User, UserRole
from app.modules.idempotency import (
    CommandOutcome,
    IdempotencyExecutor,
    IdempotencyOperation,
    validate_idempotency_key,
)
from app.modules.inventory.schemas import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    AdjustRequest,
    AdjustResponse,
    CountAdjustment,
    InventoryPage,
    InventoryRead,
    LowStockPage,
    StockMovementAdminPage,
    StockMovementKind,
    StockMovementPage,
)
from app.modules.inventory.service import (
    InventoryQueryService,
    InventoryService,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])
stock_movements_router = APIRouter(prefix="/stock-movements", tags=["inventory"])


def get_inventory_service() -> InventoryQueryService:
    """FastAPI dependency for obtaining an InventoryQueryService instance."""
    return InventoryQueryService()


def get_inventory_mutation_service() -> InventoryService:
    """FastAPI dependency for obtaining an InventoryService instance."""
    return InventoryService()


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
) -> LowStockPage:
    """Retrieve products at or below the fixed P0 low-stock threshold (5)."""
    return service.get_low_stock(
        session=session,
        page=page,
        page_size=page_size,
        threshold=DEFAULT_LOW_STOCK_THRESHOLD,
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


@router.post(
    "/{product_id}/adjustments",
    response_model=AdjustResponse,
    status_code=status.HTTP_200_OK,
)
def adjust_inventory(
    product_id: Annotated[int, Path(ge=1, description="Mã định danh sản phẩm")],
    payload: AdjustRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[InventoryService, Depends(get_inventory_mutation_service)],
) -> AdjustResponse:
    """Adjust physical inventory balance for a product (Admin only)."""
    clean_key = validate_idempotency_key(idempotency_key)

    def _execute_adjustment() -> CommandOutcome[dict[str, object]]:
        locks = service.lock_for_mutation(session, product_ids=[product_id])
        result = service.adjust_to_count(
            session,
            locks=locks,
            actor_id=current_admin.id,
            adjustment=CountAdjustment(
                product_id=product_id,
                counted_quantity=payload.counted_quantity,
                expected_stock_version=payload.expected_stock_version,
                reason=payload.reason,
            ),
        )
        response_dto = AdjustResponse(
            product_id=result.stock.product_id,
            quantity=result.stock.quantity,
            stock_version=result.stock.stock_version,
            audit_id=result.audit_id,
            movement_created=result.movement_created,
        )
        return CommandOutcome(
            status_code=status.HTTP_200_OK,
            body=response_dto.model_dump(),
        )

    executor = IdempotencyExecutor()
    outcome = executor.execute(
        session,
        actor_id=current_admin.id,
        operation=IdempotencyOperation.INVENTORY_ADJUSTMENT,
        idempotency_key=clean_key,
        request_identity={
            "operation": IdempotencyOperation.INVENTORY_ADJUSTMENT.value,
            "resource_id": product_id,
            "body": payload.model_dump(),
        },
        command=_execute_adjustment,
    )
    commit_session(session)
    return AdjustResponse.model_validate(outcome.body)


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
