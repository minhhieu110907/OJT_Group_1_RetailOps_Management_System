"""Real E2E integration & recovery validation for T04AB73 (AI + Redis + Worker)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from celery import Celery
from kombu import Exchange, Queue
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.infrastructure.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from app.modules.ai.concurrency import RedisAIConcurrencyGuard
from app.modules.ai.gemini_provider import (
    GeminiProvider,
    ProviderTurnResponse,
    ToolResponseItem,
)
from app.modules.ai.orchestrator import AIOrchestrator
from app.modules.ai.router import get_ai_orchestrator, get_ai_session_factory
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.modules.auth.security import JwtService, PasswordHasher
from app.modules.categories.models import Category
from app.modules.inventory.models import StockMovement
from app.modules.outbox.broker import CeleryEventPublisher
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.publisher import OutboxPublisher
from app.modules.outbox.writer import OutboxWriter
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.purchasing.models import PurchaseReceipt
from app.modules.sales.models import Order, OrderItem, OrderStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]

LIVE_EXCHANGE = Exchange("retailops.email", type="direct", durable=True)
LIVE_QUEUE = Queue(
    "retailops.email.v1",
    exchange=LIVE_EXCHANGE,
    routing_key="email.deliver.v1",
    durable=True,
    queue_arguments={"x-queue-type": "quorum"},
)


async def _cleanup_redis_namespace(redis_client: Redis, namespace: str) -> None:
    """Delete only keys created under this test run's isolated namespace."""
    keys = [key async for key in redis_client.scan_iter(match=f"{namespace}:*")]
    if keys:
        await redis_client.delete(*keys)


