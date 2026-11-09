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
        self, _session: object, *, page: int, page_size: int
    ) -> tuple[list[tuple[Product, Inventory]], int]:
        ordered_ids = sorted(self.store.products.keys())
        total = len(ordered_ids)
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            (self.store.products[pid], self.store.inventory[pid])
            for pid in ordered_ids[start:end]
        ]
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

    def add_zero(
        self, _session: object, product_id: int, now: datetime
    ) -> Inventory:
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


def build_fake_service() -> tuple[
    ProductService, InMemoryProductStore, FakeSession
]:
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
    application.dependency_overrides[get_current_principal] = lambda: (
        CurrentPrincipal(user=pending_user, session_id=uuid4())
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        pending_resp = await client.get("/api/v1/products")
        assert pending_resp.status_code == 403
        assert pending_resp.json()["code"] == "FORBIDDEN"


