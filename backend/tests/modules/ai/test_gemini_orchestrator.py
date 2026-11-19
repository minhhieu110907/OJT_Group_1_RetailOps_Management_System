"""Unit, security, concurrency, and API tests for T04AA86 Gemini & AI orchestration."""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import SecretStr, ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    DependencyUnavailableError,
    DomainValidationError,
    RateLimitedError,
)
from app.db.base import Base
from app.infrastructure.dependencies import get_rate_limiter
from app.infrastructure.rate_limit import RateLimitResult
from app.main import create_app
from app.modules.ai.concurrency import RedisAIConcurrencyGuard
from app.modules.ai.dependencies import get_bound_tool_request
from app.modules.ai.gemini_provider import (
    APPROVED_TOOL_NAMES,
    GeminiProvider,
    GeminiProviderError,
    GeminiQuotaExceededError,
    GeminiTimeoutError,
    ProviderFunctionCall,
    ProviderTurnResponse,
    ToolResponseItem,
    build_gemini_function_declarations,
)
from app.modules.ai.orchestrator import AIOrchestrator
from app.modules.ai.router import (
    get_ai_concurrency_guard,
    get_ai_orchestrator,
    get_ai_session_factory,
)
from app.modules.ai.tool_executor import bind_authenticated_request
from app.modules.auth.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_active_admin,
)
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.categories.models import Category
from app.modules.products.models import CatalogStatus, Inventory, Product
from app.modules.sales.models import Order, OrderItem, OrderStatus


def _make_sqlite_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_collation(dbapi_conn, _conn_record):
        dbapi_conn.create_collation("ascii_bin", lambda a, b: (a > b) - (a < b))

    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Category.__table__,
            Product.__table__,
            Inventory.__table__,
            Order.__table__,
            OrderItem.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_admin_and_data(sf, *, with_sales: bool = True, with_low_stock: bool = True):
    now = datetime(2026, 11, 18, 10, 0)
    with sf() as session, session.begin():
        admin = User(
            email_normalized="admin@retailops.local",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        staff = User(
            email_normalized="staff@retailops.local",
            password_hash="hash",
            role=UserRole.STAFF,
            status=UserStatus.ACTIVE,
            admin_slot=None,
            created_at=now,
            updated_at=now,
        )
        session.add_all([admin, staff])
        session.flush()
        if with_sales or with_low_stock:
            cat = Category(name="Beverages", description="Drinks", created_at=now)
            session.add(cat)
            session.flush()
            prod = Product(
                category_id=cat.id,
                sku="SKU-AI-001",
                name="Green Tea",
                unit="bottle",
                unit_price_vnd=25000,
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            session.add(
                Inventory(
                    product_id=prod.id,
                    quantity=2 if with_low_stock else 50,
                    updated_at=now,
                )
            )
            if with_sales:
                order = Order(
                    order_code="ORD-AI-001",
                    status=OrderStatus.COMPLETED,
                    total_vnd=50000,
                    created_by=admin.id,
                    created_at=datetime(2026, 11, 18, 8, 0),
                )
                session.add(order)
                session.flush()
                session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        quantity=2,
                        unit_price_vnd=25000,
                        line_total_vnd=50000,
                    )
                )
        return admin.id, staff.id


def _load_principal(sf, user_id: int) -> CurrentPrincipal:
    with sf() as session:
        user = session.get(User, user_id)
        assert user is not None
        session.expunge(user)
    return CurrentPrincipal(user=user, session_id=uuid4())


def _base_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "db_host": "127.0.0.1",
        "db_name": "retailops_test",
        "db_user": "retailops",
        "db_password": SecretStr("secret"),
        "jwt_secret": SecretStr("j" * 32),
        "csrf_secret": SecretStr("c" * 32),
        "gemini_api_key": SecretStr("AIzaSyFakeKeyForUnitTestOnly12345"),
        "gemini_model": "gemini-2.5-flash",
        "gemini_timeout_seconds": 10.0,
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_gemini_env_normalization_and_validation() -> None:
    s1 = _base_settings(gemini_api_key="   ")
    assert s1.gemini_api_key is None
    with pytest.raises(ValidationError):
        _base_settings(gemini_model="   ")
    with pytest.raises(ValidationError):
        _base_settings(ai_rate_limit=0)


