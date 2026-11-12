"""HTTP boundary for Purchase Receipt endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.schemas import (
    ReceiptCreateRequest,
    ReceiptRead,
    ReceiptUpdateRequest,
)

router = APIRouter(prefix="/purchase-receipts", tags=["purchase-receipts"])


def get_receipt_draft_service() -> ReceiptDraftService:
    """Dependency provider for ReceiptDraftService."""
    return ReceiptDraftService()


@router.post(
    "",
    response_model=ReceiptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_receipt(
    current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReceiptDraftService, Depends(get_receipt_draft_service)],
    payload: ReceiptCreateRequest,
) -> ReceiptRead:
    """Create a new DRAFT purchase receipt (Admin only)."""
    try:
        result = service.create_draft(
            session,
            actor_id=current_admin.id,
            supplier_id=payload.supplier_id,
            items=payload.items,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


@router.patch(
    "/{receipt_id}",
    response_model=ReceiptRead,
    status_code=status.HTTP_200_OK,
)
def update_purchase_receipt(
    receipt_id: Annotated[int, Path(gt=0, description="Purchase receipt ID")],
    current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReceiptDraftService, Depends(get_receipt_draft_service)],
    payload: ReceiptUpdateRequest,
) -> ReceiptRead:
    """Update a DRAFT purchase receipt with optimistic locking (Admin only)."""
    try:
        result = service.update_draft(
            session,
            actor_id=current_admin.id,
            receipt_id=receipt_id,
            expected_draft_version=payload.expected_draft_version,
            supplier_id=payload.supplier_id,
            items=payload.items,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


@router.get(
    "/{receipt_id}",
    response_model=ReceiptRead,
    status_code=status.HTTP_200_OK,
)
def get_purchase_receipt(
    receipt_id: Annotated[int, Path(gt=0, description="Purchase receipt ID")],
    _current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReceiptDraftService, Depends(get_receipt_draft_service)],
) -> ReceiptRead:
    """Fetch a purchase receipt by ID with its line items (Admin only)."""
    return service.get_receipt(session, receipt_id=receipt_id)
