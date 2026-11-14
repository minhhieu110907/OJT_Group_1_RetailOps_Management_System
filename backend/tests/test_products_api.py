"""API and service unit tests for Product endpoints, RBAC, and transactions."""

from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DomainValidationError,
    DuplicateSkuError,
    ResourceNotFoundError,
)
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category, CategoryStatus
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.products.repository import InventoryRepository, ProductRepository
from app.modules.products.router import get_product_service
from app.modules.products.schemas import (
    ProductCreateRequest,
    ProductSortOrder,
    ProductStatusUpdateRequest,
    ProductUpdateRequest,
)
from app.modules.products.service import (
    ProductService,
    _is_duplicate_sku_integrity_error,
)

ORIGIN = "http://127.0.0.1:5173"


def test_settings() -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        jwt_secret=SecretStr("j" * 32),
        csrf_secret=SecretStr("c" * 32),
        cors_origins=ORIGIN,
    )


def make_principal(role: UserRole) -> CurrentPrincipal:
    now = datetime(2026, 11, 7, 10, 0)
    user = User(
        id=1 if role == UserRole.ADMIN else 2,
        email_normalized=f"{role.value.lower()}@example.com",
        password_hash="hashed",
        role=role.value,
        status=UserStatus.ACTIVE.value,
        admin_slot=1 if role == UserRole.ADMIN else None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    return CurrentPrincipal(user=user, session_id=uuid4())


class FakeSession:
    """Track flush, commit, and rollback calls for unit transaction verification."""

    def __init__(self) -> None:
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0

    def flush(self) -> None:
        self.flushed += 1

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class InMemoryProductStore:
    """In-memory backing store simulating Category, Product, and Inventory tables."""

    def __init__(self) -> None:
        now = datetime(2026, 11, 7, 9, 0)
        self.categories: dict[int, Category] = {
            1: Category(
                id=1,
                name="Đồ uống",
                status=CategoryStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            ),
            2: Category(
                id=2,
                name="Danh mục ngừng dùng",
                status=CategoryStatus.INACTIVE.value,
                created_at=now,
                updated_at=now,
            ),
        }
        self.products: dict[int, Product] = {}
        self.inventory: dict[int, Inventory] = {}
        self._next_id = 1
        self.fail_inventory_add = False


class FakeProductRepository(ProductRepository):
    def __init__(self, store: InMemoryProductStore) -> None:
        self.store = store
        self.pending_product: Product | None = None

    def get_category(self, _session: object, category_id: int) -> Category | None:
        return self.store.categories.get(category_id)

    def get_by_id(self, _session: object, product_id: int) -> Product | None:
        return self.store.products.get(product_id)

    def get_by_sku(self, _session: object, sku: str) -> Product | None:
        for product in self.store.products.values():
            if product.sku == sku:
                return product
        return None

    def get_with_inventory(
        self, _session: object, product_id: int
    ) -> tuple[Product, Inventory] | None:
        product = self.store.products.get(product_id)
        inv = self.store.inventory.get(product_id)
        if product is None or inv is None:
            return None
        return product, inv

    def list_with_inventory(
        self,
        _session: object,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        category_id: int | None = None,
        status: CatalogStatus | str | None = None,
        sort: ProductSortOrder = ProductSortOrder.CREATED_DESC,
    ) -> tuple[list[tuple[Product, Inventory]], int]:
        records = list(self.store.products.values())
        if category_id is not None:
            records = [p for p in records if p.category_id == category_id]
        if status is not None:
            status_val = status.value if isinstance(status, CatalogStatus) else status
            records = [p for p in records if p.status == status_val]
        if search is not None and search.strip():
            kw = search.strip().lower()
            records = [
                p for p in records if kw in p.name.lower() or kw in p.sku.lower()
            ]

        if sort == ProductSortOrder.QUANTITY_ASC:
            records.sort(
                key=lambda p: (
                    1 if self.store.inventory[p.id].quantity is None else 0,
                    self.store.inventory[p.id].quantity or 0,
                    p.id,
                )
            )
        elif sort == ProductSortOrder.RESTOCK_FIRST:

            def _restock_key(p: Product) -> tuple[int, int, int]:
                qty = self.store.inventory[p.id].quantity
                if qty is None or qty < 0:
                    return (3, 0, p.id)
                if qty == 0:
                    return (0, 0, p.id)
                if qty <= 5:
                    return (1, qty, p.id)
                return (2, qty, p.id)

            records.sort(key=_restock_key)
        elif sort == ProductSortOrder.NAME_ASC:
            records.sort(key=lambda p: (p.name, p.id))
        elif sort == ProductSortOrder.NAME_DESC:
            records.sort(key=lambda p: (p.name, p.id), reverse=True)
        elif sort == ProductSortOrder.SKU_ASC:
            records.sort(key=lambda p: (p.sku, p.id))
        elif sort == ProductSortOrder.SKU_DESC:
            records.sort(key=lambda p: (p.sku, p.id), reverse=True)
        elif sort == ProductSortOrder.CREATED_DESC:
            records.sort(key=lambda p: (p.created_at, p.id), reverse=True)
        else:
            raise DomainValidationError("Tham số sắp xếp không hợp lệ.")

        total = len(records)
        start = (page - 1) * page_size
        end = start + page_size
        items = [(prod, self.store.inventory[prod.id]) for prod in records[start:end]]
        return items, total

    def add(self, _session: object, product: Product) -> Product:
        product.id = self.store._next_id
        self.store._next_id += 1
        self.store.products[product.id] = product
        self.pending_product = product
        return product


class FakeInventoryRepository(InventoryRepository):
    def __init__(
        self, store: InMemoryProductStore, prod_repo: FakeProductRepository
    ) -> None:
        self.store = store
        self.prod_repo = prod_repo

    def add_zero(self, _session: object, product_id: int, now: datetime) -> Inventory:
        if self.store.fail_inventory_add:
            if (
                self.prod_repo.pending_product is not None
                and self.prod_repo.pending_product.id in self.store.products
            ):
                del self.store.products[self.prod_repo.pending_product.id]
            raise RuntimeError("Simulated inventory insertion failure")
        inv = Inventory(
            product_id=product_id,
            quantity=0,
            stock_version=0,
            first_stocked_at=None,
            updated_at=now,
        )
        self.store.inventory[product_id] = inv
        return inv


def build_fake_service() -> tuple[ProductService, InMemoryProductStore, FakeSession]:
    store = InMemoryProductStore()
    prod_repo = FakeProductRepository(store)
    inv_repo = FakeInventoryRepository(store, prod_repo)
    service = ProductService(products=prod_repo, inventory=inv_repo)
    session = FakeSession()
    return service, store, session


def test_service_create_flushes_product_and_commits_inventory_atomically() -> None:
    service, _store, session = build_fake_service()
    created = service.create(
        session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="CF-001",
            name="Cà phê rang xay",
            category_id=1,
            sale_price_vnd=45_000,
        ),
    )
    assert created.id == 1
    assert created.sku == "CF-001"
    assert created.status == CatalogStatus.ACTIVE
    assert created.quantity == 0
    assert created.stock_version == 0
    assert session.flushed == 1
    assert session.committed == 1
    assert session.rolled_back == 0