def test_function_declarations_match_only_four_approved_tools() -> None:
    decls = build_gemini_function_declarations()
    assert tuple(d.name for d in decls) == APPROVED_TOOL_NAMES
    for decl in decls:
        schema_str = str(decl.parameters_json_schema).lower()
        assert "sql" not in schema_str
        assert "user_id" not in schema_str
        assert "database" not in schema_str


@pytest.mark.anyio
async def test_gemini_provider_handles_text_fc_timeout_quota_auth_and_malformed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_secret = "AIzaSySuperSecretUnitTestKey99999"
    provider = GeminiProvider(
        api_key=fake_secret,
        model="gemini-2.5-flash",
        timeout_seconds=2.0,
    )

    async def fake_generate_text(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            candidates=[
                SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))
            ],
            function_calls=[],
            text="Tổng doanh thu hôm nay là 50,000 VND.",
        )

    provider._client.aio.models.generate_content = fake_generate_text  # type: ignore[method-assign]
    turn = await provider.generate_turn("Doanh thu?", timeout_seconds=2.0)
    assert turn.text == "Tổng doanh thu hôm nay là 50,000 VND."
    assert turn.function_calls == ()

    async def fake_generate_fc(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            candidates=[
                SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))
            ],
            function_calls=[
                SimpleNamespace(
                    name="get_sales_summary",
                    args={"start_date": "2026-11-18", "end_date": "2026-11-18"},
                )
            ],
            text=None,
        )

    provider._client.aio.models.generate_content = fake_generate_fc  # type: ignore[method-assign]
    fc_turn = await provider.generate_turn("Doanh thu ngày 18?", timeout_seconds=2.0)
    assert len(fc_turn.function_calls) == 1
    assert fc_turn.function_calls[0].name == "get_sales_summary"

    async def fake_timeout(**_kwargs: Any) -> Any:
        await asyncio.sleep(0.3)

    provider._client.aio.models.generate_content = fake_timeout  # type: ignore[method-assign]
    with pytest.raises(GeminiTimeoutError):
        await provider.generate_turn("Slow?", timeout_seconds=0.1)

    async def fake_quota(**_kwargs: Any) -> Any:
        raise genai_errors.APIError(429, {"error": {"message": "Quota exceeded"}})

    provider._client.aio.models.generate_content = fake_quota  # type: ignore[method-assign]
    with pytest.raises(GeminiQuotaExceededError):
        await provider.generate_turn("Quota?", timeout_seconds=2.0)

    async def fake_auth(**_kwargs: Any) -> Any:
        raise genai_errors.APIError(403, {"error": {"message": "Invalid key"}})

    provider._client.aio.models.generate_content = fake_auth  # type: ignore[method-assign]
    with pytest.raises(GeminiProviderError):
        await provider.generate_turn("Auth?", timeout_seconds=2.0)
    assert fake_secret not in caplog.text

    async def fake_empty(**_kwargs: Any) -> Any:
        return SimpleNamespace(candidates=[], function_calls=[], text=None)

    provider._client.aio.models.generate_content = fake_empty  # type: ignore[method-assign]
    with pytest.raises(GeminiProviderError):
        await provider.generate_turn("Empty?", timeout_seconds=2.0)


