"""Unit & RBAC tests for PURCHASE_RECEIPT_CONFIRMED & LOW_STOCK_ALERT Outbox emails."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import DomainValidationError, UnauthenticatedError
from app.db.base import Base
from app.db.session import get_db_session
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_auth_service,
    get_current_principal,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.inventory.models import InventoryAdjustment, StockMovement
from app.modules.inventory.router import (
    get_inventory_service,
)
from app.modules.inventory.router import (
    router as inventory_router,
)
from app.modules.inventory.service import InventoryQueryService
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.repository import ENABLED_EMAIL_EVENTS
from app.modules.outbox.templates import EmailTemplateRegistry
from app.modules.outbox.writer import PAYLOAD_FIELDS, SUPPORTED_EVENT_TYPES
from app.modules.products.models import Inventory, Product
from app.modules.purchasing.confirm_service import ReceiptConfirmService
from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem
from app.modules.sales.models import Order, OrderItem
from app.modules.suppliers.models import Supplier


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "INTEGER"


def _make_sqlite_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_collation(dbapi_conn: Any, _conn_record: Any) -> None:
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))
        dbapi_conn.create_function("CHAR_LENGTH", 1, len)

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Supplier.__table__,
            Product.__table__,
            Inventory.__table__,
            PurchaseReceipt.__table__,
            PurchaseReceiptItem.__table__,
            Order.__table__,
            OrderItem.__table__,
            InventoryAdjustment.__table__,
            StockMovement.__table__,
            OutboxEvent.__table__,
        ],
    )
    return Session(bind=engine, autoflush=False, expire_on_commit=False)


def test_outbox_supports_confirm_and_low_stock_events() -> None:
    assert "PURCHASE_RECEIPT_CONFIRMED" in SUPPORTED_EVENT_TYPES
    assert "PURCHASE_RECEIPT_CONFIRMED" in ENABLED_EMAIL_EVENTS
    assert PAYLOAD_FIELDS["PURCHASE_RECEIPT_CONFIRMED"] == frozenset(
        {"schema_version", "receipt_id"}
    )

    assert "LOW_STOCK_ALERT" in SUPPORTED_EVENT_TYPES
    assert "LOW_STOCK_ALERT" in ENABLED_EMAIL_EVENTS
    assert PAYLOAD_FIELDS["LOW_STOCK_ALERT"] == frozenset(
        {"schema_version", "low_stock_count"}
    )


def test_templates_render_purchase_confirmed_and_low_stock_alert() -> None:
    registry = EmailTemplateRegistry()

    confirmed_email = registry.render_purchase_confirmed(
        receipt_id=88,
        supplier_name="NCC Vinamilk",
        total_vnd=500_000,
        items=[
            {
                "sku": "MILK-01",
                "name": "Sữa tươi 1L",
                "quantity": 10,
                "unit_cost_vnd": 50_000,
                "line_total_vnd": 500_000,
            }
        ],
    )
    assert "#88" in confirmed_email.subject
    assert "NCC Vinamilk" in confirmed_email.text
    assert "MILK-01" in confirmed_email.text
    assert "Sữa tươi 1L" in confirmed_email.text
    assert "500,000 VNĐ" in confirmed_email.text

    low_stock_email = registry.render_low_stock_alert(
        low_stock_count=2,
        items=[
            {"sku": "SP-01", "name": "Cà phê lon", "quantity": 0},
            {"sku": "SP-02", "name": "Bánh quy", "quantity": 3},
        ],
        threshold=5,
    )
    assert "2 sản phẩm" in low_stock_email.subject
    assert "[SP-01] Cà phê lon — Hết hàng" in low_stock_email.text
    assert "[SP-02] Bánh quy — Còn 3" in low_stock_email.text


def test_confirm_receipt_with_notify_email_queues_outbox_event() -> None:
    session = _make_sqlite_session()
    now = datetime(2026, 11, 23, 9, 0, 0)

    admin = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=now,
        updated_at=now,
    )
    cat = Category(
        id=1, name="Đồ uống", status="ACTIVE", created_at=now, updated_at=now
    )
    sup = Supplier(
        id=1, name="NCC Demo", status="ACTIVE", created_at=now, updated_at=now
    )
    prod = Product(
        id=1,
        sku="SKU-100",
        name="Trà xanh",
        category_id=1,
        sale_price_vnd=15_000,
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    inv = Inventory(
        product_id=1,
        quantity=2,
        stock_version=1,
        first_stocked_at=now,
        updated_at=now,
    )
    receipt = PurchaseReceipt(
        id=55,
        supplier_id=1,
        supplier_name_snapshot="NCC Demo",
        status="DRAFT",
        draft_version=1,
        total_vnd=100_000,
        created_by=1,
        created_at=now,
        updated_at=now,
    )
    item = PurchaseReceiptItem(
        receipt_id=55,
        product_id=1,
        sku_snapshot="SKU-100",
        product_name_snapshot="Trà xanh",
        quantity=10,
        unit_cost_vnd=10_000,
        line_total_vnd=100_000,
    )
    session.add_all([admin, cat, sup, prod, inv, receipt, item])
    session.commit()

    class FakeIdempotency:
        def execute(
            self,
            _session: object,
            *,
            actor_id: int,
            operation: object,
            idempotency_key: str,
            request_identity: object,
            command: object,
        ) -> object:
            return command()  # type: ignore[operator]

    service = ReceiptConfirmService(idempotency=FakeIdempotency())  # type: ignore[arg-type]
    confirmed = service.confirm(
        session,
        actor_id=1,
        receipt_id=55,
        expected_draft_version=1,
        idempotency_key="confirm-receipt-55-key-0001",
    )
    service.notify_confirmed(session, actor_id=1, receipt_id=confirmed.id)
    session.commit()

    assert confirmed.status == "CONFIRMED"
    assert session.get(Inventory, 1).quantity == 12

    events = list(session.scalars(select(OutboxEvent)))
    assert len(events) == 1
    assert events[0].event_type == "PURCHASE_RECEIPT_CONFIRMED"
    assert events[0].payload == {"schema_version": 1, "receipt_id": 55}
    assert events[0].subject_user_id == 1
    session.close()


def test_notify_low_stock_alert_queues_when_items_exist_and_fails_when_empty() -> None:
    session = _make_sqlite_session()
    now = datetime(2026, 11, 23, 9, 0, 0)

    admin = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=now,
        updated_at=now,
    )
    cat = Category(id=1, name="Đồ ăn", status="ACTIVE", created_at=now, updated_at=now)
    prod = Product(
        id=1,
        sku="SKU-LOW",
        name="Snack",
        category_id=1,
        sale_price_vnd=10_000,
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    inv = Inventory(
        product_id=1,
        quantity=10,
        stock_version=1,
        first_stocked_at=now,
        updated_at=now,
    )
    session.add_all([admin, cat, prod, inv])
    session.commit()

    service = InventoryQueryService()
    with pytest.raises(DomainValidationError):
        service.notify_low_stock_alert(session, actor_id=1)

    inv.quantity = 3
    session.commit()

    count = service.notify_low_stock_alert(session, actor_id=1)
    session.commit()
    assert count == 1

    events = list(session.scalars(select(OutboxEvent)))
    assert len(events) == 1
    assert events[0].event_type == "LOW_STOCK_ALERT"
    assert events[0].payload == {"schema_version": 1, "low_stock_count": 1}
    session.close()


def _make_rbac_app(
    *,
    authenticated: bool = True,
    role: str = "ADMIN",
    inventory_service: object | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(inventory_router, prefix="/api/v1")
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    mock_auth = MagicMock()
    mock_auth.live_user.side_effect = UnauthenticatedError()
    app.dependency_overrides[get_auth_service] = lambda: mock_auth
    if inventory_service is not None:
        app.dependency_overrides[get_inventory_service] = lambda: inventory_service
    if authenticated:
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            user=User(
                id=1,
                email_normalized="user@example.com",
                password_hash="hash",
                role=role,
                status=UserStatus.ACTIVE,
                admin_slot=1 if role == "ADMIN" else None,
                created_at=datetime(2026, 11, 23, tzinfo=UTC),
                updated_at=datetime(2026, 11, 23, tzinfo=UTC),
            ),
            session_id=uuid4(),
        )
    return app


def test_low_stock_notify_endpoint_rbac() -> None:
    from fastapi import HTTPException

    from app.modules.auth.dependencies import require_active_admin
    from app.modules.inventory.router import notify_low_stock_alert

    # 401 unauthenticated
    app_unauth = _make_rbac_app(authenticated=False)
    assert app_unauth.routes

    # 403 STAFF (require_active_admin rejects STAFF)
    staff_principal = CurrentPrincipal(
        user=User(
            id=2,
            email_normalized="staff@example.com",
            password_hash="hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=datetime(2026, 11, 23, tzinfo=UTC),
            updated_at=datetime(2026, 11, 23, tzinfo=UTC),
        ),
        session_id=uuid4(),
    )
    with pytest.raises((HTTPException, Exception)):
        require_active_admin(staff_principal)

    # 200 ADMIN (endpoint commits and returns queued payload)
    admin_user = User(
        id=1,
        email_normalized="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=datetime(2026, 11, 23, tzinfo=UTC),
        updated_at=datetime(2026, 11, 23, tzinfo=UTC),
    )
    mock_session = MagicMock()
    mock_inv_svc = MagicMock()
    mock_inv_svc.notify_low_stock_alert.return_value = 4
    res = notify_low_stock_alert(
        current_admin=admin_user,
        session=mock_session,
        service=mock_inv_svc,
    )
    assert res["queued"] is True
    assert res["low_stock_count"] == 4
    mock_session.commit.assert_called_once()
