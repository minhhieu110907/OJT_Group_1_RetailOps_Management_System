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
    build_system_instruction,
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
        dbapi_conn.create_function("CHAR_LENGTH", 1, len)

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
            id=1,
            email_normalized="admin@retailops.local",
            password_hash="hash",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            admin_slot=1,
            created_at=now,
            updated_at=now,
        )
        staff = User(
            id=2,
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
            cat = Category(
                id=1,
                name="Beverages",
                description="Drinks",
                status=CatalogStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session.add(cat)
            session.flush()
            prod = Product(
                id=1,
                category_id=cat.id,
                sku="SKU-AI-001",
                name="Green Tea",
                status=CatalogStatus.ACTIVE,
                sale_price_vnd=25000,
                created_at=now,
                updated_at=now,
            )
            session.add(prod)
            session.flush()
            session.add(
                Inventory(
                    product_id=prod.id,
                    quantity=2 if with_low_stock else 50,
                    stock_version=1,
                    first_stocked_at=now,
                    updated_at=now,
                )
            )
            if with_sales:
                order = Order(
                    id=1,
                    status=OrderStatus.COMPLETED,
                    total_vnd=50000,
                    created_by=admin.id,
                    sold_at=datetime(2026, 11, 18, 8, 0),
                )
                session.add(order)
                session.flush()
                session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        sku_snapshot=prod.sku,
                        product_name_snapshot=prod.name,
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
    import json

    from app.core.config import PROJECT_ROOT

    contract = json.loads(
        (PROJECT_ROOT / "contracts" / "ai_tool_schemas.json").read_text(
            encoding="utf-8"
        )
    )
    decls = build_gemini_function_declarations()
    assert len(decls) == 4
    assert tuple(d.name for d in decls) == APPROVED_TOOL_NAMES
    for decl in decls:
        assert decl.name is not None
        assert decl.parameters_json_schema == contract["tools"][decl.name]["input"]
        schema_str = str(decl.parameters_json_schema).lower()
        assert "sql" not in schema_str
        assert "user_id" not in schema_str
        assert "database" not in schema_str

    slow_decl = next(d for d in decls if d.name == "get_slow_products")
    assert "days" not in (slow_decl.parameters_json_schema or {}).get("properties", {})
    assert "days" not in (slow_decl.description or "").lower()


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

    from app.db.session import get_db_session

    def _override_db():
        with sf() as session:
            yield session

    # 1. Anonymous (no auth override) -> 401
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_rate_limiter] = lambda: fake_limiter
    app.dependency_overrides[get_ai_concurrency_guard] = lambda: fake_guard
    app.dependency_overrides[get_ai_session_factory] = lambda: sf
    app.dependency_overrides[get_ai_orchestrator] = lambda: AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: stub_provider,
        gemini_timeout_seconds=10.0,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r_anon = await client.post("/api/v1/ai/query", json={"message": "Xin chào"})
        assert r_anon.status_code == 401

    # 2. STAFF -> 403
    app.dependency_overrides[get_current_principal] = lambda: staff_principal
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


@pytest.mark.anyio
async def test_orchestrator_enforces_global_15s_deadline_across_all_paths() -> None:
    sf = _make_sqlite_session_factory()
    admin_id, _ = _seed_admin_and_data(sf, with_sales=True, with_low_stock=True)
    principal = _load_principal(sf, admin_id)

    # 1. Expired before greeting / direct -> raises DependencyUnavailableError (503)
    orch_basic = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: _StubProvider([]),
        gemini_timeout_seconds=10.0,
    )
    b_greet = bind_authenticated_request(principal, request_id="req-exp-greet")
    b_greet.budget.started_at -= b_greet.budget.deadline_seconds + 1.0
    with pytest.raises(DependencyUnavailableError):
        await orch_basic.handle_query(message="Xin chào", bound=b_greet)

    b_direct = bind_authenticated_request(principal, request_id="req-exp-direct")
    b_direct.budget.started_at -= b_direct.budget.deadline_seconds + 1.0
    with pytest.raises(DependencyUnavailableError):
        await orch_basic.handle_query(message="Xem tồn kho thấp", bound=b_direct)

    # 2. Gemini first turn exceeds deadline -> fails before calling Executor
    class _ExpiringFirstTurnProvider:
        def __init__(self, bound_ref) -> None:
            self.bound = bound_ref
            self.timeouts_seen: list[float] = []

        async def generate_turn(
            self, user_message: str, *, timeout_seconds: float
        ) -> ProviderTurnResponse:
            self.timeouts_seen.append(timeout_seconds)
            self.bound.budget.started_at -= self.bound.budget.deadline_seconds + 1.0
            return ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(name="get_low_stock", arguments={"limit": 5}),
                ),
                conversation_state=["t1"],
            )

        async def submit_tool_results(self, *_args: Any, **_kwargs: Any):
            raise AssertionError("Should not reach submit_tool_results after expiry")

    b_t1 = bind_authenticated_request(principal, request_id="req-exp-t1")
    p_t1 = _ExpiringFirstTurnProvider(b_t1)
    orch_t1 = AIOrchestrator(
        session_factory=sf, provider_factory=lambda: p_t1, gemini_timeout_seconds=10.0
    )
    with pytest.raises(DependencyUnavailableError):
        await orch_t1.handle_query(message="Phân tích tồn kho", bound=b_t1)
    assert b_t1.budget.calls == 0

    # 3. Tool execution exhausts budget -> submit_tool_results is NOT called
    b_tool = bind_authenticated_request(principal, request_id="req-exp-tool")
    submit_called = False

    class _ToolExpiresBudgetProvider:
        async def generate_turn(
            self, user_message: str, *, timeout_seconds: float
        ) -> ProviderTurnResponse:
            assert timeout_seconds <= 10.0
            return ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(name="get_low_stock", arguments={"limit": 5}),
                ),
                conversation_state=["t1"],
            )

        async def submit_tool_results(self, *_args: Any, **_kwargs: Any):
            nonlocal submit_called
            submit_called = True
            raise AssertionError("submit_tool_results must not run after deadline")

    @contextmanager
    def expiring_sf():
        with sf() as s:
            yield s
        b_tool.budget.started_at -= b_tool.budget.deadline_seconds + 1.0

    orch_tool = AIOrchestrator(
        session_factory=expiring_sf,
        provider_factory=_ToolExpiresBudgetProvider,
        gemini_timeout_seconds=10.0,
    )
    with pytest.raises(DependencyUnavailableError):
        await orch_tool.handle_query(message="Phân tích tồn kho", bound=b_tool)
    assert not submit_called

    # 4. Final Gemini turn exceeds deadline -> does NOT return AIAskResponse (200)
    b_final = bind_authenticated_request(principal, request_id="req-exp-final")
    b_final.budget.started_at -= 12.0  # only ~3s remaining

    class _ExpiringFinalTurnProvider:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        async def generate_turn(
            self, user_message: str, *, timeout_seconds: float
        ) -> ProviderTurnResponse:
            self.timeouts.append(timeout_seconds)
            assert timeout_seconds <= 3.5
            return ProviderTurnResponse(
                text=None,
                function_calls=(
                    ProviderFunctionCall(name="get_low_stock", arguments={"limit": 5}),
                ),
                conversation_state=["t1"],
            )

        async def submit_tool_results(
            self,
            conversation_state: Any,
            tool_responses: tuple[ToolResponseItem, ...],
            *,
            timeout_seconds: float,
        ) -> ProviderTurnResponse:
            self.timeouts.append(timeout_seconds)
            assert timeout_seconds <= 3.5
            b_final.budget.started_at -= b_final.budget.deadline_seconds + 1.0
            return ProviderTurnResponse(
                text="Tồn kho thấp gồm 1 sản phẩm.",
                function_calls=(),
                conversation_state=["t2"],
            )

    p_final = _ExpiringFinalTurnProvider()
    orch_final = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: p_final,
        gemini_timeout_seconds=10.0,
    )
    with pytest.raises(DependencyUnavailableError):
        await orch_final.handle_query(message="Phân tích tồn kho", bound=b_final)