class _StubProvider:
    def __init__(self, turns: list[ProviderTurnResponse]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[str, Any]] = []
        self.open_sessions_during_calls: list[int] = []
        self.session_counter_ref: list[int] | None = None

    async def generate_turn(
        self, user_message: str, *, timeout_seconds: float
    ) -> ProviderTurnResponse:
        if self.session_counter_ref is not None:
            self.open_sessions_during_calls.append(self.session_counter_ref[0])
        self.calls.append(("generate_turn", user_message))
        return self._turns.pop(0)

    async def submit_tool_results(
        self,
        conversation_state: Any,
        tool_responses: tuple[ToolResponseItem, ...],
        *,
        timeout_seconds: float,
    ) -> ProviderTurnResponse:
        if self.session_counter_ref is not None:
            self.open_sessions_during_calls.append(self.session_counter_ref[0])
        self.calls.append(("submit_tool_results", tool_responses))
        return self._turns.pop(0)


@pytest.mark.anyio
async def test_orchestrator_hybrid_routing_and_no_db_session_during_gemini() -> None:
    sf = _make_sqlite_session_factory()
    admin_id, _ = _seed_admin_and_data(sf, with_sales=True, with_low_stock=True)
    principal = _load_principal(sf, admin_id)
    open_sessions = [0]

    @contextmanager
    def tracked_sf():
        open_sessions[0] += 1
        try:
            with sf() as session:
                yield session
        finally:
            open_sessions[0] -= 1

    stub = _StubProvider(
        [
            ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(
                        name="get_sales_summary",
                        arguments={
                            "start_date": "2026-11-18",
                            "end_date": "2026-11-18",
                        },
                    ),
                ),
                conversation_state=["turn1"],
            ),
            ProviderTurnResponse(
                text="Doanh thu ngày 2026-11-18 đạt 50,000 VND với 1 đơn hoàn thành.",
                function_calls=(),
                conversation_state=["turn2"],
            ),
        ]
    )
    stub.session_counter_ref = open_sessions

    orchestrator = AIOrchestrator(
        session_factory=tracked_sf,
        provider_factory=lambda: stub,
        gemini_timeout_seconds=10.0,
        clock_vn=lambda: datetime(2026, 11, 18, 12, 0),
    )

    # 1. Greeting -> 0 Gemini calls, 0 DB sessions
    b1 = bind_authenticated_request(principal, request_id="req-greet")
    r_greet = await orchestrator.handle_query(message="Xin chào!", bound=b1)
    assert r_greet.evidence == []
    assert r_greet.insufficient_data is False
    assert len(stub.calls) == 0

    # 2. Direct low-stock -> 0 Gemini calls, grounded evidence
    b2 = bind_authenticated_request(principal, request_id="req-low")
    r_low = await orchestrator.handle_query(message="Xem tồn kho thấp", bound=b2)
    assert len(stub.calls) == 0
    assert r_low.insufficient_data is False
    assert len(r_low.evidence) == 1
    assert "get_low_stock" in r_low.evidence[0].source
    assert "SKU-AI-001" in r_low.evidence[0].summary

    # 3. Gemini Function Calling -> DB closed during Gemini network turns
    b3 = bind_authenticated_request(principal, request_id="req-llm")
    r_llm = await orchestrator.handle_query(
        message="Phân tích doanh thu ngày 18/11 giúp tôi", bound=b3
    )
    assert len(stub.calls) == 2
    assert stub.open_sessions_during_calls == [0, 0]
    assert r_llm.insufficient_data is False
    assert len(r_llm.evidence) == 1
    assert "get_sales_summary" in r_llm.evidence[0].source
    assert "revenue_vnd=50000" in r_llm.evidence[0].summary


