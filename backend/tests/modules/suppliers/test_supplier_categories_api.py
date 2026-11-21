"""API and service tests for the optional supplier <-> category link."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy import BigInteger, create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.modules.categories.models import Category, CategoryStatus
from app.modules.suppliers.models import Supplier, SupplierCategory, SupplierStatus


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
def db_engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = (Category.__table__, Supplier.__table__, SupplierCategory.__table__)
    for table in tables:
        table.create(bind=engine, checkfirst=True)
    yield engine
    for table in reversed(tables):
        table.drop(bind=engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    session = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=db_engine
    )()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_context(mock_settings: Settings) -> tuple[AuthService, dict[str, str]]:
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
    admin_session_id = uuid4()
    live_principals = {(admin_session_id.bytes, admin.id): admin}

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
    return auth_service, {"admin": admin_jwt}


@pytest.fixture
def app_instance(
    mock_settings: Settings,
    db_session: Session,
    auth_context: tuple[AuthService, dict[str, str]],
):
    app = create_app(mock_settings)
    auth_service, _ = auth_context

    class UnavailableRedis:
        async def eval(self, *_args, **_kwargs):
            raise RedisError("test Redis outage")

    app.state.rate_limiter = RedisFixedWindowRateLimiter(  # type: ignore[arg-type]
        UnavailableRedis(), "retailops:test"
    )

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


def _seed_categories(
    db_session: Session, *, count: int = 3, inactive: tuple[int, ...] = ()
) -> list[int]:
    """Insert categories with ids 1..count; ids in ``inactive`` are INACTIVE."""
    now = datetime.now(UTC).replace(tzinfo=None)
    for index in range(1, count + 1):
        db_session.add(
            Category(
                id=index,
                name=f"Danh mục {index}",
                status=(
                    CategoryStatus.INACTIVE.value
                    if index in inactive
                    else CategoryStatus.ACTIVE.value
                ),
                created_at=now,
                updated_at=now,
            )
        )
    db_session.commit()
    return list(range(1, count + 1))


def _stored_links(db_session: Session, supplier_id: int) -> list[int]:
    db_session.expire_all()
    return sorted(
        db_session.scalars(
            select(SupplierCategory.category_id).where(
                SupplierCategory.supplier_id == supplier_id
            )
        ).all()
    )


@pytest.mark.anyio
async def test_create_supplier_without_category_ids_is_backward_compatible(
    admin_client: httpx.AsyncClient,
) -> None:
    res = await admin_client.post("/api/v1/suppliers", json={"name": "NCC Cũ"})
    assert res.status_code == 201
    assert res.json()["category_ids"] == []

    detail = await admin_client.get(f"/api/v1/suppliers/{res.json()['id']}")
    assert detail.json()["category_ids"] == []

    listing = await admin_client.get("/api/v1/suppliers")
    assert listing.json()["items"][0]["category_ids"] == []


@pytest.mark.anyio
async def test_create_supplier_with_categories_and_read_back(
    admin_client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_categories(db_session)

    res = await admin_client.post(
        "/api/v1/suppliers",
        json={"name": "NCC Hai Danh Mục", "category_ids": [2, 1, 2]},
    )
    assert res.status_code == 201
    body = res.json()
    # Duplicates removed, output sorted ascending (stable).
    assert body["category_ids"] == [1, 2]

    detail = await admin_client.get(f"/api/v1/suppliers/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["category_ids"] == [1, 2]

    listing = await admin_client.get("/api/v1/suppliers")
    assert listing.json()["items"][0]["category_ids"] == [1, 2]
    assert _stored_links(db_session, body["id"]) == [1, 2]


@pytest.mark.anyio
async def test_patch_category_ids_keep_replace_and_clear(
    admin_client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_categories(db_session)
    created = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Sửa", "category_ids": [1, 2]}
    )
    sup_id = created.json()["id"]
    url = f"/api/v1/suppliers/{sup_id}"

    # Omitted -> unchanged, even when other fields are patched.
    keep = await admin_client.patch(url, json={"name": "NCC Sửa Tên"})
    assert keep.status_code == 200
    assert keep.json()["category_ids"] == [1, 2]

    # Empty PATCH body and explicit null both keep the current links.
    assert (await admin_client.patch(url, json={})).json()["category_ids"] == [1, 2]
    null_res = await admin_client.patch(url, json={"category_ids": None})
    assert null_res.status_code == 200
    assert null_res.json()["category_ids"] == [1, 2]

    # List replaces the links.
    replace = await admin_client.patch(url, json={"category_ids": [2, 3]})
    assert replace.status_code == 200
    assert replace.json()["category_ids"] == [2, 3]
    assert (await admin_client.get(url)).json()["category_ids"] == [2, 3]
    assert _stored_links(db_session, sup_id) == [2, 3]

    # [] clears every link.
    clear = await admin_client.patch(url, json={"category_ids": []})
    assert clear.status_code == 200
    assert clear.json()["category_ids"] == []
    assert _stored_links(db_session, sup_id) == []


@pytest.mark.anyio
async def test_unknown_category_id_fails_closed_without_side_effects(
    admin_client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_categories(db_session, count=2)

    res = await admin_client.post(
        "/api/v1/suppliers",
        json={"name": "NCC Không Được Tạo", "category_ids": [1, 999]},
    )
    assert res.status_code == 404
    assert res.json()["code"] == "RESOURCE_NOT_FOUND"
    assert res.json()["details"] == {"missing_category_ids": [999]}
    assert db_session.scalar(select(Supplier.id)) is None

    created = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Hợp Lệ", "category_ids": [1]}
    )
    sup_id = created.json()["id"]
    patch = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}",
        json={"name": "Tên Mới", "category_ids": [2, 999]},
    )
    assert patch.status_code == 404
    assert patch.json()["code"] == "RESOURCE_NOT_FOUND"

    # Nothing was applied: neither the links nor the name.
    assert _stored_links(db_session, sup_id) == [1]
    assert db_session.get(Supplier, sup_id).name == "NCC Hợp Lệ"


@pytest.mark.anyio
async def test_inactive_category_rules_block_new_links_but_keep_existing(
    admin_client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_categories(db_session, count=3, inactive=(3,))

    blocked = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Inactive", "category_ids": [1, 3]}
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "VALIDATION_ERROR"
    assert blocked.json()["details"] == {"inactive_category_ids": [3]}
    assert db_session.scalar(select(Supplier.id)) is None

    created = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Active", "category_ids": [1, 2]}
    )
    sup_id = created.json()["id"]
    url = f"/api/v1/suppliers/{sup_id}"

    assert (
        await admin_client.patch(url, json={"category_ids": [1, 2, 3]})
    ).status_code == 422
    assert _stored_links(db_session, sup_id) == [1, 2]

    # Deactivate an already-linked category: the existing link is grandfathered.
    category = db_session.get(Category, 2)
    category.status = CategoryStatus.INACTIVE.value
    db_session.commit()

    same_list = await admin_client.patch(url, json={"category_ids": [1, 2]})
    assert same_list.status_code == 200
    assert same_list.json()["category_ids"] == [1, 2]

    # Dropping the inactive link is always allowed.
    dropped = await admin_client.patch(url, json={"category_ids": [1]})
    assert dropped.status_code == 200
    assert dropped.json()["category_ids"] == [1]
    # ...but it can no longer be newly re-added.
    assert (
        await admin_client.patch(url, json={"category_ids": [1, 2]})
    ).status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad_value",
    [[0], [-1], ["1"], [True], [1.5], [None], "1", 1, list(range(1, 102))],
)
async def test_invalid_category_ids_payload_returns_422(
    admin_client: httpx.AsyncClient, db_session: Session, bad_value: object
) -> None:
    _seed_categories(db_session, count=1)
    created = await admin_client.post("/api/v1/suppliers", json={"name": "NCC"})
    sup_id = created.json()["id"]

    post = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC X", "category_ids": bad_value}
    )
    assert post.status_code == 422
    assert post.json()["code"] == "VALIDATION_ERROR"

    patch = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}", json={"category_ids": bad_value}
    )
    assert patch.status_code == 422
    assert patch.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_status_change_and_list_filters_still_return_category_ids(
    admin_client: httpx.AsyncClient, db_session: Session
) -> None:
    _seed_categories(db_session)
    created = await admin_client.post(
        "/api/v1/suppliers", json={"name": "NCC Status", "category_ids": [3, 1]}
    )
    sup_id = created.json()["id"]

    status_res = await admin_client.patch(
        f"/api/v1/suppliers/{sup_id}/status", json={"status": "INACTIVE"}
    )
    assert status_res.status_code == 200
    assert status_res.json()["category_ids"] == [1, 3]
    assert status_res.json()["status"] == SupplierStatus.INACTIVE.value

    filtered = await admin_client.get("/api/v1/suppliers?status=INACTIVE")
    assert filtered.json()["items"][0]["category_ids"] == [1, 3]


@pytest.mark.anyio
async def test_list_suppliers_has_no_n_plus_one_for_category_ids(
    admin_client: httpx.AsyncClient, db_session: Session, db_engine: Engine
) -> None:
    _seed_categories(db_session)

    async def create(index: int) -> None:
        res = await admin_client.post(
            "/api/v1/suppliers",
            json={"name": f"NCC {index}", "category_ids": [1 + index % 3, 1]},
        )
        assert res.status_code == 201

    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many) -> None:
        statements.append(statement)

    async def list_and_capture() -> tuple[list[str], dict]:
        statements.clear()
        event.listen(db_engine, "before_cursor_execute", record)
        try:
            res = await admin_client.get("/api/v1/suppliers?page_size=100")
        finally:
            event.remove(db_engine, "before_cursor_execute", record)
        assert res.status_code == 200
        return list(statements), res.json()

    await create(1)
    await create(2)
    small_sql, small_body = await list_and_capture()

    for index in range(3, 13):
        await create(index)
    large_sql, large_body = await list_and_capture()

    assert len(small_body["items"]) == 2
    assert len(large_body["items"]) == 12
    # Query count is independent of the number of suppliers on the page and the
    # category links are fetched with exactly one batched statement.
    assert len(small_sql) == len(large_sql) == 3  # count + page + links
    assert sum("supplier_categories" in sql for sql in large_sql) == 1
    for item in large_body["items"]:
        assert item["category_ids"] == sorted(item["category_ids"])


def test_service_rolls_back_supplier_when_link_insert_fails(
    db_session: Session,
) -> None:
    from app.modules.suppliers.repository import SupplierRepository
    from app.modules.suppliers.schemas import SupplierCreate
    from app.modules.suppliers.service import SupplierService

    _seed_categories(db_session, count=1)

    class FailingLinkRepo(SupplierRepository):
        def replace_category_links(self, session, supplier_id, category_ids) -> None:
            super().replace_category_links(session, supplier_id, category_ids)
            raise RuntimeError("simulated failure after link flush")

    service = SupplierService(repository=FailingLinkRepo())
    with pytest.raises(RuntimeError, match="simulated failure after link flush"):
        service.create_supplier(
            db_session, SupplierCreate(name="Rollback NCC", category_ids=[1])
        )

    assert db_session.scalar(select(Supplier.id)) is None
    assert db_session.scalar(select(SupplierCategory.supplier_id)) is None