def test_service_create_rolls_back_when_inventory_creation_fails() -> None:
    service, store, session = build_fake_service()
    store.fail_inventory_add = True
    with pytest.raises(RuntimeError, match="Simulated inventory insertion failure"):
        service.create(
            session,  # type: ignore[arg-type]
            ProductCreateRequest(
                sku="CF-FAIL",
                name="Cà phê lỗi",
                category_id=1,
                sale_price_vnd=45_000,
            ),
        )
    assert session.flushed == 1
    assert session.committed == 0
    assert session.rolled_back == 1
    assert len(store.products) == 0
    assert len(store.inventory) == 0


def test_service_create_and_update_reject_inactive_or_missing_category() -> None:
    service, _store, session = build_fake_service()

    # Missing category -> 404 RESOURCE_NOT_FOUND
    with pytest.raises(ResourceNotFoundError):
        service.create(
            session,  # type: ignore[arg-type]
            ProductCreateRequest(
                sku="CF-404",
                name="Sản phẩm thiếu danh mục",
                category_id=999,
                sale_price_vnd=20_000,
            ),
        )

    # Inactive category -> 422 VALIDATION_ERROR
    with pytest.raises(DomainValidationError) as exc_info:
        service.create(
            session,  # type: ignore[arg-type]
            ProductCreateRequest(
                sku="CF-INACTIVE-CAT",
                name="Sản phẩm gán danh mục ngừng hoạt động",
                category_id=2,
                sale_price_vnd=20_000,
            ),
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"

    # Create valid product then try updating to INACTIVE category -> 422
    created = service.create(
        session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="CF-VALID",
            name="Sản phẩm hợp lệ",
            category_id=1,
            sale_price_vnd=20_000,
        ),
    )
    with pytest.raises(DomainValidationError):
        service.update(
            session,  # type: ignore[arg-type]
            created.id,
            ProductUpdateRequest(category_id=2),
        )