@pytest.mark.anyio
async def test_orchestrator_rejects_disallowed_tool_bad_args_and_empty_evidence() -> (
    None
):
    sf = _make_sqlite_session_factory()
    admin_id, _ = _seed_admin_and_data(sf, with_sales=False, with_low_stock=False)
    principal = _load_principal(sf, admin_id)

    # Disallowed tool -> 422 DomainValidationError
    bad_tool_provider = _StubProvider(
        [
            ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(
                        name="execute_sql", arguments={"query": "SELECT * FROM users"}
                    ),
                ),
            )
        ]
    )
    orch1 = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: bad_tool_provider,
        gemini_timeout_seconds=10.0,
    )
    with pytest.raises(DomainValidationError):
        await orch1.handle_query(
            message="Cho tôi xem danh sách user",
            bound=bind_authenticated_request(principal, request_id="req-bad-tool"),
        )

    # Invalid arguments -> 422 from AIToolExecutor
    bad_args_provider = _StubProvider(
        [
            ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(
                        name="get_top_products", arguments={"days": 999}
                    ),
                ),
            )
        ]
    )
    orch2 = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: bad_args_provider,
        gemini_timeout_seconds=10.0,
    )
    with pytest.raises(DomainValidationError):
        await orch2.handle_query(
            message="Top sản phẩm 999 ngày qua",
            bound=bind_authenticated_request(principal, request_id="req-bad-args"),
        )

    # Gemini text without tool call -> insufficient_data=True, evidence=[]
    no_tool_provider = _StubProvider(
        [
            ProviderTurnResponse(
                text="Doanh thu ước tính khoảng 100 triệu.", function_calls=()
            )
        ]
    )
    orch3 = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: no_tool_provider,
        gemini_timeout_seconds=10.0,
    )
    res_no_tool = await orch3.handle_query(
        message="Doanh thu quý này thế nào?",
        bound=bind_authenticated_request(principal, request_id="req-no-tool"),
    )
    assert res_no_tool.insufficient_data is True
    assert res_no_tool.evidence == []

    # Tool returns zero/empty data -> insufficient_data=True
    empty_sales_provider = _StubProvider(
        [
            ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(
                        name="get_sales_summary",
                        arguments={
                            "start_date": "2026-11-18",
                            "end_date": "2026-11-18",
                        },
                    ),
                ),
                conversation_state=["t1"],
            ),
            ProviderTurnResponse(
                text="Không có đơn hàng nào trong ngày 2026-11-18.",
                function_calls=(),
                conversation_state=["t2"],
            ),
        ]
    )
    orch4 = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: empty_sales_provider,
        gemini_timeout_seconds=10.0,
    )
    res_empty = await orch4.handle_query(
        message="Doanh thu ngày 18/11?",
        bound=bind_authenticated_request(principal, request_id="req-empty"),
    )
    assert res_empty.insufficient_data is True
    assert len(res_empty.evidence) == 1


