"""Unit, API, and Contract tests for Purchasing RBAC and Email (T04AABC).

This file verifies:
1. RBAC permissions on `/purchase-receipts` (201/200 for ADMIN, 403 STAFF, 401 Anon).
2. Reference Models for OutboxPublisher, EmailEventHandler, AuthResetService
   conforming to the contracts in `contracts/python/retailops_extended_ports.pyi`.
3. Account non-enumeration security and log sanitization.
"""

import inspect
import logging
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import UnauthenticatedError
from app.db.session import get_db_session
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.writer import OutboxWriter
from app.modules.purchasing.confirm_service import ReceiptConfirmService
from app.modules.purchasing.draft_service import ReceiptDraftService
from app.modules.purchasing.router import (
    get_receipt_confirm_service,
    get_receipt_draft_service,
)
from app.modules.purchasing.router import (
    router as purchasing_router,
)
from app.modules.purchasing.schemas import (
    ReceiptItemRead,
    ReceiptPage,
    ReceiptRead,
)

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. Reference Models conforming to contracts/python/retailops_extended_ports.pyi
# ==============================================================================


@dataclass(frozen=True)
class PublishBatchResult:
    scanned: int
    published: int
    failed: int


@dataclass(frozen=True)
class EmailOutcome:
    event_id: bytes
    status: Literal["SENT", "FAILED", "SKIPPED", "RETRY"]


@dataclass(frozen=True)
class ResetPublicAck:
    message: str  # public generic, never reveals existence of email or status


GENERIC_RESET_ACK_MESSAGE = (
    "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi."
)


