"""Full HTTP E2E integration test for POST /api/v1/ai/query (MySQL + Redis + Auth)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.modules.ai.gemini_provider import ProviderFunctionCall, ProviderTurnResponse
from app.modules.ai.orchestrator import AIOrchestrator
from app.modules.ai.router import get_ai_orchestrator, get_ai_session_factory
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.security import PasswordHasher
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = [pytest.mark.integration, pytest.mark.redis_integration]
__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


class _ControlledE2EGeminiProvider:
    async def generate_turn(
        self, user_message: str, *, timeout_seconds: float
    ) -> ProviderTurnResponse:
        return ProviderTurnResponse(
            text=None,
            function_calls=(
                ProviderFunctionCall(
                    name="get_sales_summary",
                    arguments={"start_date": "2026-11-18", "end_date": "2026-11-18"},
                ),
            ),
            conversation_state=["turn1"],
        )

    async def submit_tool_results(
        self,
        conversation_state: Any,
        tool_responses: tuple[Any, ...],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        payload = tool_responses[0].payload
        rev = payload["data"]["revenue_vnd"]
        return ProviderTurnResponse(
            text=f"Doanh thu ngày 2026-11-18 là {rev:,} VND.",
            function_calls=(),
            conversation_state=["turn2"],
        )


@pytest.mark.anyio
async def test_ai_query_http_e2e_with_real_mysql_auth_and_redis(
    migrated_integration_engine: Engine,
    integration_database_url: Any,
) -> None:
    redis_url = os.getenv("RETAILOPS_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("RETAILOPS_TEST_REDIS_URL is required")

    run_id = uuid4().hex[:12]
    now = datetime(2026, 11, 18, 10, 0)
    hasher = PasswordHasher(work_factor=4)
    password = "AiE2ePassword!123"
    admin_email = f"ai-e2e-admin-{run_id}@retailops.local"
    staff_email = f"ai-e2e-staff-{run_id}@retailops.local"

    user_ids: list[int] = []
    category_ids: list[int] = []
    product_ids: list[int] = []
    order_ids: list[int] = []
    order_item_ids: list[int] = []

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            admin = User(
                email_normalized=admin_email,
                password_hash=hasher.hash(password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=None,
                created_at=now,
                updated_at=now,
            )
            staff = User(
                email_normalized=staff_email,
                password_hash=hasher.hash(password),
                role=UserRole.STAFF,
                status=UserStatus.ACTIVE,
                admin_slot=None,
                created_at=now,
                updated_at=now,
            )
            cat = Category(
                name=f"AI-E2E-Cat-{run_id}",
                description="E2E category",
                created_at=now,
            )
            session.add_all([admin, staff, cat])
            session.flush()
            user_ids.extend([admin.id, staff.id])
            category_ids.append(cat.id)

            prod = Product(
                category_id=cat.id,
                sku=f"AI-E2E-{run_id}",
                name=f"AI E2E Product {run_id}",
                unit="pcs",
                unit_price_vnd=25000,
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            product_ids.append(prod.id)

            session.add(Inventory(product_id=prod.id, quantity=5, updated_at=now))
            order = Order(
                order_code=f"ORD-AIE2E-{run_id}",
                status=OrderStatus.COMPLETED,
                total_vnd=75000,
                created_by=admin.id,
                created_at=datetime(2026, 11, 18, 9, 0),
            )
            session.add(order)
            session.flush()
            order_ids.append(order.id)

            item = OrderItem(
                order_id=order.id,
                product_id=prod.id,
                quantity=3,
                unit_price_vnd=25000,
                line_total_vnd=75000,
            )
            session.add(item)
            session.flush()
            order_item_ids.append(item.id)

        sf = sessionmaker(
            bind=migrated_integration_engine, autoflush=False, expire_on_commit=False
        )
        settings = Settings(
            _env_file=None,
            environment="development",
            db_host=integration_database_url.host or "127.0.0.1",
            db_port=integration_database_url.port or 3306,
            db_name=integration_database_url.database or "retailops_test",
            db_user=integration_database_url.username or "retailops_test_runner",
            db_password=SecretStr(integration_database_url.password or ""),
            jwt_secret=SecretStr("j" * 32),
            csrf_secret=SecretStr("c" * 32),
            redis_url=SecretStr(redis_url),
            rate_limit_namespace=f"retailops:ai-e2e:{run_id}",
            ai_rate_limit=2,
            ai_rate_window_seconds=60,
            ai_max_concurrent_requests=2,
        )
        app = create_app(settings)

        def _override_db():
            with sf() as session:
                yield session

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[get_ai_session_factory] = lambda: sf
        app.dependency_overrides[get_ai_orchestrator] = lambda: AIOrchestrator(
            session_factory=sf,
            provider_factory=_ControlledE2EGeminiProvider,
            gemini_timeout_seconds=10.0,
        )

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1"
            ) as client:
                admin_login = await client.post(
                    "/api/v1/auth/login",
                    json={"email": admin_email, "password": password},
                )
                assert admin_login.status_code == 200
                admin_token = admin_login.json()["access_token"]

                staff_login = await client.post(
                    "/api/v1/auth/login",
                    json={"email": staff_email, "password": password},
                )
                assert staff_login.status_code == 200
                staff_token = staff_login.json()["access_token"]

                # 1. STAFF rejected with 403
                r_staff = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {staff_token}"},
                    json={"message": "Phân tích doanh thu ngày 2026-11-18"},
                )
                assert r_staff.status_code == 403

                # 2. ADMIN query -> real MySQL ToolExecutor + grounded evidence
                r1 = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"message": "Phân tích doanh thu ngày 2026-11-18"},
                )
                assert r1.status_code == 200
                body = r1.json()
                assert body["insufficient_data"] is False
                assert "get_sales_summary" in body["evidence"][0]["source"]
                assert "revenue_vnd=" in body["evidence"][0]["summary"]

                # 3. Second request within limit -> 200
                r2 = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"message": "Xin chào"},
                )
                assert r2.status_code == 200

                # 4. Third request exceeds ai_rate_limit=2 -> 429 from real Redis
                r3 = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"message": "Xin chào"},
                )
                assert r3.status_code == 429
    finally:
        with Session(migrated_integration_engine) as session, session.begin():
            if order_item_ids:
                session.execute(
                    delete(OrderItem).where(OrderItem.id.in_(order_item_ids))
                )
            if order_ids:
                session.execute(delete(Order).where(Order.id.in_(order_ids)))
            if product_ids:
                session.execute(
                    delete(Inventory).where(Inventory.product_id.in_(product_ids))
                )
                session.execute(delete(Product).where(Product.id.in_(product_ids)))
            if category_ids:
                session.execute(delete(Category).where(Category.id.in_(category_ids)))
            if user_ids:
                session.execute(
                    delete(RefreshToken).where(
                        RefreshToken.session_id.in_(
                            select(AuthSession.id).where(
                                AuthSession.user_id.in_(user_ids)
                            )
                        )
                    )
                )
                session.execute(
                    delete(AuthSession).where(AuthSession.user_id.in_(user_ids))
                )
                session.execute(delete(User).where(User.id.in_(user_ids)))