class _InMemoryFakeRedis:
    """Minimal async Redis eval stub matching concurrency Lua semantics."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.user_locks: dict[str, str] = {}
        self.global_zset: dict[str, float] = {}

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        if self.fail:
            raise RedisConnectionError("Redis unreachable")
        user_key = args[0]
        if "ZREMRANGEBYSCORE" in script:
            token, _ttl, max_conc, now, expires = (
                args[2],
                int(args[3]),
                int(args[4]),
                float(args[5]),
                float(args[6]),
            )
            self.global_zset = {k: v for k, v in self.global_zset.items() if v > now}
            if user_key in self.user_locks:
                return 0
            if len(self.global_zset) >= max_conc:
                return -1
            self.user_locks[user_key] = token
            self.global_zset[token] = expires
            return 1
        # release script
        token = args[2]
        if self.user_locks.get(user_key) == token:
            del self.user_locks[user_key]
        self.global_zset.pop(token, None)
        return 1


@pytest.mark.anyio
async def test_ai_concurrency_guard_per_user_global_cap_and_fail_closed() -> None:
    fake_redis = _InMemoryFakeRedis()
    guard = RedisAIConcurrencyGuard(fake_redis, "retailops:test")  # type: ignore[arg-type]

    lease1 = await guard.acquire(user_id=1, max_concurrent=2, ttl_seconds=30, now=100.0)
    # Same user concurrent -> rejected (429)
    with pytest.raises(RateLimitedError):
        await guard.acquire(user_id=1, max_concurrent=2, ttl_seconds=30, now=100.0)

    lease2 = await guard.acquire(user_id=2, max_concurrent=2, ttl_seconds=30, now=100.0)
    # Global cap reached -> rejected (429)
    with pytest.raises(RateLimitedError):
        await guard.acquire(user_id=3, max_concurrent=2, ttl_seconds=30, now=100.0)

    await guard.release(lease1)
    await guard.release(lease2)
    # Released -> user 1 can acquire again
    lease3 = await guard.acquire(user_id=1, max_concurrent=2, ttl_seconds=30, now=101.0)
    await guard.release(lease3)

    # Redis failure -> fail-closed 503 DependencyUnavailableError
    failing_guard = RedisAIConcurrencyGuard(_InMemoryFakeRedis(fail=True), "ns")  # type: ignore[arg-type]
    with pytest.raises(DependencyUnavailableError):
        await failing_guard.acquire(user_id=1, max_concurrent=5, ttl_seconds=30)


@pytest.mark.anyio
async def test_ai_query_http_security_validation_and_redis_fail_closed() -> None:
    sf = _make_sqlite_session_factory()
    admin_id, staff_id = _seed_admin_and_data(sf, with_sales=True, with_low_stock=True)
    admin_principal = _load_principal(sf, admin_id)
    staff_principal = _load_principal(sf, staff_id)

    settings = _base_settings()
    app = create_app(settings)

    class _FakeLimiter:
        def __init__(self, *, allowed: bool = True, fail: bool = False) -> None:
            self.allowed = allowed
            self.fail = fail

        async def check(self, **_kwargs: Any) -> RateLimitResult:
            if self.fail:
                raise RedisConnectionError("Redis down")
            return RateLimitResult(allowed=self.allowed, count=1, retry_after=60)

    fake_limiter = _FakeLimiter()
    fake_guard = RedisAIConcurrencyGuard(_InMemoryFakeRedis(), "ns")  # type: ignore[arg-type]
    stub_provider = _StubProvider([])

    # 1. Anonymous (no auth override) -> 401
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_anon = await client.post("/api/v1/ai/query", json={"message": "Xin chào"})
        assert r_anon.status_code == 401

    # 2. STAFF -> 403
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_principal] = lambda: staff_principal
    app.dependency_overrides[get_rate_limiter] = lambda: fake_limiter
    app.dependency_overrides[get_ai_concurrency_guard] = lambda: fake_guard
    app.dependency_overrides[get_ai_session_factory] = lambda: sf
    app.dependency_overrides[get_ai_orchestrator] = lambda: AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: stub_provider,
        gemini_timeout_seconds=10.0,
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_staff = await client.post("/api/v1/ai/query", json={"message": "Xin chào"})
        assert r_staff.status_code == 403

    # 3. ADMIN -> extra fields (422), blank/long (422), Redis fail (503), 200 OK
    app.dependency_overrides[get_current_principal] = lambda: admin_principal
    app.dependency_overrides[get_bound_tool_request] = lambda: (
        bind_authenticated_request(
            admin_principal, request_id=uuid4().hex, settings=settings
        )
    )
    app.dependency_overrides[require_active_admin] = lambda: admin_principal.user
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_spoof = await client.post(
            "/api/v1/ai/query",
            json={"message": "Xin chào", "user_id": 999, "role": "ADMIN"},
        )
        assert r_spoof.status_code == 422

        r_blank = await client.post("/api/v1/ai/query", json={"message": "   "})
        assert r_blank.status_code == 422

        r_long = await client.post("/api/v1/ai/query", json={"message": "a" * 4001})
        assert r_long.status_code == 422

        r_ok = await client.post(
            "/api/v1/ai/query", json={"message": "Xem tồn kho thấp"}
        )
        assert r_ok.status_code == 200
        body = r_ok.json()
        assert set(body.keys()) == {"answer", "evidence", "insufficient_data"}
        assert body["insufficient_data"] is False
        assert len(body["evidence"]) == 1
        assert set(body["evidence"][0].keys()) == {"source", "period", "summary"}

        # Redis failure -> 503 fail-closed
        fake_limiter.fail = True
        r_redis_down = await client.post(
            "/api/v1/ai/query", json={"message": "Xem tồn kho thấp"}
        )
        assert r_redis_down.status_code == 503
