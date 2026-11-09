"""HTTP and security integration tests for Suppliers API."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.modules.suppliers.models import Supplier, SupplierStatus


@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        db_host="localhost",
        db_user="retailops",
        db_password=SecretStr("password"),
        db_name="retailops_db",
        jwt_secret=SecretStr("test-jwt-secret-key-for-testing-purposes-123456"),
        csrf_secret=SecretStr("test-csrf-secret-key-for-testing-purposes-123456"),
    )


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Supplier.__table__.create(bind=engine, checkfirst=True)
    yield engine
    Supplier.__table__.drop(bind=engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=db_engine,
    )
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_context(
    mock_settings: Settings,
) -> tuple[AuthService, dict[str, str]]:
    """Create real signed JWT access tokens and live session verification."""
    now = datetime.now(UTC).replace(tzinfo=None)
    expires_at = now + timedelta(hours=4)

    admin = User(
        id=1,
        email_normalized="admin@retailops.test",
        password_hash="mock_hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        created_at=now,
        updated_at=now,
    )
    staff = User(
        id=2,
        email_normalized="staff@retailops.test",
        password_hash="mock_hash",
        role=UserRole.STAFF,
        status=UserStatus.ACTIVE,
        admin_slot=None,
        created_at=now,
        updated_at=now,
    )
    admin_session_id = uuid4()
    staff_session_id = uuid4()
    live_principals = {
        (admin_session_id.bytes, admin.id): admin,
        (staff_session_id.bytes, staff.id): staff,
    }

    class LiveSessionAuthRepo(AuthRepository):
        def find_live_principal(
            self, _session: Session, session_id: bytes, user_id: int, _now: datetime
        ) -> User | None:
            return live_principals.get((session_id, user_id))

    auth_service = AuthService(mock_settings, repository=LiveSessionAuthRepo())
    admin_jwt, _ = auth_service.jwt.issue(
        user_id=admin.id,
        session_id=admin_session_id,
        session_expires_at=expires_at,
        now=now.replace(tzinfo=UTC),
    )
    staff_jwt, _ = auth_service.jwt.issue(
        user_id=staff.id,
        session_id=staff_session_id,
        session_expires_at=expires_at,
        now=now.replace(tzinfo=UTC),
    )
    return auth_service, {"admin": admin_jwt, "staff": staff_jwt}


@pytest.fixture
def app_instance(
    mock_settings: Settings,
    db_session: Session,
    auth_context: tuple[AuthService, dict[str, str]],
):
    """Create FastAPI app using the real auth dependency chain (no principal mock)."""
    app = create_app(mock_settings)
    auth_service, _ = auth_context

    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = lambda: mock_settings
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(
    app_instance, auth_context: tuple[AuthService, dict[str, str]]
) -> AsyncGenerator[httpx.AsyncClient, None]:
    _, tokens = auth_context
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    ) as client:
        yield client


@pytest.fixture
async def staff_client(
    app_instance, auth_context: tuple[AuthService, dict[str, str]]
) -> AsyncGenerator[httpx.AsyncClient, None]:
    _, tokens = auth_context
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {tokens['staff']}"},
    ) as client:
        yield client


@pytest.fixture
async def unauth_client(app_instance) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.anyio
async def test_admin_get_suppliers_success_and_pagination(
    admin_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    """1. Admin GET suppliers list and detail succeeds with filters and pagination."""
    empty_res = await admin_client.get("/api/v1/suppliers")
    assert empty_res.status_code == 200
    assert empty_res.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }

    now = datetime.now(UTC).replace(tzinfo=None)
    s1 = Supplier(
        name="Công ty Nước Giải Khát A",
        contact_email="a@example.com",
        contact_phone="0901111111",
        status=SupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    s2 = Supplier(
        name="Công ty Thực Phẩm B",
        contact_email=None,
        contact_phone=None,
        status=SupplierStatus.INACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    list_res = await admin_client.get("/api/v1/suppliers?page=1&page_size=10")
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Công ty Nước Giải Khát A"
    assert body["items"][0]["created_at"].endswith("Z")

    active_res = await admin_client.get("/api/v1/suppliers?status=ACTIVE")
    assert active_res.status_code == 200
    assert active_res.json()["total"] == 1
    assert active_res.json()["items"][0]["id"] == s1.id

    search_res = await admin_client.get("/api/v1/suppliers?search=Thực Phẩm")
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["id"] == s2.id

    detail_res = await admin_client.get(f"/api/v1/suppliers/{s1.id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["name"] == "Công ty Nước Giải Khát A"
    assert detail_res.json()["contact_email"] == "a@example.com"


@pytest.mark.anyio
async def test_staff_forbidden_on_all_supplier_endpoints_403(
    staff_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    """2. Staff receives 403 FORBIDDEN on GET list/detail, POST, PATCH, and status."""
    now = datetime.now(UTC).replace(tzinfo=None)
    sup = Supplier(
        name="NCC Nội Bộ",
        contact_email="internal@example.com",
        contact_phone="0902222222",
        status=SupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db_session.add(sup)
    db_session.commit()

    res_list = await staff_client.get("/api/v1/suppliers")
    assert res_list.status_code == 403
    assert res_list.json()["code"] == "FORBIDDEN"

    res_detail = await staff_client.get(f"/api/v1/suppliers/{sup.id}")
    assert res_detail.status_code == 403
    assert res_detail.json()["code"] == "FORBIDDEN"

    res_post = await staff_client.post(
        "/api/v1/suppliers", json={"name": "Staff Tạo NCC"}
    )
    assert res_post.status_code == 403
    assert res_post.json()["code"] == "FORBIDDEN"

    res_patch = await staff_client.patch(
        f"/api/v1/suppliers/{sup.id}", json={"name": "Staff Sửa NCC"}
    )
    assert res_patch.status_code == 403
    assert res_patch.json()["code"] == "FORBIDDEN"

    res_status = await staff_client.patch(
        f"/api/v1/suppliers/{sup.id}/status", json={"status": "INACTIVE"}
    )
    assert res_status.status_code == 403
    assert res_status.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_anonymous_and_invalid_token_supplier_requests_return_401(
    unauth_client: httpx.AsyncClient,
) -> None:
    """3. Anonymous or invalid token requests return 401 on all supplier endpoints."""
    for method, path, payload in [
        ("GET", "/api/v1/suppliers", None),
        ("GET", "/api/v1/suppliers/1", None),
        ("POST", "/api/v1/suppliers", {"name": "NCC Ẩn Danh"}),
        ("PATCH", "/api/v1/suppliers/1", {"name": "Đổi Tên"}),
        ("PATCH", "/api/v1/suppliers/1/status", {"status": "INACTIVE"}),
    ]:
        res = await unauth_client.request(method, path, json=payload)
        assert res.status_code == 401
        assert res.json()["code"] == "UNAUTHENTICATED"

    bad_token_res = await unauth_client.get(
        "/api/v1/suppliers",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert bad_token_res.status_code == 401
    assert bad_token_res.json()["code"] == "SESSION_INVALID"


@pytest.mark.anyio
async def test_admin_create_supplier_returns_201_and_allows_duplicate_names(
    admin_client: httpx.AsyncClient,
) -> None:
    """4. Admin create Supplier returns 201 and allows duplicate names per ERD."""
    res1 = await admin_client.post(
        "/api/v1/suppliers",
        json={
            "name": "  Công ty TNHH Thực Phẩm Xanh  ",
            "contact_email": "contact@greenfood.example.com",
            "contact_phone": "  0912345678  ",
        },
    )
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["name"] == "Công ty TNHH Thực Phẩm Xanh"
    assert data1["contact_email"] == "contact@greenfood.example.com"
    assert data1["contact_phone"] == "0912345678"
    assert data1["status"] == "ACTIVE"
    assert data1["created_at"].endswith("Z")
    assert data1["updated_at"].endswith("Z")

    # Duplicate name allowed per ERD (no UNIQUE constraint on suppliers.name)
    res2 = await admin_client.post(
        "/api/v1/suppliers",
        json={"name": "Công ty TNHH Thực Phẩm Xanh"},
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["id"] != data1["id"]
    assert data2["name"] == "Công ty TNHH Thực Phẩm Xanh"
    assert data2["contact_email"] is None
    assert data2["contact_phone"] is None


@pytest.mark.anyio
async def test_admin_update_supplier_and_persist_null_or_omitted_fields(
    admin_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    """5, 6, 7. Admin PATCH updates fields, null clears contacts, omitted preserved."""
    create_res = await admin_client.post(
        "/api/v1/suppliers",
        json={
            "name": "NCC Ban Đầu",
            "contact_email": "initial@example.com",
            "contact_phone": "0909999999",
        },
    )
    assert create_res.status_code == 201
    sup_id = create_res.json()["id"]

    # 7. Omitted contact_email & contact_phone are preserved when only updating name
    patch_name_only = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}",
        json={"name": "  NCC Đã Đổi Tên  "},
    )
    assert patch_name_only.status_code == 200
    assert patch_name_only.json()["name"] == "NCC Đã Đổi Tên"
    assert patch_name_only.json()["contact_email"] == "initial@example.com"
    assert patch_name_only.json()["contact_phone"] == "0909999999"

    # Omitted name and contact_phone are preserved when updating only contact_email
    patch_email_only = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}",
        json={"contact_email": "updated@example.com"},
    )
    assert patch_email_only.status_code == 200
    assert patch_email_only.json()["name"] == "NCC Đã Đổi Tên"
    assert patch_email_only.json()["contact_email"] == "updated@example.com"
    assert patch_email_only.json()["contact_phone"] == "0909999999"

    # 6. Explicit null for contact_email & contact_phone clears and persists in DB
    patch_clear_contacts = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}",
        json={"contact_email": None, "contact_phone": None},
    )
    assert patch_clear_contacts.status_code == 200
    cleared_body = patch_clear_contacts.json()
    assert cleared_body["name"] == "NCC Đã Đổi Tên"
    assert cleared_body["contact_email"] is None
    assert cleared_body["contact_phone"] is None

    db_session.expire_all()
    persisted = db_session.scalar(select(Supplier).where(Supplier.id == sup_id))
    assert persisted is not None
    assert persisted.name == "NCC Đã Đổi Tên"
    assert persisted.contact_email is None
    assert persisted.contact_phone is None


@pytest.mark.anyio
async def test_supplier_invalid_payloads_return_422(
    admin_client: httpx.AsyncClient,
) -> None:
    """8. Invalid supplier payloads and query params return 422 VALIDATION_ERROR."""
    create_res = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Hợp Lệ"}
    )
    sup_id = create_res.json()["id"]

    invalid_create_payloads = [
        {"name": "   "},  # blank name
        {"name": "A" * 161},  # name > 160 chars
        {"name": "Valid", "contact_email": "not-an-email"},  # invalid email
        {"name": "Valid", "contact_phone": "1" * 33},  # phone > 32 chars
        {"name": "Valid", "extra_field": "forbidden"},  # extra="forbid"
    ]
    for payload in invalid_create_payloads:
        res = await admin_client.post("/api/v1/suppliers", json=payload)
        assert res.status_code == 422
        assert res.json()["code"] == "VALIDATION_ERROR"

    invalid_patch_payloads = [
        {"name": None},  # explicit null name forbidden
        {"name": "   "},  # blank name
        {"name": "B" * 161},  # name > 160 chars
        {"contact_email": "bad-email"},  # invalid email
        {"contact_phone": "9" * 33},  # phone > 32 chars
        {"unknown": "field"},  # extra="forbid"
    ]
    for payload in invalid_patch_payloads:
        res = await admin_client.patch(f"/api/v1/suppliers/{sup_id}", json=payload)
        assert res.status_code == 422
        assert res.json()["code"] == "VALIDATION_ERROR"

    bad_status = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}/status", json={"status": "DELETED"}
    )
    assert bad_status.status_code == 422
    assert bad_status.json()["code"] == "VALIDATION_ERROR"

    bad_page_size = await admin_client.get("/api/v1/suppliers?page_size=101")
    assert bad_page_size.status_code == 422


@pytest.mark.anyio
async def test_missing_supplier_returns_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """9. Missing supplier returns 404 RESOURCE_NOT_FOUND on GET, PATCH, and status."""
    res_get = await admin_client.get("/api/v1/suppliers/999999")
    assert res_get.status_code == 404
    assert res_get.json()["code"] == "RESOURCE_NOT_FOUND"

    res_patch = await admin_client.patch(
        "/api/v1/suppliers/999999", json={"name": "Không Tồn Tại"}
    )
    assert res_patch.status_code == 404
    assert res_patch.json()["code"] == "RESOURCE_NOT_FOUND"

    res_status = await admin_client.patch(
        "/api/v1/suppliers/999999/status", json={"status": "INACTIVE"}
    )
    assert res_status.status_code == 404
    assert res_status.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
async def test_supplier_status_update_persists_without_deleting_record(
    admin_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    """10. Status update transitions ACTIVE/INACTIVE without deleting the record."""
    create_res = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Trạng Thái"}
    )
    sup_id = create_res.json()["id"]

    deact_res = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}/status", json={"status": "INACTIVE"}
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["status"] == "INACTIVE"

    db_session.expire_all()
    persisted = db_session.get(Supplier, sup_id)
    assert persisted is not None
    assert persisted.status == SupplierStatus.INACTIVE

    react_res = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}/status", json={"status": "ACTIVE"}
    )
    assert react_res.status_code == 200
    assert react_res.json()["status"] == "ACTIVE"

    delete_res = await admin_client.delete(f"/api/v1/suppliers/{sup_id}")
    assert delete_res.status_code == 405


def test_service_transaction_rollback_and_repository_no_commit(
    db_session: Session,
) -> None:
    """Verify repository add only flushes and service rolls back on failure."""
    from app.modules.categories.models import Category, CategoryStatus
    from app.modules.categories.repository import CategoryRepository
    from app.modules.categories.schemas import CategoryCreate
    from app.modules.categories.service import CategoryService
    from app.modules.suppliers.repository import SupplierRepository
    from app.modules.suppliers.schemas import SupplierCreate
    from app.modules.suppliers.service import SupplierService

    Category.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    now = datetime.now(UTC).replace(tzinfo=None)

    # 1. Repository add() flushes ID but does NOT commit
    sup_repo = SupplierRepository()
    uncommitted = Supplier(
        name="Uncommitted Supplier",
        status=SupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    sup_repo.add(db_session, uncommitted)
    assert uncommitted.id is not None
    db_session.rollback()
    assert db_session.get(Supplier, uncommitted.id) is None

    # 2. SupplierService and CategoryService rollback session on error
    class FailingSupplierRepo(SupplierRepository):
        def add(self, session: Session, supplier: Supplier) -> Supplier:
            super().add(session, supplier)
            raise RuntimeError("simulated DB failure after flush")

    class FailingCategoryRepo(CategoryRepository):
        def add(self, session: Session, category: Category) -> Category:
            super().add(session, category)
            raise RuntimeError("simulated DB failure after flush")

    sup_service = SupplierService(repository=FailingSupplierRepo())
    with pytest.raises(RuntimeError, match="simulated DB failure after flush"):
        sup_service.create_supplier(
            db_session, SupplierCreate(name="Should Rollback Supplier")
        )
    assert (
        db_session.scalar(
            select(Supplier).where(Supplier.name == "Should Rollback Supplier")
        )
        is None
    )

    cat_service = CategoryService(repository=FailingCategoryRepo())
    with pytest.raises(RuntimeError, match="simulated DB failure after flush"):
        cat_service.create_category(
            db_session, CategoryCreate(name="Should Rollback Category")
        )
    assert (
        db_session.scalar(
            select(Category).where(Category.name == "Should Rollback Category")
        )
        is None
    )
    assert CategoryStatus.ACTIVE == "ACTIVE"
