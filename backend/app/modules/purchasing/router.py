"""HTTP boundary for Purchase Receipt endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import commit_session, get_db_session
from app.modules.auth.dependencies import require_active_admin
from app.modules.auth.models import User
from app.modules.purchasing.confirmation_service import ReceiptConfirmationService
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.schemas import (
    ReceiptCreateRequest,
    ReceiptPage,
    ReceiptRead,
    ReceiptUpdateRequest,
    ReceiptVersionRequest,
)

router = APIRouter(prefix="/purchase-receipts", tags=["purchase-receipts"])


def get_receipt_draft_service() -> ReceiptDraftService:
    """Dependency provider for ReceiptDraftService."""
    return ReceiptDraftService()


def get_receipt_confirmation_service() -> ReceiptConfirmationService:
    """Dependency provider for ReceiptConfirmationService."""
    return ReceiptConfirmationService()


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


@router.post(
    "/{receipt_id}/confirm",
    response_model=ReceiptRead,
    status_code=status.HTTP_200_OK,
)
def confirm_purchase_receipt(
    receipt_id: Annotated[int, Path(gt=0, description="Purchase receipt ID")],
    payload: ReceiptVersionRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[
        ReceiptConfirmationService,
        Depends(get_receipt_confirmation_service),
    ],
) -> ReceiptRead:
    """Confirm a DRAFT purchase receipt and increase stock atomically (Admin only)."""
    try:
        result = service.confirm_receipt(
            session,
            actor_id=current_admin.id,
            receipt_id=receipt_id,
            expected_draft_version=payload.expected_draft_version,
            idempotency_key=idempotency_key,
        )
        commit_session(session)
        return result
    except Exception:
        session.rollback()
        raise


@router.post(
    "/{receipt_id}/cancel",
    response_model=ReceiptRead,
    status_code=status.HTTP_200_OK,
)
def cancel_purchase_receipt(
    receipt_id: Annotated[int, Path(gt=0, description="Purchase receipt ID")],
    current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReceiptDraftService, Depends(get_receipt_draft_service)],
    payload: ReceiptVersionRequest,
) -> ReceiptRead:
    """Cancel a DRAFT purchase receipt with optimistic locking (Admin only)."""
    try:
        result = service.cancel_draft(
            session,
            actor_id=current_admin.id,
            receipt_id=receipt_id,
            expected_draft_version=payload.expected_draft_version,
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


@router.get(
    "",
    response_model=ReceiptPage,
    status_code=status.HTTP_200_OK,
)
def list_purchase_receipts(
    _current_admin: Annotated[User, Depends(require_active_admin)],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReceiptDraftService, Depends(get_receipt_draft_service)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit")] = 20,
    status: Annotated[
        str | None,
        Query(description="Status filter: DRAFT, CONFIRMED, CANCELLED"),
    ] = None,
    supplier_id: Annotated[
        int | None,
        Query(ge=1, description="Supplier ID filter"),
    ] = None,
    from_date: Annotated[
        date | None,
        Query(description="From date inclusive (YYYY-MM-DD Vietnam time)"),
    ] = None,
    to_date: Annotated[
        date | None,
        Query(description="To date inclusive (YYYY-MM-DD Vietnam time)"),
    ] = None,
) -> ReceiptPage:
    """List purchase receipts with pagination and filters (Admin only)."""
    return service.list_receipts(
        session,
        page=page,
        page_size=page_size,
        status=status,
        supplier_id=supplier_id,
        from_date=from_date,
        to_date=to_date,
    )


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
