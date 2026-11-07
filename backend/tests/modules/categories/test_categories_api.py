"""Integration tests for Categories API."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category, CategoryStatus


@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-testing-purposes",
        jwt_secret=SecretStr("test-jwt-secret-key-for-testing-purposes-123456"),
        csrf_secret=SecretStr("test-csrf-secret-key-for-testing-purposes-123456"),
        db_host="localhost",
        db_user="retailops",
        db_password="password",
        db_name="retailops_db",
    )


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Category.__table__.create(bind=engine, checkfirst=True)
    yield engine
    Category.__table__.drop(bind=engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
    )
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin_user() -> User:
    return User(
        id=1,
        email_normalized="admin@retailops.test",
        password_hash="mock_hash",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def staff_user() -> User:
    return User(
        id=2,
        email_normalized="staff@retailops.test",
        password_hash="mock_hash",
        role=UserRole.STAFF,
        status=UserStatus.ACTIVE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def app_instance(mock_settings: Settings, db_session: Session):
    app = create_app(mock_settings)

    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = lambda: mock_settings
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(
    app_instance, admin_user: User
) -> AsyncGenerator[httpx.AsyncClient, None]:
    principal = CurrentPrincipal(user=admin_user, session_id=uuid4())
    app_instance.dependency_overrides[get_current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def staff_client(
    app_instance, staff_user: User
) -> AsyncGenerator[httpx.AsyncClient, None]:
    principal = CurrentPrincipal(user=staff_user, session_id=uuid4())
    app_instance.dependency_overrides[get_current_principal] = lambda: principal
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def unauth_client(app_instance) -> AsyncGenerator[httpx.AsyncClient, None]:
    # Đảm bảo không dính override principal khi test unauthenticated
    app_instance.dependency_overrides.pop(get_current_principal, None)
    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --- Helper client creators to avoid fixture override conflicts ---


def make_admin_client(app_instance, admin_user: User) -> httpx.AsyncClient:
    principal = CurrentPrincipal(user=admin_user, session_id=uuid4())
    app_instance.dependency_overrides[get_current_principal] = lambda: principal
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_instance), base_url="http://test"
    )


def make_staff_client(app_instance, staff_user: User) -> httpx.AsyncClient:
    principal = CurrentPrincipal(user=staff_user, session_id=uuid4())
    app_instance.dependency_overrides[get_current_principal] = lambda: principal
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_instance), base_url="http://test"
    )


# --- Test Cases ---


@pytest.mark.anyio
async def test_get_categories_empty_list(staff_client: httpx.AsyncClient) -> None:
    res = await staff_client.get("/api/v1/categories")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.anyio
async def test_get_categories_list_accessible_by_both_staff_and_admin(
    app_instance,
    admin_user: User,
    staff_user: User,
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    cat1 = Category(
        name="Đồ uống", status=CategoryStatus.ACTIVE, created_at=now, updated_at=now
    )
    cat2 = Category(
        name="Gia dụng", status=CategoryStatus.INACTIVE, created_at=now, updated_at=now
    )
    db_session.add_all([cat1, cat2])
    db_session.commit()

    async with make_staff_client(app_instance, staff_user) as staff_c:
        res_staff = await staff_c.get("/api/v1/categories")
        assert res_staff.status_code == 200
        assert res_staff.json()["total"] == 2

    async with make_admin_client(app_instance, admin_user) as admin_c:
        res_admin = await admin_c.get("/api/v1/categories?status=ACTIVE")
        assert res_admin.status_code == 200
        assert res_admin.json()["total"] == 1
        assert res_admin.json()["items"][0]["name"] == "Đồ uống"


@pytest.mark.anyio
async def test_get_category_detail_and_not_found(
    staff_client: httpx.AsyncClient,
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    cat = Category(
        name="Bánh kẹo", status=CategoryStatus.ACTIVE, created_at=now, updated_at=now
    )
    db_session.add(cat)
    db_session.commit()

    res = await staff_client.get(f"/api/v1/categories/{cat.id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Bánh kẹo"

    res_not_found = await staff_client.get("/api/v1/categories/999999")
    assert res_not_found.status_code == 404
    assert res_not_found.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.anyio
async def test_create_category_admin_success(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.post("/api/v1/categories", json={"name": "Thực phẩm sạch"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Thực phẩm sạch"
    assert data["status"] == "ACTIVE"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.anyio
async def test_create_category_staff_forbidden(staff_client: httpx.AsyncClient) -> None:
    res = await staff_client.post("/api/v1/categories", json={"name": "Mỹ phẩm"})
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_create_category_unauth(unauth_client: httpx.AsyncClient) -> None:
    res = await unauth_client.post("/api/v1/categories", json={"name": "Mỹ phẩm"})
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_create_category_validation_error(
    admin_client: httpx.AsyncClient,
) -> None:
    res_empty = await admin_client.post("/api/v1/categories", json={"name": "   "})
    assert res_empty.status_code == 422

    res_long = await admin_client.post("/api/v1/categories", json={"name": "A" * 121})
    assert res_long.status_code == 422


@pytest.mark.anyio
async def test_create_category_duplicate_name_allowed(
    admin_client: httpx.AsyncClient,
) -> None:
    res1 = await admin_client.post("/api/v1/categories", json={"name": "Đồng giá"})
    assert res1.status_code == 201

    res2 = await admin_client.post("/api/v1/categories", json={"name": "Đồng giá"})
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]


@pytest.mark.anyio
async def test_update_category_name_admin(
    app_instance,
    admin_user: User,
    staff_user: User,
) -> None:
    async with make_admin_client(app_instance, admin_user) as admin_c:
        create_res = await admin_c.post("/api/v1/categories", json={"name": "Tên Cũ"})
        assert create_res.status_code == 201
        cat_id = create_res.json()["id"]

    # Staff không có quyền update
    async with make_staff_client(app_instance, staff_user) as staff_c:
        staff_res = await staff_c.patch(
            f"/api/v1/categories/{cat_id}", json={"name": "Tên Mới"}
        )
        assert staff_res.status_code == 403

    # Admin update thành công
    async with make_admin_client(app_instance, admin_user) as admin_c:
        admin_res = await admin_c.patch(
            f"/api/v1/categories/{cat_id}", json={"name": "Tên Mới"}
        )
        assert admin_res.status_code == 200
        assert admin_res.json()["name"] == "Tên Mới"


@pytest.mark.anyio
async def test_update_category_status_admin(
    app_instance,
    admin_user: User,
    staff_user: User,
) -> None:
    async with make_admin_client(app_instance, admin_user) as admin_c:
        create_res = await admin_c.post(
            "/api/v1/categories", json={"name": "Hàng Tươi"}
        )
        assert create_res.status_code == 201
        cat_id = create_res.json()["id"]

        admin_res = await admin_c.patch(
            f"/api/v1/categories/{cat_id}/status", json={"status": "INACTIVE"}
        )
        assert admin_res.status_code == 200
        assert admin_res.json()["status"] == "INACTIVE"

    # Staff không có quyền đổi status
    async with make_staff_client(app_instance, staff_user) as staff_c:
        staff_res = await staff_c.patch(
            f"/api/v1/categories/{cat_id}/status", json={"status": "ACTIVE"}
        )
        assert staff_res.status_code == 403