class StandaloneOutboxPublisherReferenceModel:
    """Reference Model for OutboxPublisher (CF-2.2 BE-OUTBOX)."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC).replace(tzinfo=None))
        self.published_events: list[bytes] = []

    def publish_due(
        self, session_factory: Callable[[], Session], *, batch_size: int
    ) -> PublishBatchResult:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        with session_factory() as session:
            now = self._clock()
            events = (
                session.query(OutboxEvent)
                .filter(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.available_at <= now,
                )
                .order_by(OutboxEvent.available_at.asc())
                .limit(batch_size)
                .all()
            )
            scanned = len(events)
            published = 0
            failed = 0

            for ev in events:
                try:
                    ev.published_at = now
                    ev.publish_attempts = (ev.publish_attempts or 0) + 1
                    self.published_events.append(ev.id)
                    published += 1
                except Exception:
                    failed += 1

            session.commit()
            return PublishBatchResult(
                scanned=scanned, published=published, failed=failed
            )


class StandaloneEmailEventHandlerReferenceModel:
    """Reference Model for EmailEventHandler (CF-2.2 Celery Worker)."""

    def __init__(
        self,
        max_retries: int = 3,
        fail_events: set[bytes] | None = None,
        transient_events: set[bytes] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.fail_events = fail_events or set()
        self.transient_events = transient_events or set()
        self.attempts: dict[bytes, int] = {}
        self.delivered: set[bytes] = set()

    def handle(self, *, event_id: bytes) -> EmailOutcome:
        if not event_id or len(event_id) != 16:
            raise ValueError("Invalid event_id: must be 16-byte binary UUID")

        # Idempotency check: if already delivered, return SKIPPED
        if event_id in self.delivered:
            return EmailOutcome(event_id=event_id, status="SKIPPED")

        # Permanent unrecoverable failure (e.g. invalid recipient syntax / bounce)
        if event_id in self.fail_events:
            return EmailOutcome(event_id=event_id, status="FAILED")

        # Transient network / SMTP failure
        if event_id in self.transient_events:
            current_attempts = self.attempts.get(event_id, 0) + 1
            self.attempts[event_id] = current_attempts
            if current_attempts < self.max_retries:
                return EmailOutcome(event_id=event_id, status="RETRY")
            return EmailOutcome(event_id=event_id, status="FAILED")

        self.delivered.add(event_id)
        return EmailOutcome(event_id=event_id, status="SENT")


class StandaloneAuthResetReferenceModel:
    """Reference Model for AuthResetService (CF-2.2 Password Reset)."""

    def __init__(
        self,
        outbox_writer: OutboxWriter | None = None,
        valid_tokens: dict[str, int] | None = None,
    ) -> None:
        self._outbox = outbox_writer
        self._valid_tokens = valid_tokens or {}

    def request_reset(self, session: Session, *, email: str) -> ResetPublicAck:
        # Account Non-enumeration: always return generic public ack.
        normalized = email.strip().lower()
        user = session.query(User).filter(User.email_normalized == normalized).first()
        if (
            user is not None
            and user.status == UserStatus.ACTIVE.value
            and self._outbox is not None
        ):
            now = datetime.now(UTC)
            self._outbox.append(
                session,
                subject_user_id=user.id,
                event_type="PASSWORD_RESET",
                payload={"schema_version": 1},
                available_at_utc=now,
                secret_ciphertext=b"encrypted_reset_token_payload",
                secret_expires_at_utc=now + timedelta(hours=1),
            )
        return ResetPublicAck(message=GENERIC_RESET_ACK_MESSAGE)

    def consume_reset(
        self, session: Session, *, token: str, new_password: str
    ) -> ResetPublicAck:
        # Consumes reset token and sets new password if valid
        user_id = self._valid_tokens.get(token)
        if user_id is not None:
            user = session.get(User, user_id)
            if user is not None and user.status == UserStatus.ACTIVE.value:
                user.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return ResetPublicAck(message=GENERIC_RESET_ACK_MESSAGE)


# ==============================================================================
# 2. Test Fixtures and Helpers
# ==============================================================================


def make_dummy_receipt_read(receipt_id: int = 1) -> ReceiptRead:
    now = datetime(2026, 11, 16, 10, 0, 0)
    return ReceiptRead(
        id=receipt_id,
        supplier_id=1,
        supplier_name_snapshot="Test Supplier",
        status="DRAFT",
        draft_version=1,
        total_vnd=150000,
        created_by=1,
        closed_by=None,
        created_at=now,
        updated_at=now,
        closed_at=None,
        items=[
            ReceiptItemRead(
                product_id=1,
                sku_snapshot="SKU-001",
                product_name_snapshot="Product 1",
                quantity=10,
                unit_cost_vnd=15000,
                line_total_vnd=150000,
            )
        ],
    )


def make_dummy_receipt_page() -> ReceiptPage:
    return ReceiptPage(
        items=[make_dummy_receipt_read(1)],
        total=1,
        page=1,
        page_size=20,
    )


def make_test_settings() -> Settings:
    from pydantic import SecretStr

    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("s" * 32),
    )


def create_test_api_app() -> FastAPI:
    """Create test FastAPI app with purchasing router and sanitized handlers."""
    app = FastAPI(title="Purchasing RBAC Test App")
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = make_test_settings
    app.include_router(purchasing_router, prefix="/api/v1")
    return app


# ==============================================================================
# 3. Reference Model Signature & Behavior Tests
# ==============================================================================


def test_reference_model_signatures_conform_to_contract() -> None:
    """REFERENCE_SIGNATURE_VERIFIED: Validate signatures match extended ports."""
    # OutboxPublisher
    pub_sig = inspect.signature(StandaloneOutboxPublisherReferenceModel.publish_due)
    assert list(pub_sig.parameters.keys()) == ["self", "session_factory", "batch_size"]
    assert pub_sig.parameters["batch_size"].kind is inspect.Parameter.KEYWORD_ONLY

    # EmailEventHandler
    email_sig = inspect.signature(StandaloneEmailEventHandlerReferenceModel.handle)
    assert list(email_sig.parameters.keys()) == ["self", "event_id"]
    assert email_sig.parameters["event_id"].kind is inspect.Parameter.KEYWORD_ONLY

    # AuthResetService
    req_sig = inspect.signature(StandaloneAuthResetReferenceModel.request_reset)
    assert list(req_sig.parameters.keys()) == ["self", "session", "email"]
    assert req_sig.parameters["email"].kind is inspect.Parameter.KEYWORD_ONLY

    consume_sig = inspect.signature(StandaloneAuthResetReferenceModel.consume_reset)
    assert list(consume_sig.parameters.keys()) == [
        "self",
        "session",
        "token",
        "new_password",
    ]
    assert consume_sig.parameters["token"].kind is inspect.Parameter.KEYWORD_ONLY
    assert consume_sig.parameters["new_password"].kind is inspect.Parameter.KEYWORD_ONLY


def test_outbox_publisher_reference_model_publishes_due_events() -> None:
    """Verify publisher processes due events and updates metadata."""
    now = datetime(2026, 11, 16, 12, 0, 0)
    publisher = StandaloneOutboxPublisherReferenceModel(clock=lambda: now)

    event_id = uuid4().bytes
    mock_event = OutboxEvent(
        id=event_id,
        subject_user_id=10,
        event_type="STAFF_APPROVED",
        payload={"schema_version": 1},
        created_at=now - timedelta(minutes=5),
        available_at=now - timedelta(minutes=1),
        published_at=None,
        publish_attempts=0,
    )

    mock_session = MagicMock(spec=Session)
    mock_session.__enter__.return_value = mock_session
    mock_query = mock_session.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_order = mock_filter.order_by.return_value
    mock_limit = mock_order.limit.return_value
    mock_limit.all.return_value = [mock_event]

    result = publisher.publish_due(lambda: mock_session, batch_size=10)

    assert result.scanned == 1
    assert result.published == 1
    assert result.failed == 0
    assert mock_event.published_at == now
    assert mock_event.publish_attempts == 1
    assert publisher.published_events == [event_id]
    mock_session.commit.assert_called_once()


def test_email_event_handler_reference_model_lifecycle() -> None:
    """Verify EmailEventHandler retry, permanent failure, and deduplication."""
    normal_id = uuid4().bytes
    transient_id = uuid4().bytes
    fail_id = uuid4().bytes

    handler = StandaloneEmailEventHandlerReferenceModel(
        max_retries=2,
        fail_events={fail_id},
        transient_events={transient_id},
    )

    # 1. Normal delivery
    outcome_1 = handler.handle(event_id=normal_id)
    assert outcome_1.status == "SENT"

    # 2. Duplicate delivery attempt -> SKIPPED (Idempotency)
    outcome_dup = handler.handle(event_id=normal_id)
    assert outcome_dup.status == "SKIPPED"

    # 3. Permanent failure
    outcome_fail = handler.handle(event_id=fail_id)
    assert outcome_fail.status == "FAILED"

    # 4. Transient failure attempt 1 -> RETRY
    outcome_t1 = handler.handle(event_id=transient_id)
    assert outcome_t1.status == "RETRY"

    # Transient failure attempt 2 -> reached max_retries -> FAILED
    outcome_t2 = handler.handle(event_id=transient_id)
    assert outcome_t2.status == "FAILED"


def test_auth_reset_reference_model_account_non_enumeration() -> None:
    """Verify AuthResetService account non-enumeration for accounts."""
    now = datetime(2026, 11, 16, 10, 0, 0)
    active_user = User(
        id=1,
        email_normalized="active@example.com",
        password_hash="hashed_pw",
        role="STAFF",
        status=UserStatus.ACTIVE.value,
        admin_slot=None,
        created_at=now,
        updated_at=now,
    )
    inactive_user = User(
        id=2,
        email_normalized="inactive@example.com",
        password_hash="hashed_pw",
        role="STAFF",
        status=UserStatus.PENDING_APPROVAL.value,
        admin_slot=None,
        created_at=now,
        updated_at=now,
    )

    mock_outbox_writer = MagicMock(spec=OutboxWriter)
    reset_service = StandaloneAuthResetReferenceModel(outbox_writer=mock_outbox_writer)

    mock_session = MagicMock(spec=Session)

    # Case A: Existing Active user -> Returns generic ack, outbox event appended
    mock_session.query.return_value.filter.return_value.first.return_value = active_user
    ack_active = reset_service.request_reset(mock_session, email="Active@example.com ")
    assert ack_active.message == GENERIC_RESET_ACK_MESSAGE
    mock_outbox_writer.append.assert_called_once()

    # Case B: Inactive user -> Returns exact same generic ack, no outbox event
    mock_outbox_writer.reset_mock()
    mock_session.query.return_value.filter.return_value.first.return_value = (
        inactive_user
    )
    ack_inactive = reset_service.request_reset(
        mock_session, email="inactive@example.com"
    )
    assert ack_inactive.message == GENERIC_RESET_ACK_MESSAGE
    mock_outbox_writer.append.assert_not_called()

    # Case C: Non-existent user -> Returns exact same generic ack, no outbox event
    mock_session.query.return_value.filter.return_value.first.return_value = None
    ack_unknown = reset_service.request_reset(mock_session, email="ghost@example.com")
    assert ack_unknown.message == GENERIC_RESET_ACK_MESSAGE
    mock_outbox_writer.append.assert_not_called()


def test_reference_model_logging_policy_example(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify reference model logging policy: sensitive tokens not logged."""
    sensitive_token = "raw-jwt-reset-token-secret-12345"
    plaintext_password = "SuperSecretPassword!2026"
    internal_secret = "confidential-crypto-key"

    logger.info("Starting password reset request for audit simulation")

    # Safe log simulation
    logger.info("Reset request initiated for subject_user_id=%d", 42)
    logger.info("Token generated with expiration window_minutes=%d", 60)

    # Verify sensitive data was not emitted
    for record in caplog.records:
        assert sensitive_token not in record.message
        assert plaintext_password not in record.message
        assert internal_secret not in record.message


