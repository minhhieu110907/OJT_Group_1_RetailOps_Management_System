"""Unit & HTTP API tests for Bonus T3C9EFC — CSV Product Import."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import BigInteger, create_engine, event, func, select, text
from sqlalchemy.dialects.mysql import DATETIME, TINYINT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.infrastructure.rate_limit import (
    RateLimitResult,
    RedisFixedWindowRateLimiter,
)
from app.main import create_app
from app.modules.auth.models import AuthSession, User, UserRole, UserStatus
from app.modules.auth.security import JwtService
from app.modules.categories.models import Category, CategoryStatus
from app.modules.products.models import Inventory, Product


@compiles(TINYINT, "sqlite")
def _compile_tinyint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(DATETIME, "sqlite")
def _compile_datetime_sqlite(_element, _compiler, **_kw):
    return "DATETIME"


class _AllowAllRateLimiter(RedisFixedWindowRateLimiter):
    def __init__(self) -> None:
        pass

    async def check(self, **_kwargs: Any) -> RateLimitResult:
        return RateLimitResult(allowed=True, count=1, retry_after=0)


def _build_sqlite_app():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_collation(dbapi_conn, _conn_record):
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))
        dbapi_conn.create_function("CHAR_LENGTH", 1, len)

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Product.__table__,
            Inventory.__table__,
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE auth_sessions ("
                "id BLOB PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "expires_at DATETIME NOT NULL, "
                "revoked_at DATETIME)"
            )
        )

    sf = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    with sf() as session, session.begin():
        admin = User(
            email_normalized="csv-admin@retailops.local",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        staff = User(
            email_normalized="csv-staff@retailops.local",
            password_hash="hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add_all([admin, staff])
        session.flush()

        admin_sess = uuid4().bytes
        staff_sess = uuid4().bytes
        session.add_all(
            [
                AuthSession(
                    id=admin_sess,
                    user_id=admin.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=4),
                    revoked_at=None,
                ),
                AuthSession(
                    id=staff_sess,
                    user_id=staff.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=4),
                    revoked_at=None,
                ),
            ]
        )

        cat_active = Category(
            name="Đồ uống",
            status=CategoryStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        cat_inactive = Category(
            name="Ngừng kinh doanh",
            status=CategoryStatus.INACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        cat_dup1 = Category(
            name="Trùng tên",
            status=CategoryStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        cat_dup2 = Category(
            name="Trùng tên",
            status=CategoryStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        session.add_all([cat_active, cat_inactive, cat_dup1, cat_dup2])
        session.flush()

        existing_prod = Product(
            category_id=cat_active.id,
            sku="SKU-EXIST-001",
            name="Existing Tea",
            status="ACTIVE",
            sale_price_vnd=20000,
            created_at=now,
            updated_at=now,
        )
        session.add(existing_prod)
        session.flush()
        session.add(
            Inventory(
                product_id=existing_prod.id,
                quantity=0,
                stock_version=0,
                first_stocked_at=None,
                updated_at=now,
            )
        )

        ids = {
            "admin_id": admin.id,
            "staff_id": staff.id,
            "admin_sess": admin_sess,
            "staff_sess": staff_sess,
            "cat_active_id": cat_active.id,
            "cat_inactive_id": cat_inactive.id,
        }

    settings = Settings(
        _env_file=None,
        environment="development",
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("t3c9efc-jwt-secret-0123456789abcdef"),
        csrf_secret=SecretStr("c" * 32),
        idempotency_secret=SecretStr("i" * 32),
    )
    jwt_svc = JwtService(settings)
    now_utc = datetime.now(UTC)
    admin_tok, _ = jwt_svc.issue(
        user_id=ids["admin_id"],
        session_id=UUID(bytes=ids["admin_sess"]),
        session_expires_at=now_utc + timedelta(hours=2),
        now=now_utc,
    )
    staff_tok, _ = jwt_svc.issue(
        user_id=ids["staff_id"],
        session_id=UUID(bytes=ids["staff_sess"]),
        session_expires_at=now_utc + timedelta(hours=2),
        now=now_utc,
    )

    app = create_app(settings)
    app.state.rate_limiter = _AllowAllRateLimiter()

    def _override_db():
        with sf() as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = _override_db
    return (
        app,
        sf,
        {"Authorization": f"Bearer {admin_tok}"},
        {"Authorization": f"Bearer {staff_tok}"},
        ids,
    )


@pytest.mark.anyio
async def test_csv_import_valid_multipart_utf8_bom_creates_zero_stock() -> None:
    app, sf, admin_h, _staff_h, ids = _build_sqlite_app()
    csv_body = (
        "\ufeffsku,name,category,price\r\n"
        "SKU-IMP-001,Cà phê sữa đá,Đồ uống,29000\r\n"
        f"SKU-IMP-002,Trà đào cam sả,{ids['cat_active_id']},35000\r\n"
    ).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={"file": ("products.csv", csv_body, "text/csv")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total_rows": 2,
        "imported_count": 2,
        "skipped_count": 0,
        "error_count": 0,
        "errors": [],
    }

    with sf() as session:
        p1 = session.scalar(select(Product).where(Product.sku == "SKU-IMP-001"))
        p2 = session.scalar(select(Product).where(Product.sku == "SKU-IMP-002"))
        assert p1 is not None and p1.sale_price_vnd == 29000
        assert p2 is not None and p2.sale_price_vnd == 35000
        inv1 = session.get(Inventory, p1.id)
        inv2 = session.get(Inventory, p2.id)
        assert inv1 is not None and inv1.quantity == 0 and inv1.stock_version == 0
        assert inv2 is not None and inv2.quantity == 0 and inv2.stock_version == 0


@pytest.mark.anyio
async def test_csv_import_partial_success_reports_errors_without_rollback() -> None:
    app, sf, admin_h, _staff_h, _ids = _build_sqlite_app()
    csv_text = (
        "sku,name,category,price\n"
        "SKU-OK-1,Sản phẩm hợp lệ 1,Đồ uống,15000\n"
        "SKU-OK-1,Trùng SKU trong file,Đồ uống,15000\n"
        "SKU-EXIST-001,Trùng SKU trong DB,Đồ uống,15000\n"
        "SKU-BAD-PRICE,Giá âm,Đồ uống,-500\n"
        "SKU-ZERO-PRICE,Giá bằng 0,Đồ uống,0\n"
        "SKU-FLOAT-PRICE,Giá thập phân,Đồ uống,12000.5\n"
        "SKU-NO-CAT,Thiếu danh mục,Không tồn tại,15000\n"
        "SKU-INACT-CAT,Danh mục ngừng hoạt động,Ngừng kinh doanh,15000\n"
        "SKU-DUP-CAT,Danh mục trùng tên,Trùng tên,15000\n"
        "SKU BAD SPACE,SKU có khoảng trắng,Đồ uống,15000\n"
        ",Thiếu SKU,Đồ uống,15000\n"
        "SKU-NO-NAME,,Đồ uống,15000\n"
        "SKU-BAD-COLS,Chỉ có 3 cột,Đồ uống\n"
        "SKU-OK-2,Sản phẩm hợp lệ 2,Đồ uống,42000\n"
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/products/import/csv",
            headers={**admin_h, "Content-Type": "text/csv; charset=utf-8"},
            content=csv_text.encode("utf-8"),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_rows"] == 14
    assert body["imported_count"] == 2
    assert body["skipped_count"] == 12
    assert body["error_count"] == 12
    assert [e["row_number"] for e in body["errors"]] == list(range(3, 15))

    with sf() as session:
        assert session.scalar(select(Product).where(Product.sku == "SKU-OK-1"))
        assert session.scalar(select(Product).where(Product.sku == "SKU-OK-2"))
        # Existing product remains untouched + only 2 new products added
        assert session.scalar(select(func.count(Product.id))) == 3


@pytest.mark.anyio
async def test_csv_import_rbac_rejects_unauthenticated_and_staff() -> None:
    app, sf, _admin_h, staff_h, _ids = _build_sqlite_app()
    csv_bytes = b"sku,name,category,price\nSKU-RBAC,Test,1,10000\n"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_no_auth = await client.post(
            "/api/v1/products/import/csv",
            headers={"Content-Type": "text/csv"},
            content=csv_bytes,
        )
        r_staff = await client.post(
            "/api/v1/products/import/csv",
            headers={**staff_h, "Content-Type": "text/csv"},
            content=csv_bytes,
        )

    assert r_no_auth.status_code == 401
    assert r_staff.status_code == 403
    with sf() as session:
        assert session.scalar(select(Product).where(Product.sku == "SKU-RBAC")) is None


@pytest.mark.anyio
async def test_csv_import_file_level_422_and_header_only_zero_rows() -> None:
    app, sf, admin_h, _staff_h, _ids = _build_sqlite_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Empty file -> 422
        r_empty = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert r_empty.status_code == 422

        # 2. Missing required header -> 422
        r_missing_hdr = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={"file": ("bad.csv", b"sku,name\nA,B\n", "text/csv")},
        )
        assert r_missing_hdr.status_code == 422

        # 3. Non-.csv extension -> 422
        r_wrong_ext = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={"file": ("products.xlsx", b"sku,name,category,price\n", "text/csv")},
        )
        assert r_wrong_ext.status_code == 422

        # 4. Binary / null bytes disguised as .csv -> 422
        r_binary = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={"file": ("fake.csv", b"\x89PNG\r\n\x1a\n\x00\x00", "text/csv")},
        )
        assert r_binary.status_code == 422

        # 5. Unsupported raw content-type -> 422
        r_json_ct = await client.post(
            "/api/v1/products/import/csv",
            headers={**admin_h, "Content-Type": "application/json"},
            content=b'{"sku":"A"}',
        )
        assert r_json_ct.status_code == 422

        # 6. Header-only CSV (0 data rows) -> 200 with total_rows=0
        r_hdr_only = await client.post(
            "/api/v1/products/import/csv",
            headers=admin_h,
            files={
                "file": ("header_only.csv", b"sku,name,category,price\n", "text/csv")
            },
        )
        assert r_hdr_only.status_code == 200
        assert r_hdr_only.json() == {
            "total_rows": 0,
            "imported_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "errors": [],
        }

    with sf() as session:
        assert session.scalar(select(func.count(Product.id))) == 1