def test_service_rejects_duplicate_sku_on_create_and_update() -> None:
    service, _store, session = build_fake_service()
    first = service.create(
        session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="SKU-A",
            name="Sản phẩm A",
            category_id=1,
            sale_price_vnd=10_000,
        ),
    )
    second = service.create(
        session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="SKU-B",
            name="Sản phẩm B",
            category_id=1,
            sale_price_vnd=15_000,
        ),
    )

    with pytest.raises(DuplicateSkuError):
        service.create(
            session,  # type: ignore[arg-type]
            ProductCreateRequest(
                sku="SKU-A",
                name="Sản phẩm trùng",
                category_id=1,
                sale_price_vnd=20_000,
            ),
        )

    with pytest.raises(DuplicateSkuError):
        service.update(
            session,  # type: ignore[arg-type]
            second.id,
            ProductUpdateRequest(sku=first.sku),
        )


def test_service_status_toggle_preserves_inventory_balance() -> None:
    service, store, session = build_fake_service()
    created = service.create(
        session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="SKU-STATUS",
            name="Sản phẩm đổi trạng thái",
            category_id=1,
            sale_price_vnd=30_000,
        ),
    )
    # Simulate stocked inventory
    store.inventory[created.id].quantity = 25
    store.inventory[created.id].stock_version = 3

    deactivated = service.update_status(
        session,  # type: ignore[arg-type]
        created.id,
        ProductStatusUpdateRequest(status=CatalogStatus.INACTIVE),
    )
    assert deactivated.status == CatalogStatus.INACTIVE
    assert deactivated.quantity == 25
    assert deactivated.stock_version == 3

    reactivated = service.update_status(
        session,  # type: ignore[arg-type]
        created.id,
        ProductStatusUpdateRequest(status=CatalogStatus.ACTIVE),
    )
    assert reactivated.status == CatalogStatus.ACTIVE
    assert reactivated.quantity == 25
    assert reactivated.stock_version == 3