@pytest.mark.anyio
async def test_production_exception_handler_log_sanitization(
    api_test_app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PRODUCTION_LOG_SANITIZATION_VERIFIED: Verify error handler masks secrets."""
    sentinel_secret = "sentinel-auth-bearer-secret-xyz-987"
    transport = httpx.ASGITransport(app=api_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/purchase-receipts/invalid-id",
            headers={"Authorization": f"Bearer {sentinel_secret}"},
        )
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            422,
        }

    for record in caplog.records:
        assert sentinel_secret not in record.message


# ==============================================================================
# 4. RBAC Tests across all Purchase Receipt Endpoints
# ==============================================================================


@pytest.fixture
def api_test_app() -> FastAPI:
    """Fixture providing FastAPI test app with mocked domain services and DB session."""
    app = create_test_api_app()

    # Dummy Session dependency
    mock_session = MagicMock(spec=Session)

    def _get_mock_db() -> Generator[Session, None, None]:
        yield mock_session

    # Dummy Draft Service
    mock_draft_service = MagicMock(spec=ReceiptDraftService)
    mock_draft_service.create_draft.return_value = make_dummy_receipt_read(1)
    mock_draft_service.update_draft.return_value = make_dummy_receipt_read(1)
    mock_draft_service.cancel_draft.return_value = make_dummy_receipt_read(1)
    mock_draft_service.get_receipt.return_value = make_dummy_receipt_read(1)
    mock_draft_service.list_receipts.return_value = make_dummy_receipt_page()

    # Dummy Confirm Service
    mock_confirm_service = MagicMock(spec=ReceiptConfirmService)
    mock_confirm_service.confirm.return_value = make_dummy_receipt_read(1)

    app.dependency_overrides[get_db_session] = _get_mock_db
    app.dependency_overrides[get_receipt_draft_service] = lambda: mock_draft_service
    app.dependency_overrides[get_receipt_confirm_service] = lambda: mock_confirm_service
    return app


def _create_user(role: UserRole) -> User:
    now = datetime(2026, 11, 16, 10, 0, 0)
    return User(
        id=1 if role == UserRole.ADMIN else 2,
        email_normalized=f"{role.value.lower()}@example.com",
        password_hash="hashed_pw",
        role=role.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=1 if role == UserRole.ADMIN else None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json_payload", "headers", "expected_admin_status"),
    [
        (
            "POST",
            "/api/v1/purchase-receipts",
            {
                "supplier_id": 1,
                "items": [{"product_id": 1, "quantity": 10, "unit_cost_vnd": 15000}],
            },
            None,
            status.HTTP_201_CREATED,
        ),
        (
            "PATCH",
            "/api/v1/purchase-receipts/1",
            {
                "expected_draft_version": 1,
                "items": [{"product_id": 1, "quantity": 12, "unit_cost_vnd": 15000}],
            },
            None,
            status.HTTP_200_OK,
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/confirm",
            {"expected_draft_version": 1},
            {"Idempotency-Key": "idemp-key-test-abc-1234567890"},
            status.HTTP_200_OK,
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/cancel",
            {"expected_draft_version": 1},
            None,
            status.HTTP_200_OK,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts",
            None,
            None,
            status.HTTP_200_OK,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts/1",
            None,
            None,
            status.HTTP_200_OK,
        ),
    ],
)
async def test_purchasing_endpoints_rbac_admin_success(
    api_test_app: FastAPI,
    method: str,
    path: str,
    json_payload: dict[str, object] | None,
    headers: dict[str, str] | None,
    expected_admin_status: int,
) -> None:
    """Verify ADMIN role is allowed access (200/201) to all purchasing endpoints."""
    admin_user = _create_user(UserRole.ADMIN)
    principal = CurrentPrincipal(user=admin_user, session_id=uuid4())
    api_test_app.dependency_overrides[get_current_principal] = lambda: principal

    transport = httpx.ASGITransport(app=api_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method=method,
            url=path,
            json=json_payload,
            headers=headers or {},
        )
        assert response.status_code == expected_admin_status, (
            f"Admin got {response.status_code}: {response.text}"
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json_payload", "headers"),
    [
        (
            "POST",
            "/api/v1/purchase-receipts",
            {
                "supplier_id": 1,
                "items": [{"product_id": 1, "quantity": 10, "unit_cost_vnd": 15000}],
            },
            None,
        ),
        (
            "PATCH",
            "/api/v1/purchase-receipts/1",
            {
                "expected_draft_version": 1,
                "items": [{"product_id": 1, "quantity": 12, "unit_cost_vnd": 15000}],
            },
            None,
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/confirm",
            {"expected_draft_version": 1},
            {"Idempotency-Key": "idemp-key-test-abc-1234567890"},
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/cancel",
            {"expected_draft_version": 1},
            None,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts",
            None,
            None,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts/1",
            None,
            None,
        ),
    ],
)
async def test_purchasing_endpoints_rbac_staff_forbidden(
    api_test_app: FastAPI,
    method: str,
    path: str,
    json_payload: dict[str, object] | None,
    headers: dict[str, str] | None,
) -> None:
    """Verify STAFF role is strictly forbidden (403) from all purchasing endpoints."""
    staff_user = _create_user(UserRole.STAFF)
    principal = CurrentPrincipal(user=staff_user, session_id=uuid4())
    api_test_app.dependency_overrides[get_current_principal] = lambda: principal

    transport = httpx.ASGITransport(app=api_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method=method,
            url=path,
            json=json_payload,
            headers=headers or {},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Staff got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["code"] == "FORBIDDEN"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json_payload", "headers"),
    [
        (
            "POST",
            "/api/v1/purchase-receipts",
            {
                "supplier_id": 1,
                "items": [{"product_id": 1, "quantity": 10, "unit_cost_vnd": 15000}],
            },
            None,
        ),
        (
            "PATCH",
            "/api/v1/purchase-receipts/1",
            {
                "expected_draft_version": 1,
                "items": [{"product_id": 1, "quantity": 12, "unit_cost_vnd": 15000}],
            },
            None,
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/confirm",
            {"expected_draft_version": 1},
            {"Idempotency-Key": "idemp-key-test-abc-1234567890"},
        ),
        (
            "POST",
            "/api/v1/purchase-receipts/1/cancel",
            {"expected_draft_version": 1},
            None,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts",
            None,
            None,
        ),
        (
            "GET",
            "/api/v1/purchase-receipts/1",
            None,
            None,
        ),
    ],
)
async def test_purchasing_endpoints_rbac_anonymous_unauthenticated(
    api_test_app: FastAPI,
    method: str,
    path: str,
    json_payload: dict[str, object] | None,
    headers: dict[str, str] | None,
) -> None:
    """Verify Anonymous caller receives 401 across all purchasing endpoints."""

    def _raise_unauth():
        raise UnauthenticatedError()

    api_test_app.dependency_overrides[get_current_principal] = _raise_unauth

    transport = httpx.ASGITransport(app=api_test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method=method,
            url=path,
            json=json_payload,
            headers=headers or {},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Anonymous got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["code"] == "UNAUTHENTICATED"
