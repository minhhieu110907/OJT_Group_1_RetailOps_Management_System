"""HTTP boundary for checkout."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.inventory.service import InventoryService
from app.modules.sales.inventory_port import InventoryServicePort
from app.modules.sales.schemas import CancelOrderRequest, CheckoutRequest, OrderRead
from app.modules.sales.service import CheckoutService, OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


def get_inventory_service() -> InventoryServicePort:
    """Provide the merged CF-02 InventoryService implementation."""
    return InventoryService()


def get_checkout_service(
    inventory: Annotated[InventoryServicePort, Depends(get_inventory_service)],
) -> CheckoutService:
    return CheckoutService(inventory)


def get_order_service(
    inventory: Annotated[InventoryServicePort, Depends(get_inventory_service)],
) -> OrderService:
    return OrderService(inventory)


@router.post(
    "/checkout",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
)
def checkout(
    payload: CheckoutRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[CheckoutService, Depends(get_checkout_service)],
) -> OrderRead:
    return service.checkout(
        session,
        actor_id=current_user.id,
        idempotency_key=idempotency_key,
        items=payload.items,
    )


@router.post(
    "/{order_id}/cancel",
    response_model=OrderRead,
    status_code=status.HTTP_200_OK,
)
def cancel_order(
    order_id: Annotated[int, Path(gt=0)],
    payload: CancelOrderRequest,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderRead:
    return service.cancel(
        session,
        actor_id=current_user.id,
        actor_role=str(current_user.role),
        order_id=order_id,
        reason=payload.reason,
        idempotency_key=idempotency_key,
    )