class _ObservingLiveGeminiProvider:
    """Pass-through observer over the real GeminiProvider (never mocks responses)."""

    def __init__(self, inner: GeminiProvider) -> None:
        self._inner = inner
        self.generate_calls = 0
        self.tool_call_names: list[str] = []
        self.submit_tool_calls = 0

    async def generate_turn(
        self, user_message: str, *, timeout_seconds: float
    ) -> ProviderTurnResponse:
        self.generate_calls += 1
        turn = await self._inner.generate_turn(
            user_message, timeout_seconds=timeout_seconds
        )
        self.tool_call_names.extend(call.name for call in turn.function_calls)
        return turn

    async def submit_tool_results(
        self,
        conversation_state: object,
        tool_responses: tuple[ToolResponseItem, ...],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        self.submit_tool_calls += 1
        return await self._inner.submit_tool_results(
            conversation_state, tool_responses, timeout_seconds=timeout_seconds
        )


def _assert_no_secrets_leaked(text: str, *, forbidden_secrets: tuple[str, ...]) -> None:
    for secret in forbidden_secrets:
        if secret:
            assert secret not in text


def _cleanup_ai_run(
    engine: Engine,
    *,
    order_ids: tuple[int, ...] = (),
    product_ids: tuple[int, ...] = (),
    category_ids: tuple[int, ...] = (),
    owned_session_ids: tuple[bytes, ...] = (),
    owned_user_ids: tuple[int, ...] = (),
) -> None:
    with Session(engine) as session, session.begin():
        if order_ids:
            session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            session.execute(delete(Order).where(Order.id.in_(order_ids)))
        if product_ids:
            session.execute(
                delete(Inventory).where(Inventory.product_id.in_(product_ids))
            )
            session.execute(delete(Product).where(Product.id.in_(product_ids)))
        if category_ids:
            session.execute(delete(Category).where(Category.id.in_(category_ids)))
        sess_ids = set(owned_session_ids)
        if owned_user_ids:
            sess_ids.update(
                session.scalars(
                    select(AuthSession.id).where(
                        AuthSession.user_id.in_(owned_user_ids)
                    )
                )
            )
        if sess_ids:
            session.execute(
                delete(RefreshToken).where(RefreshToken.session_id.in_(sess_ids))
            )
            session.execute(delete(AuthSession).where(AuthSession.id.in_(sess_ids)))
        if owned_user_ids:
            session.execute(delete(User).where(User.id.in_(owned_user_ids)))


def _seed_ai_context(
    engine: Engine, *, run_id: str
) -> tuple[int, int, int, int, int, list[int], list[bytes]]:
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    hasher = PasswordHasher(work_factor=4)
    owned_user_ids: list[int] = []
    owned_session_ids: list[bytes] = []

    with Session(engine) as session, session.begin():
        existing_admin = session.scalar(
            select(User).where(
                User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
            )
        )
        if existing_admin is None:
            admin = User(
                email_normalized=f"t04ab73-admin-{run_id}@retailops.local",
                password_hash=hasher.hash("T04ab73Admin!123"),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()
            admin_id = admin.id
            owned_user_ids.append(admin_id)
        else:
            admin_id = existing_admin.id

        staff = User(
            email_normalized=f"t04ab73-staff-{run_id}@retailops.local",
            password_hash=hasher.hash("T04ab73Staff!123"),
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        cat = Category(
            name=f"T04AB73-Cat-{run_id}",
            description="T04AB73 E2E category",
            status=CatalogStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add_all([staff, cat])
        session.flush()
        owned_user_ids.append(staff.id)

        prod = Product(
            category_id=cat.id,
            sku=f"T04AB73-{run_id}",
            name=f"T04AB73 Item {run_id}",
            status=CatalogStatus.ACTIVE,
            sale_price_vnd=50_000,
            created_at=now,
            updated_at=now,
        )
        session.add(prod)
        session.flush()
        session.add(
            Inventory(
                product_id=prod.id,
                quantity=2,
                stock_version=1,
                first_stocked_at=now - timedelta(days=2),
                updated_at=now,
            )
        )
        order = Order(
            created_by=staff.id,
            status=OrderStatus.COMPLETED,
            total_vnd=150_000,
            sold_at=now - timedelta(hours=2),
        )
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=prod.id,
                sku_snapshot=prod.sku,
                product_name_snapshot=prod.name,
                unit_price_vnd=50_000,
                quantity=3,
                line_total_vnd=150_000,
            )
        )
        admin_sess = uuid4().bytes
        staff_sess = uuid4().bytes
        session.add_all(
            [
                AuthSession(
                    id=admin_sess,
                    user_id=admin_id,
                    created_at=now,
                    expires_at=now + timedelta(hours=2),
                ),
                AuthSession(
                    id=staff_sess,
                    user_id=staff.id,
                    created_at=now,
                    expires_at=now + timedelta(hours=2),
                ),
            ]
        )
        owned_session_ids.extend([admin_sess, staff_sess])
        return (
            admin_id,
            staff.id,
            cat.id,
            prod.id,
            order.id,
            owned_user_ids,
            owned_session_ids,
        )


@pytest.mark.integration
@pytest.mark.redis_integration
@pytest.mark.anyio
async def test_t04ab73_ai_redis_interruption_recovery_and_safe_logs(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify real MySQL+Redis AI auth, fail-closed Redis outage, recovery & logs."""
    redis_url = os.getenv("RETAILOPS_TEST_REDIS_URL")
    if not redis_url:
        pytest.fail("RETAILOPS_TEST_REDIS_URL is required for Redis integration tests")

    run_id = uuid4().hex[:12]
    jwt_secret = f"t04ab73-jwt-secret-{run_id}-0123456789abcdef"
    csrf_secret = f"t04ab73-csrf-secret-{run_id}-0123456789abcdef"
    idem_secret = f"t04ab73-idem-secret-{run_id}-0123456789abcdef"
    (
        admin_id,
        staff_id,
        cat_id,
        prod_id,
        order_id,
        owned_users,
        owned_sessions,
    ) = _seed_ai_context(migrated_integration_engine, run_id=run_id)

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
        jwt_secret=SecretStr(jwt_secret),
        csrf_secret=SecretStr(csrf_secret),
        idempotency_secret=SecretStr(idem_secret),
        redis_url=SecretStr(redis_url),
        redis_connect_timeout_seconds=1.0,
        redis_socket_timeout_seconds=1.0,
    )

    now = datetime.now(UTC)
    jwt_svc = JwtService(settings)
    admin_tok, _ = jwt_svc.issue(
        user_id=admin_id,
        session_id=UUID(bytes=owned_sessions[0]),
        session_expires_at=now + timedelta(hours=2),
        now=now,
    )
    staff_tok, _ = jwt_svc.issue(
        user_id=staff_id,
        session_id=UUID(bytes=owned_sessions[1]),
        session_expires_at=now + timedelta(hours=2),
        now=now,
    )
    forbidden_secrets = (
        jwt_secret,
        csrf_secret,
        idem_secret,
        admin_tok,
        staff_tok,
        integration_database_url.password or "",
    )

    healthy_redis = Redis.from_url(redis_url, decode_responses=False)
    broken_redis = Redis.from_url(
        "redis://127.0.0.1:1/15",
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
        decode_responses=False,
    )
    ns = f"t04ab73-{run_id}"
    canary_key = f"t04ab73-unrelated-canary-{run_id}"

    try:
        await healthy_redis.set(canary_key, b"preserve-me", ex=60)
        app = create_app(settings)
        app.state.rate_limiter = RedisFixedWindowRateLimiter(healthy_redis, ns)
        app.state.ai_concurrency_guard = RedisAIConcurrencyGuard(healthy_redis, ns)

        def _override_db():
            with sf() as session:
                yield session

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[get_ai_session_factory] = lambda: sf

        with Session(migrated_integration_engine) as session:
            before_counts = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
            )

        with caplog.at_level("INFO"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                # 1. STAFF denied -> 403
                r_staff = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {staff_tok}"},
                    json={"message": "Tồn kho thấp"},
                )
                assert r_staff.status_code == 403
                _assert_no_secrets_leaked(
                    r_staff.text, forbidden_secrets=forbidden_secrets
                )

                # 2. ADMIN direct-tool query with real MySQL + real Redis -> 200
                r_ok = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_tok}"},
                    json={"message": "Tồn kho thấp"},
                )
                assert r_ok.status_code == 200
                assert f"T04AB73-{run_id}" in r_ok.json()["answer"]
                _assert_no_secrets_leaked(
                    r_ok.text, forbidden_secrets=forbidden_secrets
                )

                # 3. Simulated Redis connection failure -> fail closed (503, no bypass)
                app.state.rate_limiter = RedisFixedWindowRateLimiter(broken_redis, ns)
                app.state.ai_concurrency_guard = RedisAIConcurrencyGuard(
                    broken_redis, ns
                )
                r_down = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_tok}"},
                    json={"message": "Tồn kho thấp"},
                )
                assert r_down.status_code == 503
                _assert_no_secrets_leaked(
                    r_down.text, forbidden_secrets=forbidden_secrets
                )
                assert "Traceback" not in r_down.text

                # 4. Redis connection restored -> subsequent request succeeds 200
                app.state.rate_limiter = RedisFixedWindowRateLimiter(healthy_redis, ns)
                app.state.ai_concurrency_guard = RedisAIConcurrencyGuard(
                    healthy_redis, ns
                )
                r_rec = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_tok}"},
                    json={"message": "Tồn kho thấp"},
                )
                assert r_rec.status_code == 200

        # 5. Read-only DB invariant, Redis key isolation & security-safe logs
        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 2 and inv.stock_version == 1
            after_counts = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
            )
            assert after_counts == before_counts

        for rec in caplog.records:
            _assert_no_secrets_leaked(
                rec.getMessage(), forbidden_secrets=forbidden_secrets
            )
            assert "Bearer " not in rec.getMessage()

        await _cleanup_redis_namespace(healthy_redis, ns)
        assert await healthy_redis.get(canary_key) == b"preserve-me"
    finally:
        await _cleanup_redis_namespace(healthy_redis, ns)
        await healthy_redis.delete(canary_key)
        await healthy_redis.aclose()
        await broken_redis.aclose()
        _cleanup_ai_run(
            migrated_integration_engine,
            order_ids=(order_id,),
            product_ids=(prod_id,),
            category_ids=(cat_id,),
            owned_session_ids=tuple(owned_sessions),
            owned_user_ids=tuple(owned_users),
        )


@pytest.mark.integration
@pytest.mark.redis_integration
@pytest.mark.anyio
async def test_t04ab73_real_gemini_provider_e2e_with_mysql_and_redis(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Live Gemini provider E2E against isolated MySQL + Redis (requires API key)."""
    api_key = os.getenv("RETAILOPS_GEMINI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("RETAILOPS_GEMINI_API_KEY is required for live Gemini E2E")
    redis_url = os.getenv("RETAILOPS_TEST_REDIS_URL")
    if not redis_url:
        pytest.fail("RETAILOPS_TEST_REDIS_URL is required for Redis integration tests")

    run_id = uuid4().hex[:12]
    model = os.getenv("RETAILOPS_GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
    (
        admin_id,
        _staff_id,
        cat_id,
        prod_id,
        order_id,
        owned_users,
        owned_sessions,
    ) = _seed_ai_context(migrated_integration_engine, run_id=run_id)

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
        jwt_secret=SecretStr(f"t04ab73-live-jwt-{run_id}-0123456789abcdef"),
        csrf_secret=SecretStr(f"t04ab73-live-csrf-{run_id}-0123456789abcdef"),
        idempotency_secret=SecretStr(f"t04ab73-live-idem-{run_id}-0123456789abcdef"),
        redis_url=SecretStr(redis_url),
        gemini_api_key=SecretStr(api_key),
        gemini_model=model,
    )
    now = datetime.now(UTC)
    admin_tok, _ = JwtService(settings).issue(
        user_id=admin_id,
        session_id=UUID(bytes=owned_sessions[0]),
        session_expires_at=now + timedelta(hours=2),
        now=now,
    )
    redis_client = Redis.from_url(redis_url, decode_responses=False)
    ns = f"t04ab73-live-{run_id}"
    observer = _ObservingLiveGeminiProvider(
        GeminiProvider(api_key=api_key, model=model, timeout_seconds=10.0)
    )
    try:
        app = create_app(settings)
        app.state.rate_limiter = RedisFixedWindowRateLimiter(redis_client, ns)
        app.state.ai_concurrency_guard = RedisAIConcurrencyGuard(redis_client, ns)

        def _override_db():
            with sf() as session:
                yield session

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db_session] = _override_db
        app.dependency_overrides[get_ai_session_factory] = lambda: sf
        app.dependency_overrides[get_ai_orchestrator] = lambda: AIOrchestrator(
            session_factory=sf,
            provider_factory=lambda: observer,
            gemini_timeout_seconds=10.0,
        )

        with Session(migrated_integration_engine) as session:
            before_counts = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
            )

        with caplog.at_level("INFO"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/ai/query",
                    headers={"Authorization": f"Bearer {admin_tok}"},
                    json={"message": "Sản phẩm bán chạy trong 7 ngày qua"},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"].strip()
        assert body["evidence"]
        # Prove live Gemini provider was actually called and performed tool calling
        assert observer.generate_calls >= 1
        assert observer.tool_call_names
        assert observer.submit_tool_calls >= 1
        # Verify DB remained strictly read-only
        with Session(migrated_integration_engine) as session:
            inv = session.get(Inventory, prod_id)
            assert inv is not None and inv.quantity == 2 and inv.stock_version == 1
            after_counts = (
                session.scalar(select(func.count(StockMovement.id))),
                session.scalar(select(func.count(Order.id))),
                session.scalar(select(func.count(PurchaseReceipt.id))),
            )
            assert after_counts == before_counts
        forbidden = (api_key, admin_tok, integration_database_url.password or "")
        _assert_no_secrets_leaked(resp.text, forbidden_secrets=forbidden)
        for rec in caplog.records:
            _assert_no_secrets_leaked(rec.getMessage(), forbidden_secrets=forbidden)
    finally:
        await _cleanup_redis_namespace(redis_client, ns)
        await redis_client.aclose()
        _cleanup_ai_run(
            migrated_integration_engine,
            order_ids=(order_id,),
            product_ids=(prod_id,),
            category_ids=(cat_id,),
            owned_session_ids=tuple(owned_sessions),
            owned_user_ids=tuple(owned_users),
        )


@pytest.mark.rabbitmq_integration
def test_t04ab73_worker_interruption_recovery_and_mailpit_safe_logs(
    migrated_integration_engine: Engine,
    integration_database_url: URL,
) -> None:
    """Verify queued message survives worker outage, delivers to Mailpit & logs safe."""
    publisher_url = os.environ.get("RETAILOPS_TEST_RABBITMQ_PUBLISHER_URL")
    worker_url = os.environ.get("RETAILOPS_TEST_RABBITMQ_WORKER_URL")
    smtp_port = os.environ.get("MAILPIT_SMTP_HOST_PORT")
    mailpit_http_port = os.environ.get("MAILPIT_HTTP_HOST_PORT")
    if not all([publisher_url, worker_url, smtp_port, mailpit_http_port]):
        pytest.fail("RabbitMQ and Mailpit test environment variables are required")

    run_id = uuid4().hex[:12]
    recipient = f"t04ab73-worker-{run_id}@example.com"
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
    user_id: int | None = None
    event_id: bytes | None = None

    try:
        # 1. Commit real business + Outbox event while NO Celery worker is running
        with Session(migrated_integration_engine) as session, session.begin():
            user = User(
                email_normalized=recipient,
                password_hash="t04ab73-non-secret-hash",
                role=UserRole.STAFF,
                status=UserStatus.ACTIVE,
                admin_slot=None,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            user_id = user.id
            event_id = OutboxWriter().append(
                session,
                subject_user_id=user.id,
                event_type="STAFF_APPROVED",
                payload={"schema_version": 1, "approval_request_id": 1, "actor_id": 1},
                available_at_utc=now,
            )

        # 2. Publish to real RabbitMQ while worker is stopped -> message stays queued
        sf = sessionmaker(bind=migrated_integration_engine, expire_on_commit=False)
        pub_celery = Celery(f"t04ab73-pub-{run_id}", broker=publisher_url)
        pub_celery.conf.broker_transport_options = {"confirm_publish": True}
        pub_celery.conf.task_queues = (LIVE_QUEUE,)
        pub_result = OutboxPublisher(CeleryEventPublisher(pub_celery)).publish_due(
            sf, batch_size=25
        )
        assert pub_result.published >= 1

        # Confirm event is published in DB but NOT yet SENT (worker is down)
        with Session(migrated_integration_engine) as session:
            ev = session.get(OutboxEvent, event_id)
            assert ev is not None
            assert ev.published_at is not None
            assert ev.outcome is None

        # 3. Start real Celery worker -> consumes queued message & sends to Mailpit
        env = os.environ.copy()
        env.update(
            {
                "RETAILOPS_ENVIRONMENT": "development",
                "RETAILOPS_DB_HOST": integration_database_url.host or "127.0.0.1",
                "RETAILOPS_DB_PORT": str(integration_database_url.port or 3306),
                "RETAILOPS_DB_NAME": integration_database_url.database
                or "retailops_test",
                "RETAILOPS_DB_USER": integration_database_url.username
                or "retailops_test_runner",
                "RETAILOPS_DB_PASSWORD": integration_database_url.password or "",
                "RETAILOPS_RABBITMQ_URL": worker_url or "",
                "RETAILOPS_SMTP_HOST": "127.0.0.1",
                "RETAILOPS_SMTP_PORT": str(smtp_port),
                "RETAILOPS_SMTP_STARTTLS": "false",
                "RETAILOPS_SMTP_FROM_ADDRESS": "no-reply@retailops.local",
                "RETAILOPS_JWT_SECRET": "j" * 32,
                "RETAILOPS_CSRF_SECRET": "c" * 32,
                "RETAILOPS_IDEMPOTENCY_SECRET": "i" * 32,
            }
        )
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "app.worker.celery_app:celery_app",
                    "worker",
                    "--loglevel=INFO",
                    "--pool=solo",
                    "--concurrency=1",
                    "--without-gossip",
                    "--without-mingle",
                    "--without-heartbeat",
                    "--queues=retailops.email.v1",
                ],
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 30.0
                delivered = False
                while time.monotonic() < deadline:
                    with Session(migrated_integration_engine) as session:
                        ev = session.get(OutboxEvent, event_id)
                        if ev is not None and ev.outcome == "SENT":
                            delivered = True
                            break
                    time.sleep(0.5)
                assert delivered, "Worker did not deliver queued event after startup"
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                log_file.seek(0)
                worker_logs = log_file.read()

        # 4. Inspect real Mailpit message via HTTP API
        with urllib.request.urlopen(
            f"http://127.0.0.1:{mailpit_http_port}/api/v1/messages", timeout=10
        ) as resp:
            messages = json.loads(resp.read()).get("messages", [])
        matching = [
            m
            for m in messages
            if any(addr.get("Address") == recipient for addr in (m.get("To") or []))
        ]
        assert matching, f"Expected Mailpit email for {recipient}"

        # 5. Security-safe log & email verification (no DB/broker/app secrets leaked)
        forbidden_worker_secrets = (
            integration_database_url.password or "",
            os.environ.get("RABBITMQ_WORKER_PASSWORD", ""),
            worker_url or "",
            "j" * 32,
            "c" * 32,
            "i" * 32,
        )
        _assert_no_secrets_leaked(
            worker_logs, forbidden_secrets=forbidden_worker_secrets
        )
        assert "amqp://" not in worker_logs
        _assert_no_secrets_leaked(
            json.dumps(matching[0]), forbidden_secrets=forbidden_worker_secrets
        )
    finally:
        with Session(migrated_integration_engine) as session, session.begin():
            if event_id is not None:
                session.execute(delete(OutboxEvent).where(OutboxEvent.id == event_id))
            if user_id is not None:
                session.execute(delete(User).where(User.id == user_id))