@pytest.mark.anyio
async def test_api_unauthenticated_requests_return_401() -> None:
    settings = test_settings()
    service, _store, fake_session = build_fake_service()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: fake_session
    application.dependency_overrides[get_product_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        for method, path, body in (
            ("GET", "/api/v1/products", None),
            ("GET", "/api/v1/products/1", None),
            (
                "POST",
                "/api/v1/products",
                {
                    "sku": "SKU-1",
                    "name": "SP 1",
                    "category_id": 1,
                    "sale_price_vnd": 10000,
                },
            ),
            ("PATCH", "/api/v1/products/1", {"name": "SP mới"}),
            ("PATCH", "/api/v1/products/1/status", {"status": "INACTIVE"}),
        ):
            response = await client.request(method, path, json=body)
            assert response.status_code == 401
            assert response.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.anyio
async def test_api_staff_can_read_but_gets_403_on_mutations() -> None:
    settings = test_settings()
    service, _store, fake_session = build_fake_service()
    # Seed 1 product as Admin
    created = service.create(
        fake_session,  # type: ignore[arg-type]
        ProductCreateRequest(
            sku="TEA-001",
            name="Trà Ô Long",
            category_id=1,
            sale_price_vnd=18_000,
        ),
    )

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: fake_session
    application.dependency_overrides[get_product_service] = lambda: service
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.STAFF
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        # Staff GET list -> 200 OK, no cost fields leaked
        list_resp = await client.get("/api/v1/products?page=1&page_size=20")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data["total"] == 1
        assert list_data["page"] == 1
        assert list_data["page_size"] == 20
        item = list_data["items"][0]
        assert item["sku"] == "TEA-001"
        assert "unit_cost_vnd" not in item
        assert "cost" not in item

        # Staff GET detail -> 200 OK
        detail_resp = await client.get(f"/api/v1/products/{created.id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == created.id

        # Staff POST -> 403 FORBIDDEN
        post_resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "TEA-002",
                "name": "Trà Đào",
                "category_id": 1,
                "sale_price_vnd": 20_000,
            },
        )
        assert post_resp.status_code == 403
        assert post_resp.json() == {
            "code": "FORBIDDEN",
            "message": "Chỉ quản trị viên mới có quyền thực hiện thao tác.",
            "details": None,
        }

        # Staff PATCH -> 403 FORBIDDEN
        patch_resp = await client.patch(
            f"/api/v1/products/{created.id}",
            json={"name": "Trà Ô Long Đặc Biệt"},
        )
        assert patch_resp.status_code == 403
        assert patch_resp.json()["code"] == "FORBIDDEN"

        # Staff PATCH status -> 403 FORBIDDEN
        status_resp = await client.patch(
            f"/api/v1/products/{created.id}/status",
            json={"status": "INACTIVE"},
        )
        assert status_resp.status_code == 403
        assert status_resp.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_api_admin_crud_and_error_envelopes() -> None:
    settings = test_settings()
    service, _store, fake_session = build_fake_service()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: fake_session
    application.dependency_overrides[get_product_service] = lambda: service
    application.dependency_overrides[get_current_principal] = lambda: make_principal(
        UserRole.ADMIN
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        # 1. Create product -> 201
        create_resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "MILK-001",
                "name": "Sữa tươi tiệt trùng",
                "category_id": 1,
                "sale_price_vnd": 32_000,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["id"] == 1
        assert created["quantity"] == 0
        assert created["stock_version"] == 0

        # 2. Duplicate SKU -> 409 DUPLICATE_SKU
        dup_resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "MILK-001",
                "name": "Sữa khác",
                "category_id": 1,
                "sale_price_vnd": 35_000,
            },
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["code"] == "DUPLICATE_SKU"

        # 3. Category INACTIVE -> 422 VALIDATION_ERROR
        inactive_cat_resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "MILK-002",
                "name": "Sữa danh mục đóng",
                "category_id": 2,
                "sale_price_vnd": 35_000,
            },
        )
        assert inactive_cat_resp.status_code == 422
        assert inactive_cat_resp.json()["code"] == "VALIDATION_ERROR"

        # 4. Category missing -> 404 RESOURCE_NOT_FOUND
        missing_cat_resp = await client.post(
            "/api/v1/products",
            json={
                "sku": "MILK-003",
                "name": "Sữa danh mục không tồn tại",
                "category_id": 999,
                "sale_price_vnd": 35_000,
            },
        )
        assert missing_cat_resp.status_code == 404
        assert missing_cat_resp.json()["code"] == "RESOURCE_NOT_FOUND"

        # 5. PATCH forbids quantity / stock_version -> 422 VALIDATION_ERROR
        forbid_qty_resp = await client.patch(
            "/api/v1/products/1",
            json={"quantity": 100},
        )
        assert forbid_qty_resp.status_code == 422
        assert forbid_qty_resp.json()["code"] == "VALIDATION_ERROR"

        # 6. PATCH valid fields -> 200 OK
        patch_resp = await client.patch(
            "/api/v1/products/1",
            json={"name": "Sữa tươi ít đường", "sale_price_vnd": 34_000},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Sữa tươi ít đường"
        assert patch_resp.json()["sale_price_vnd"] == 34_000

        # 7. PATCH status -> 200 OK
        status_resp = await client.patch(
            "/api/v1/products/1/status",
            json={"status": "INACTIVE"},
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "INACTIVE"

        # 8. Pagination bounds (>100 -> 422)
        bad_page_resp = await client.get("/api/v1/products?page=1&page_size=101")
        assert bad_page_resp.status_code == 422
        assert bad_page_resp.json()["code"] == "VALIDATION_ERROR"

        # 9. Missing product -> 404
        missing_prod_resp = await client.get("/api/v1/products/999")
        assert missing_prod_resp.status_code == 404
        assert missing_prod_resp.json()["code"] == "RESOURCE_NOT_FOUND"


def test_duplicate_sku_integrity_error_classifier_requires_1062_and_sku_key() -> None:
    from sqlalchemy.exc import IntegrityError

    class FakeMySQLError(Exception):
        pass

    dup_sku_err = IntegrityError(
        "INSERT INTO products ...",
        {},
        FakeMySQLError(
            1062,
            "Duplicate entry 'CF-01' for key 'products.uq_products_sku'",
        ),
    )
    assert _is_duplicate_sku_integrity_error(dup_sku_err) is True

    # Non-1062 error (e.g. 1452 FK constraint on category_id) must NOT match
    fk_err = IntegrityError(
        "INSERT INTO products ...",
        {},
        FakeMySQLError(
            1452,
            "Cannot add or update a child row: a foreign key constraint fails "
            "(`retailops`.`products`, CONSTRAINT `fk_products_category_id_categories`)",
        ),
    )
    assert _is_duplicate_sku_integrity_error(fk_err) is False

    # 1062 on another unique constraint (e.g. inventory PK) must NOT match
    other_1062_err = IntegrityError(
        "INSERT INTO inventory ...",
        {},
        FakeMySQLError(1062, "Duplicate entry '1' for key 'inventory.PRIMARY'"),
    )
    assert _is_duplicate_sku_integrity_error(other_1062_err) is False


@pytest.mark.anyio
async def test_api_non_active_or_revoked_user_is_rejected_with_401() -> None:
    from app.core.exceptions import SessionInvalidError
    from app.modules.auth.dependencies import get_auth_service

    class RevokedAuthService:
        def live_user(self, _session: object, _token: str) -> tuple[User, object]:
            raise SessionInvalidError()

    settings = test_settings()
    service, _store, fake_session = build_fake_service()
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: fake_session
    application.dependency_overrides[get_product_service] = lambda: service
    application.dependency_overrides[get_auth_service] = RevokedAuthService

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/products",
            headers={"Authorization": "Bearer revoked-or-inactive-user-token"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "SESSION_INVALID"

    # Also verify get_current_active_user blocks a non-ACTIVE principal with 403
    now = datetime(2026, 11, 7, 10, 0)
    pending_user = User(
        id=99,
        email_normalized="pending@example.com",
        password_hash="hashed",
        role=UserRole.STAFF.value,
        status=UserStatus.PENDING_APPROVAL.value,
        admin_slot=None,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    application.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        user=pending_user, session_id=uuid4()
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        pending_resp = await client.get("/api/v1/products")
        assert pending_resp.status_code == 403
        assert pending_resp.json()["code"] == "FORBIDDEN"


def _build_sqlite_product_session() -> tuple[object, list[str]]:
    """Build an in-memory SQLite session with ascii_bin, Unicode lower, and SQL log."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    executed_sql: list[str] = []

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_conn: object, _record: object) -> None:
        conn = dbapi_conn  # type: ignore[assignment]
        conn.create_collation(  # type: ignore[attr-defined]
            "ascii_bin", lambda a, b: (a > b) - (a < b)
        )
        conn.create_function(  # type: ignore[attr-defined]
            "lower", 1, lambda s: s.lower() if isinstance(s, str) else s
        )

    @event.listens_for(engine, "before_cursor_execute")
    def _record_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        executed_sql.append(statement)

    Category.__table__.create(engine)
    Product.__table__.create(engine)
    Inventory.__table__.create(engine)

    session = Session(engine)
    now = datetime(2026, 11, 8, 8, 0, 0)
    cat_drink = Category(
        id=1,
        name="Đồ uống",
        status=CategoryStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    cat_snack = Category(
        id=2,
        name="Bánh kẹo",
        status=CategoryStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add_all([cat_drink, cat_snack])

    # Seed 6 products with distinct SKUs, names, categories, statuses, and timestamps
    # P1 and P2 share the exact same name ("Cà phê rang xay") to test id tie-breaker
    # P3 and P4 share the exact same created_at to test created_desc tie-breaker by id
    t1 = datetime(2026, 11, 8, 9, 0, 0)
    t2 = datetime(2026, 11, 8, 9, 5, 0)
    t3 = datetime(2026, 11, 8, 9, 10, 0)
    t4 = datetime(2026, 11, 8, 9, 15, 0)
    t5 = datetime(2026, 11, 8, 9, 20, 0)

    seed_rows = [
        (
            1,
            1,
            "CF-ARABICA-01",
            "Cà phê rang xay",
            CatalogStatus.ACTIVE.value,
            55_000,
            12,
            2,
            t1,
        ),
        (
            2,
            1,
            "CF-ROBUSTA-02",
            "Cà phê rang xay",
            CatalogStatus.ACTIVE.value,
            45_000,
            8,
            1,
            t2,
        ),
        (
            3,
            1,
            "TEA_OLONG_100%",
            "Trà Ô Long 100% nguyên chất",
            CatalogStatus.INACTIVE.value,
            30_000,
            0,
            0,
            t3,
        ),
        (
            4,
            2,
            "SNK-OREO-01",
            "Bánh quy Oreo Vani",
            CatalogStatus.ACTIVE.value,
            18_000,
            25,
            4,
            t3,
        ),
        (
            5,
            2,
            "SNK-LAYS-02",
            "Khoai tây Lay's",
            CatalogStatus.INACTIVE.value,
            22_000,
            5,
            1,
            t4,
        ),
        (
            6,
            1,
            "MILK-TH-01",
            "Sữa tươi tiệt trùng",
            CatalogStatus.ACTIVE.value,
            32_000,
            40,
            3,
            t5,
        ),
    ]
    for pid, cid, sku, name, st, price, qty, ver, created in seed_rows:
        session.add(
            Product(
                id=pid,
                category_id=cid,
                sku=sku,
                name=name,
                status=st,
                sale_price_vnd=price,
                created_at=created,
                updated_at=created,
            )
        )
        session.add(
            Inventory(
                product_id=pid,
                quantity=qty,
                stock_version=ver,
                first_stocked_at=created if qty > 0 else None,
                updated_at=created,
            )
        )
    session.commit()
    executed_sql.clear()
    return session, executed_sql


def test_sql_repository_search_filter_sort_pagination_and_no_n_plus_one() -> None:
    """Verify SQLAlchemy repository query semantics, tie-breakers, and query count."""
    session, executed_sql = _build_sqlite_product_session()
    service = ProductService()

    # 1. Default sort (created_desc with id DESC tie-breaker):
    # Expected order of IDs: 6 (t5), 5 (t4), 4 (t3, id=4), 3 (t3, id=3), 2 (t2), 1 (t1)
    executed_sql.clear()
    default_res = service.list_products(session, page=1, page_size=20)  # type: ignore[arg-type]
    assert default_res.total == 6
    assert [item.id for item in default_res.items] == [6, 5, 4, 3, 2, 1]
    # Verify exactly 2 SQL statements executed (1 COUNT + 1 SELECT JOIN), no N+1!
    select_statements = [
        s for s in executed_sql if s.lstrip().upper().startswith("SELECT")
    ]
    assert len(select_statements) == 2

    # 2. Sort whitelist: name_asc (id ASC tie-breaker on P1 & P2)
    name_asc_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.NAME_ASC,
    )
    assert [item.id for item in name_asc_res.items] == [4, 1, 2, 5, 6, 3]

    # 3. Sort whitelist: name_desc (with id DESC tie-breaker on P2 & P1)
    name_desc_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.NAME_DESC,
    )
    assert [item.id for item in name_desc_res.items] == [3, 6, 5, 2, 1, 4]

    # 4. Sort whitelist: sku_asc and sku_desc
    sku_asc_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.SKU_ASC,
    )
    assert [item.sku for item in sku_asc_res.items] == [
        "CF-ARABICA-01",
        "CF-ROBUSTA-02",
        "MILK-TH-01",
        "SNK-LAYS-02",
        "SNK-OREO-01",
        "TEA_OLONG_100%",
    ]

    sku_desc_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.SKU_DESC,
    )
    assert [item.sku for item in sku_desc_res.items] == list(
        reversed([item.sku for item in sku_asc_res.items])
    )

    # 5. Case-insensitive search by SKU (even on ascii_bin column) and Vietnamese name
    sku_search_res = service.list_products(
        session,  # type: ignore[arg-type]
        search="  cf-robusta  ",
    )
    assert sku_search_res.total == 1
    assert sku_search_res.items[0].id == 2

    name_search_res = service.list_products(
        session,  # type: ignore[arg-type]
        search="cÀ pHê",
        sort=ProductSortOrder.NAME_ASC,
    )
    assert name_search_res.total == 2
    assert [item.id for item in name_search_res.items] == [1, 2]

    # 6. LIKE wildcard escaping (% and _ treated literally, not as SQL wildcards)
    literal_percent = service.list_products(
        session,  # type: ignore[arg-type]
        search="100%",
    )
    assert [item.id for item in literal_percent.items] == [3]

    literal_underscore = service.list_products(
        session,  # type: ignore[arg-type]
        search="TEA_OLONG",
    )
    assert [item.id for item in literal_underscore.items] == [3]

    # 7. Filter by category_id, status, and combined filters
    cat1_active = service.list_products(
        session,  # type: ignore[arg-type]
        category_id=1,
        status=CatalogStatus.ACTIVE,
        sort=ProductSortOrder.CREATED_DESC,
    )
    assert cat1_active.total == 3
    assert [item.id for item in cat1_active.items] == [6, 2, 1]

    combined = service.list_products(
        session,  # type: ignore[arg-type]
        search="cà phê",
        category_id=1,
        status=CatalogStatus.ACTIVE,
        sort=ProductSortOrder.SKU_DESC,
    )
    assert combined.total == 2
    assert [item.id for item in combined.items] == [2, 1]

    # 8. Multi-page pagination stability across tied names (page_size=2 over 6 items)
    seen_ids: list[int] = []
    for p in (1, 2, 3):
        page_res = service.list_products(
            session,  # type: ignore[arg-type]
            page=p,
            page_size=2,
            sort=ProductSortOrder.NAME_ASC,
        )
        assert page_res.total == 6
        assert page_res.page == p
        assert page_res.page_size == 2
        assert len(page_res.items) == 2
        seen_ids.extend(item.id for item in page_res.items)
    assert seen_ids == [4, 1, 2, 5, 6, 3]
    assert len(set(seen_ids)) == 6

    # 8b. Sort by quantity_asc (0 -> 5 -> 8 -> 12 -> 25 -> 40) and restock_first across pages
    # Seed quantities: P3(0), P5(5), P2(8), P1(12), P4(25), P6(40)
    qty_asc_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.QUANTITY_ASC,
    )
    assert [item.id for item in qty_asc_res.items] == [3, 5, 2, 1, 4, 6]
    assert [item.quantity for item in qty_asc_res.items] == [0, 5, 8, 12, 25, 40]

    restock_res = service.list_products(
        session,  # type: ignore[arg-type]
        sort=ProductSortOrder.RESTOCK_FIRST,
    )
    assert [item.id for item in restock_res.items] == [3, 5, 2, 1, 4, 6]

    # Multi-page pagination with quantity_asc (page_size=2 over 6 items)
    qty_paged_ids: list[int] = []
    for p in (1, 2, 3):
        page_res = service.list_products(
            session,  # type: ignore[arg-type]
            page=p,
            page_size=2,
            sort=ProductSortOrder.QUANTITY_ASC,
        )
        assert page_res.total == 6
        qty_paged_ids.extend(item.id for item in page_res.items)
    assert qty_paged_ids == [3, 5, 2, 1, 4, 6]

    # 9. Empty result
    empty_res = service.list_products(
        session,  # type: ignore[arg-type]
        search="KHONG-TON-TAI-XYZ",
    )
    assert empty_res.total == 0
    assert empty_res.items == []
    assert empty_res.page == 1
    assert empty_res.page_size == 20


def test_router_and_service_query_contract_and_validation_sync() -> None:
    """Verify router endpoint, service validation, and OpenAPI schema synchronously."""
    from app.modules.products.router import list_products

    session, _ = _build_sqlite_product_session()
    service = ProductService()
    application = create_app(test_settings())

    # 1. OpenAPI schema for GET /api/v1/products exposes exact query contract
    openapi = application.openapi()
    get_op = openapi["paths"]["/api/v1/products"]["get"]
    param_map = {p["name"]: p for p in get_op["parameters"]}
    assert set(param_map.keys()) == {
        "page",
        "page_size",
        "search",
        "category_id",
        "status",
        "sort",
    }
    assert "stock_status" not in param_map
    assert param_map["sort"]["schema"]["default"] == "created_desc"

    # 2. Direct router call for STAFF and ADMIN returns filtered ProductListResponse
    for role in (UserRole.STAFF, UserRole.ADMIN):
        principal = make_principal(role)
        res = list_products(
            _current_user=principal.user,
            session=session,  # type: ignore[arg-type]
            service=service,
            page=1,
            page_size=2,
            search="Cà phê",
            category_id=1,
            status=CatalogStatus.ACTIVE,
            sort=ProductSortOrder.NAME_ASC,
        )
        assert res.total == 2
        assert [item.id for item in res.items] == [1, 2]
        for item in res.items:
            dumped = item.model_dump()
            assert "unit_cost_vnd" not in dumped
            assert "cost" not in dumped

    # 3. Service validation rejects invalid bounds, search length, status, and sort
    for invalid_kwargs in (
        {"page": 0},
        {"page": -1},
        {"page_size": 0},
        {"page_size": 101},
        {"category_id": 0},
        {"category_id": -3},
        {"search": "x" * 101},
        {"status": "DELETED"},
        {"sort": "invalid_sort"},
        {"sort": "price_asc"},
    ):
        with pytest.raises(DomainValidationError) as exc_info:
            service.list_products(
                session,  # type: ignore[arg-type]
                **invalid_kwargs,  # type: ignore[arg-type]
            )
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "VALIDATION_ERROR"


@pytest.mark.anyio
async def test_api_products_query_params_validation_and_staff_admin_access() -> None:
    """Verify HTTP query parameter contract, 422 validation, and DTO field safety."""
    settings = test_settings()
    sql_session, _ = _build_sqlite_product_session()
    service = ProductService()

    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_db_session] = lambda: sql_session
    application.dependency_overrides[get_product_service] = lambda: service

    for role in (UserRole.STAFF, UserRole.ADMIN):
        application.dependency_overrides[get_current_principal] = lambda r=role: (
            make_principal(r)
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                "/api/v1/products",
                params={
                    "page": 1,
                    "page_size": 2,
                    "search": "Cà phê",
                    "category_id": 1,
                    "status": "ACTIVE",
                    "sort": "name_asc",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 2
            assert body["page"] == 1
            assert body["page_size"] == 2
            assert [item["id"] for item in body["items"]] == [1, 2]
            for item in body["items"]:
                assert set(item.keys()) == {
                    "id",
                    "category_id",
                    "sku",
                    "name",
                    "status",
                    "sale_price_vnd",
                    "quantity",
                    "stock_version",
                    "created_at",
                    "updated_at",
                }
                assert "unit_cost_vnd" not in item
                assert "cost" not in item

    # Negative validation tests (422) — invalid params never silently ignored
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        for invalid_params in (
            {"page": 0},
            {"page": -1},
            {"page_size": 0},
            {"page_size": 101},
            {"category_id": 0},
            {"category_id": -3},
            {"status": "DELETED"},
            {"status": "PENDING"},
            {"search": "x" * 101},
            {"sort": "invalid_sort"},
            {"sort": "price_asc"},
            {"sort": "id; DROP TABLE products"},
        ):
            bad_resp = await client.get("/api/v1/products", params=invalid_params)
            assert bad_resp.status_code == 422, f"Expected 422 for {invalid_params}"
            err_body = bad_resp.json()
            assert err_body["code"] == "VALIDATION_ERROR"