def test_build_system_instruction_embeds_vietnam_date_context() -> None:
    fixed_now = datetime(2026, 11, 22, 9, 30)
    instruction = build_system_instruction(fixed_now)
    assert "2026-11-22" in instruction
    assert "22/11/2026" in instruction
    assert "2026-11-21" in instruction  # yesterday
    assert "2026-11-16" in instruction  # 7-day start (inclusive) and Monday of week
    assert "2026-10-24" in instruction  # 30-day start (inclusive)
    assert "2026-11-01" in instruction  # month start

    provider = GeminiProvider(
        api_key="AIzaSyFakeKeyForDateContextTest1234",
        model="gemini-2.5-flash",
        timeout_seconds=5.0,
        clock_vn=lambda: fixed_now,
    )
    cfg = provider._build_config()
    assert isinstance(cfg.system_instruction, str)
    assert "2026-11-22" in cfg.system_instruction


@pytest.mark.anyio
async def test_orchestrator_fast_path_admin_queries_zero_gemini_calls() -> None:
    sf = _make_sqlite_session_factory()
    admin_id, _ = _seed_admin_and_data(sf, with_sales=True, with_low_stock=True)
    principal = _load_principal(sf, admin_id)
    stub = _StubProvider([])

    fixed_vn = datetime(2026, 11, 18, 15, 0)
    fixed_utc = datetime(2026, 11, 18, 8, 0)

    orchestrator = AIOrchestrator(
        session_factory=sf,
        provider_factory=lambda: stub,
        gemini_timeout_seconds=10.0,
        clock_vn=lambda: fixed_vn,
    )

    def _bound(req_id: str):
        return bind_authenticated_request(
            principal, request_id=req_id, clock=lambda: fixed_utc
        )

    # 1. Combined sales + products for last 7 days (2 direct calls, 0 Gemini calls)
    res_combined = await orchestrator.handle_query(
        message="Doanh thu và Sản phẩm 7 ngày gần nhất của cửa hàng",
        bound=_bound("req-fp-combined"),
    )
    assert len(stub.calls) == 0
    assert res_combined.insufficient_data is False
    assert len(res_combined.evidence) == 2
    assert "get_sales_summary" in res_combined.evidence[0].source
    assert res_combined.evidence[0].period == "12/11/2026 - 18/11/2026"
    assert "revenue_vnd=50000" in res_combined.evidence[0].summary
    assert "get_top_products" in res_combined.evidence[1].source
    assert res_combined.evidence[1].period == "12/11/2026 - 18/11/2026"
    assert "SKU-AI-001" in res_combined.answer

    # 2. UI suggested prompt #1: 7-day sales summary
    res_sales_7d = await orchestrator.handle_query(
        message="Doanh thu và số đơn hoàn tất 7 ngày gần nhất như thế nào?",
        bound=_bound("req-fp-sales-7d"),
    )
    assert len(stub.calls) == 0
    assert res_sales_7d.insufficient_data is False
    assert len(res_sales_7d.evidence) == 1
    assert res_sales_7d.evidence[0].period == "12/11/2026 - 18/11/2026"

    # 3. UI suggested prompt #2: Top products 30 days
    res_top_30d = await orchestrator.handle_query(
        message="Những sản phẩm nào bán chạy nhất trong 30 ngày qua?",
        bound=_bound("req-fp-top-30d"),
    )
    assert len(stub.calls) == 0
    assert res_top_30d.insufficient_data is False
    assert "get_top_products" in res_top_30d.evidence[0].source
    assert res_top_30d.evidence[0].period == "20/10/2026 - 18/11/2026"

    # 4. UI suggested prompt #4: Slow products
    res_slow = await orchestrator.handle_query(
        message="Sản phẩm nào bán chậm cần xem xét kế hoạch nhập hàng?",
        bound=_bound("req-fp-slow"),
    )
    assert len(stub.calls) == 0
    assert len(res_slow.evidence) == 1
    assert "get_slow_products" in res_slow.evidence[0].source

    # 5. Yesterday / this week / this month sales
    res_yday = await orchestrator.handle_query(
        message="Doanh thu hôm qua thế nào?",
        bound=_bound("req-fp-yday"),
    )
    assert len(stub.calls) == 0
    assert res_yday.evidence[0].period == "17/11/2026"

    res_month = await orchestrator.handle_query(
        message="Doanh thu tháng này",
        bound=_bound("req-fp-month"),
    )
    assert len(stub.calls) == 0
    assert res_month.evidence[0].period == "01/11/2026 - 18/11/2026"

    # 6. Reorder advisor natural variants (0 Gemini calls)
    res_reorder_user = await orchestrator.handle_query(
        message="Sản phẩm nào cần nhập thêm",
        bound=_bound("req-reorder-user"),
    )
    assert len(stub.calls) == 0
    assert res_reorder_user.insufficient_data is False
    assert len(res_reorder_user.evidence) >= 1
    assert any("get_low_stock" in ev.source for ev in res_reorder_user.evidence)
    assert "SKU-AI-001" in res_reorder_user.answer

    res_reorder_short = await orchestrator.handle_query(
        message="cần nhập thêm",
        bound=_bound("req-reorder-short"),
    )
    assert len(stub.calls) == 0
    assert res_reorder_short.insufficient_data is False

    # 7. Low stock fast-path natural variants (0 Gemini calls)
    res_low_stock = await orchestrator.handle_query(
        message="Sản phẩm nào sắp hết",
        bound=_bound("req-low-stock-variant"),
    )
    assert len(stub.calls) == 0
    assert len(res_low_stock.evidence) == 1
    assert "get_low_stock" in res_low_stock.evidence[0].source


def test_fast_path_superlative_and_top_n_time_unit_queries() -> None:
    """Verify 'nhất' superlatives and 'top N sản phẩm ... trong <time unit>' routing."""
    from zoneinfo import ZoneInfo

    from app.modules.ai.orchestrator import _match_direct_tools, _normalize_text

    fixed_vn = datetime(2026, 11, 22, 10, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    def match(msg: str):
        return _match_direct_tools(_normalize_text(msg), now_vn=fixed_vn)

    # Top N sản phẩm + various time units (ngày, tuần, tháng, tuần/tháng này & qua)
    assert match("Top 5 sản phẩm trong 7 ngày") == [
        ("get_top_products", {"days": 7, "limit": 5})
    ]
    assert match("Top 3 sản phẩm bán chạy nhất trong 2 tuần") == [
        ("get_top_products", {"days": 14, "limit": 3})
    ]
    assert match("Top 10 sản phẩm trong 1 tháng") == [
        ("get_top_products", {"days": 30, "limit": 10})
    ]
    assert match("Top 5 sản phẩm bán tốt nhất trong 3 tháng qua") == [
        ("get_top_products", {"days": 90, "limit": 5})
    ]
    assert match("Top 4 sản phẩm bán nhiều nhất tuần qua") == [
        ("get_top_products", {"days": 7, "limit": 4})
    ]
    assert match("Top 6 sản phẩm mua nhiều nhất tháng qua") == [
        ("get_top_products", {"days": 30, "limit": 6})
    ]
    assert match("Top 3 sản phẩm doanh thu cao nhất tháng này") == [
        ("get_top_products", {"days": 22, "limit": 3})
    ]
    assert match("3 sản phẩm bán chạy nhất 14 ngày gần nhất") == [
        ("get_top_products", {"days": 14, "limit": 3})
    ]
    assert match("Sản phẩm nào bán được nhiều nhất?") == [
        ("get_top_products", {"days": 7, "limit": 5})
    ]
    assert match("Sản phẩm doanh thu cao nhất trong 1 tuần") == [
        ("get_top_products", {"days": 7, "limit": 5})
    ]

    # Superlative slow-moving products
    assert match("Top 5 sản phẩm bán chậm nhất") == [
        ("get_slow_products", {"limit": 5})
    ]
    assert match("Sản phẩm nào bán ế nhất?") == [("get_slow_products", {"limit": 10})]
    assert match("3 sản phẩm tồn lâu nhất") == [("get_slow_products", {"limit": 3})]

    # Superlative low-stock products
    assert match("Top 5 sản phẩm tồn kho thấp nhất") == [
        ("get_low_stock", {"limit": 5})
    ]
    assert match("Sản phẩm nào còn ít nhất?") == [("get_low_stock", {"limit": 10})]
    assert match("Top 15 sản phẩm tồn ít nhất") == [("get_low_stock", {"limit": 15})]

    # Sales + relative/calendar periods + new sales keywords & overview
    assert match("Doanh thu 1 tháng gần nhất") == [
        ("get_sales_summary", {"start_date": "2026-10-24", "end_date": "2026-11-22"})
    ]
    assert match("Doanh số tuần trước") == [
        ("get_sales_summary", {"start_date": "2026-11-09", "end_date": "2026-11-15"})
    ]
    assert match("Doanh thu tháng trước") == [
        ("get_sales_summary", {"start_date": "2026-10-01", "end_date": "2026-10-31"})
    ]
    assert match("Số đơn hàng hôm nay") == [
        ("get_sales_summary", {"start_date": "2026-11-22", "end_date": "2026-11-22"})
    ]
    assert match("Xem doanh thu") == [
        ("get_sales_summary", {"start_date": "2026-11-22", "end_date": "2026-11-22"})
    ]
    assert match("Tình hình bán hàng nửa tháng qua") == [
        ("get_sales_summary", {"start_date": "2026-11-08", "end_date": "2026-11-22"}),
        ("get_top_products", {"days": 15, "limit": 5}),
    ]
    assert match("Doanh thu và top 3 sản phẩm bán chạy nhất 1 tháng qua") == [
        ("get_sales_summary", {"start_date": "2026-10-24", "end_date": "2026-11-22"}),
        ("get_top_products", {"days": 30, "limit": 3}),
    ]
    assert match("Mặt hàng nào chạy nhất?") == [
        ("get_top_products", {"days": 7, "limit": 5})
    ]
    assert match("Hàng tồn đọng") == [("get_slow_products", {"limit": 10})]
    assert match("Cảnh báo tồn kho") == [("get_low_stock", {"limit": 10})]

    # Guards: out-of-range period/limit, explicit month, unsupported sales queries
    assert match("Top 5 sản phẩm bán chạy nhất trong 6 tháng") is None
    assert match("Top 50 sản phẩm bán chạy nhất 7 ngày") is None
    assert match("Doanh thu tháng 10") is None
    assert match("Ngày nào doanh thu cao nhất tuần này?") is None
    assert match("So sánh doanh thu tuần này và tuần trước") is None
    assert match("Top 5 sản phẩm bán chạy tháng trước") is None
