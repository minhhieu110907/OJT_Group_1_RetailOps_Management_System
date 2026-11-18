import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    DependencyUnavailableError,
    DomainValidationError,
    ForbiddenError,
    RateLimitedError,
)
from app.modules.ai.tool_executor import (
    AIToolExecutor,
    ToolBudget,
    ToolContext,
    bind_authenticated_request,
)
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.auth.models import UserRole, UserStatus


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.lookups = 0

    def get(self, model, actor_id, **kwargs):
        self.lookups += 1
        return self.user if actor_id == self.user.id else None


def admin_session():
    return FakeSession(
        SimpleNamespace(id=7, role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    )


def context(actor_id=7):
    return ToolContext(actor_id=actor_id, actor_role="ADMIN", request_id="req-1")


def empty_sales():
    return SimpleNamespace(
        period_start=datetime(2026, 11, 18, tzinfo=UTC),
        period_end_exclusive=datetime(2026, 11, 19, tzinfo=UTC),
        revenue_vnd=0,
        completed_orders=0,
        cancelled_orders=0,
        aov_vnd=0,
    )


class Sales:
    def __init__(self, value=None):
        self.calls = 0
        self.value = value or empty_sales()

    def summary(self, session, *, period):
        self.calls += 1
        return self.value


class Products:
    def __init__(self, item=None):
        self.calls = 0
        self.item = item or SimpleNamespace(
            product_id=1, sku="SKU", name="Name", sold_units=1, revenue_vnd=10
        )

    def top(self, session, *, period, page, page_size):
        self.calls += 1
        return SimpleNamespace(items=(self.item,), total=1)

    def slow(self, session, *, as_of_utc, page, page_size):
        self.calls += 1
        return SimpleNamespace(items=(), total=0)


class Inventory:
    def get_low_stock(self, **kwargs):
        return SimpleNamespace(items=(), total=0)


def executor(*, budget=None, verifier=None, clock=None, sales=None, products=None):
    return AIToolExecutor(
        sales_service=sales or Sales(),
        product_service=products or Products(),
        inventory_service=Inventory(),
        budget=budget,
        clock=clock or (lambda: datetime(2026, 11, 18, 12, tzinfo=UTC)),
        context_verifier=verifier or (lambda received: received == context()),
    )


def bound(*, user=None, sales=None, products=None, clock=None):
    user = user or admin_session().user
    return bind_authenticated_request(
        CurrentPrincipal(user=user, session_id=uuid4()),
        request_id="req-1",
        sales_service=sales or Sales(),
        product_service=products or Products(),
        inventory_service=Inventory(),
        clock=clock or (lambda: datetime(2026, 11, 18, 12, tzinfo=UTC)),
    )


def test_bound_budget_uses_central_settings_and_preserves_contract_ceiling():
    settings = Settings(
        _env_file=None,
        db_host="127.0.0.1",
        db_name="unit_test_only",
        db_user="unit_test_user",
        db_password="not-a-real-password",
        ai_request_deadline_seconds=5,
        ai_max_tool_calls=2,
        ai_max_tool_output_bytes=1024,
    )
    principal = CurrentPrincipal(user=admin_session().user, session_id=uuid4())
    request = bind_authenticated_request(
        principal, request_id="configured", settings=settings
    )
    assert (request.budget.deadline_seconds, request.budget.max_calls) == (5, 2)
    assert request.budget.max_output_bytes == 1024
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            db_host="127.0.0.1",
            db_name="unit_test_only",
            db_user="unit_test_user",
            db_password="not-a-real-password",
            ai_max_tool_calls=4,
        )


def test_admin_and_identity_spoofing_are_verified_before_dispatch():
    sales = Sales()
    tool = executor(sales=sales)
    assert (
        tool.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={},
            context=context(),
        ).data["revenue_vnd"]
        == 0
    )
    with pytest.raises(ForbiddenError):
        tool.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={},
            context=context(8),
        )
    assert sales.calls == 1


def test_staff_is_rejected_before_business_service():
    session = FakeSession(
        SimpleNamespace(id=7, role=UserRole.STAFF, status=UserStatus.ACTIVE)
    )
    sales = Sales()
    with pytest.raises(ForbiddenError):
        executor(sales=sales).execute(
            session, tool_id="get_sales_summary", arguments={}, context=context()
        )
    assert sales.calls == 0


@pytest.mark.parametrize(
    "tool_id, arguments",
    [
        ("unknown", {}),
        ("get_top_products", {"limit": True}),
        ("get_low_stock", {"limit": 21}),
        ("get_slow_products", {"sql": "DROP TABLE users"}),
    ],
)
def test_allowlist_and_arguments_are_strict(tool_id, arguments):
    with pytest.raises(DomainValidationError):
        executor().execute(
            admin_session(), tool_id=tool_id, arguments=arguments, context=context()
        )


def test_date_defaults_and_timezone_period_are_passed_to_service():
    sales = Sales()
    tool = executor(sales=sales)
    result = tool.execute(
        admin_session(), tool_id="get_sales_summary", arguments={}, context=context()
    )
    assert result.source_period == "2026-11-17T17:00:00+00:00/2026-11-18T17:00:00+00:00"


def test_budget_is_shared_and_counts_failed_calls():
    budget = ToolBudget()
    tool = executor(budget=budget)
    for _ in range(3):
        tool.execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=context(),
        )
    with pytest.raises(RateLimitedError):
        tool.execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=context(),
        )
    assert budget.calls == 3


def test_output_budget_and_sensitive_fields_are_enforced():
    item = SimpleNamespace(
        product_id=1,
        sku="SKU",
        name="Name",
        sold_units=1,
        revenue_vnd=10,
        quantity=2,
        cost_price=999,
    )
    tool = executor(
        products=Products(item), budget=ToolBudget(output_bytes=32 * 1024 - 1)
    )
    with pytest.raises(RateLimitedError):
        tool.execute(
            admin_session(), tool_id="get_top_products", arguments={}, context=context()
        )
    result = executor(products=Products(item)).execute(
        admin_session(), tool_id="get_top_products", arguments={}, context=context()
    )
    assert "cost_price" not in result.data["items"][0]


def test_deadline_is_checked_after_adapter_returns():
    budget = ToolBudget(started_at=0.0)
    budget.started_at = __import__("time").monotonic() - 16
    with pytest.raises(DependencyUnavailableError):
        executor(budget=budget).execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=context(),
        )


def test_dependency_failure_is_not_an_empty_result():
    class BrokenProducts(Products):
        def slow(self, **kwargs):
            raise RuntimeError("database down")

    with pytest.raises(DependencyUnavailableError) as caught:
        executor(products=BrokenProducts()).execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=context(),
        )
    assert "database down" not in caught.value.message


def test_bound_factory_rejects_cloned_modified_and_other_request_context():
    first, second = bound(), bound()
    sales = Sales()
    first = bound(sales=sales)
    for supplied in (
        replace(first.context),
        replace(first.context, actor_id=8),
        replace(first.context, actor_role="STAFF"),
        second.context,
    ):
        with pytest.raises(ForbiddenError):
            first.executor.execute(
                admin_session(),
                tool_id="get_sales_summary",
                arguments={},
                context=supplied,
            )
    assert first.budget.calls == 0
    assert sales.calls == 0
    first.executor.execute(
        admin_session(),
        tool_id="get_sales_summary",
        arguments={},
        context=first.context,
    )
    assert first.budget.calls == 1
    assert second.budget.calls == 0


def test_in_place_context_tampering_is_rejected():
    request = bound()
    object.__setattr__(request.context, "actor_id", 8)
    with pytest.raises(ForbiddenError):
        request.executor.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={},
            context=request.context,
        )
    assert request.budget.calls == 0


def test_bound_factory_rejects_staff_before_service():
    staff = SimpleNamespace(id=7, role=UserRole.STAFF, status=UserStatus.ACTIVE)
    request = bound(user=staff)
    with pytest.raises(ForbiddenError):
        request.executor.execute(
            FakeSession(staff),
            tool_id="get_sales_summary",
            arguments={},
            context=request.context,
        )
    assert request.budget.calls == 0


def test_invalid_model_calls_consume_shared_quota():
    request = bound()
    for _ in range(3):
        with pytest.raises(DomainValidationError):
            request.executor.execute(
                admin_session(),
                tool_id="unknown",
                arguments={},
                context=request.context,
            )
    with pytest.raises(RateLimitedError):
        request.executor.execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=request.context,
        )
    assert request.budget.calls == 3


def test_three_valid_calls_share_one_bound_request_budget():
    request = bound()
    for tool_id in ("get_sales_summary", "get_top_products", "get_low_stock"):
        request.executor.execute(
            admin_session(), tool_id=tool_id, arguments={}, context=request.context
        )
    assert request.budget.calls == 3
    with pytest.raises(RateLimitedError):
        request.executor.execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=request.context,
        )


def test_concurrent_tool_calls_cannot_overspend_request_budget():
    request = bound()

    def invoke(_):
        try:
            request.executor.execute(
                admin_session(),
                tool_id="get_slow_products",
                arguments={},
                context=request.context,
            )
            return "ok"
        except RateLimitedError:
            return "limited"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(invoke, range(4)))
    assert sorted(outcomes) == ["limited", "ok", "ok", "ok"]
    assert request.budget.calls == 3


@pytest.mark.parametrize(
    "value", [None, "20261118", "2026-1-18", "2026-02-30", 20261118]
)
def test_sales_dates_reject_null_noncanonical_and_invalid_values(value):
    request = bound()
    with pytest.raises(DomainValidationError):
        request.executor.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={"start_date": value},
            context=request.context,
        )


def test_single_start_date_exceeding_ninety_days_is_rejected():
    request = bound()
    with pytest.raises(DomainValidationError):
        request.executor.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={"start_date": "2026-08-01"},
            context=request.context,
        )


def test_vietnam_today_is_not_utc_today_at_midnight_boundary():
    request = bound(clock=lambda: datetime(2026, 11, 17, 18, tzinfo=UTC))
    result = request.executor.execute(
        admin_session(),
        tool_id="get_sales_summary",
        arguments={},
        context=request.context,
    )
    assert result.source_period == "2026-11-17T17:00:00+00:00/2026-11-18T17:00:00+00:00"


def test_malformed_required_output_and_optional_fields_fail_closed():
    for item in (
        SimpleNamespace(product_id=1, sku="x", name="n", sold_units=1),
        SimpleNamespace(
            product_id=1, sku="x", name="n", sold_units=1, revenue_vnd=1, quantity=-1
        ),
        SimpleNamespace(
            product_id=1,
            sku="x",
            name="n",
            sold_units=1,
            revenue_vnd=1,
            first_stocked_at="not-a-date",
        ),
    ):
        request = bound(products=Products(item))
        with pytest.raises(DependencyUnavailableError):
            request.executor.execute(
                admin_session(),
                tool_id="get_top_products",
                arguments={},
                context=request.context,
            )


def test_output_is_serialized_utc_and_byte_count_matches_handoff(caplog):
    item = SimpleNamespace(
        product_id=1,
        sku="SKU",
        name="Cà phê",
        sold_units=1,
        revenue_vnd=10,
        quantity=None,
        first_stocked_at=datetime(2026, 11, 18, 7, tzinfo=UTC),
        cost_price=99,
    )
    request = bound(products=Products(item))
    with caplog.at_level("INFO"):
        result = request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={},
            context=request.context,
        )
    assert result.data["items"][0]["first_stocked_at"] == "2026-11-18T07:00:00Z"
    assert "cost_price" not in result.data["items"][0]
    payload = json.dumps(
        {
            "tool_id": result.tool_id,
            "data": result.data,
            "source_period": result.source_period,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert request.budget.output_bytes == len(payload)
    assert any(record.output_bytes == len(payload) for record in caplog.records)


def test_deadline_after_service_query_is_safe_error():
    request = bound()

    class ExpiringProducts(Products):
        def slow(self, *args, **kwargs):
            request.budget.started_at = time.monotonic() - 16
            return super().slow(*args, **kwargs)

    request = bound(products=ExpiringProducts())
    with pytest.raises(DependencyUnavailableError):
        request.executor.execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=request.context,
        )
    assert request.budget.calls == 1


def test_expired_request_never_starts_database_query():
    request = bound()
    request.budget.started_at = time.monotonic() - 16
    session = admin_session()
    with pytest.raises(DependencyUnavailableError) as caught:
        request.executor.execute(
            session, tool_id="get_slow_products", arguments={}, context=request.context
        )
    assert session.lookups == 0
    assert request.budget.calls == 0
    assert caught.value.status_code == 503


def test_error_http_semantics_are_distinct():
    request = bound()
    with pytest.raises(DomainValidationError) as invalid:
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={"days": True},
            context=request.context,
        )
    assert invalid.value.status_code == 422
    with pytest.raises(ForbiddenError) as forbidden:
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={},
            context=replace(request.context),
        )
    assert forbidden.value.status_code == 403
    request.budget.calls = 3
    with pytest.raises(RateLimitedError) as quota:
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={},
            context=request.context,
        )
    assert quota.value.status_code == 429


def test_malformed_sales_dto_fails_instead_of_returning_zero():
    value = SimpleNamespace(
        period_start=datetime(2026, 11, 18, tzinfo=UTC),
        period_end_exclusive=datetime(2026, 11, 19, tzinfo=UTC),
        revenue_vnd=-1,
        completed_orders=0,
        cancelled_orders=0,
        aov_vnd=0,
    )
    request = bound(sales=Sales(value))
    with pytest.raises(DependencyUnavailableError):
        request.executor.execute(
            admin_session(),
            tool_id="get_sales_summary",
            arguments={},
            context=request.context,
        )


def test_page_larger_than_requested_limit_is_rejected():
    class Oversized(Products):
        def top(self, *args, **kwargs):
            return SimpleNamespace(items=(self.item,) * 6, total=6)

    request = bound(products=Oversized())
    with pytest.raises(DependencyUnavailableError):
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={"limit": 5},
            context=request.context,
        )


def test_real_cumulative_utf8_output_limit():
    item = SimpleNamespace(
        product_id=1, sku="SKU", name="é" * 6000, sold_units=1, revenue_vnd=10
    )
    request = bound(products=Products(item))
    for _ in range(2):
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={},
            context=request.context,
        )
    assert request.budget.output_bytes > 24000
    with pytest.raises(RateLimitedError):
        request.executor.execute(
            admin_session(),
            tool_id="get_top_products",
            arguments={},
            context=request.context,
        )
    assert request.budget.calls == 3


def test_strict_result_models_track_frozen_json_contract():
    from app.modules.ai.tool_executor import (
        _LowStockItem,
        _LowStockPage,
        _ProductItem,
        _ProductPage,
        _SalesData,
    )

    schema_path = (
        Path(__file__).resolve().parents[4] / "contracts" / "ai_tool_schemas.json"
    )
    schemas = json.loads(schema_path.read_text(encoding="utf-8"))["tools"]
    models = {
        "get_sales_summary": _SalesData,
        "get_top_products": _ProductPage,
        "get_slow_products": _ProductPage,
        "get_low_stock": _LowStockPage,
    }
    for tool_id, model in models.items():
        output = schemas[tool_id]["output"]
        assert output["additionalProperties"] is False
        assert set(output["required"]) == {"tool_id", "data", "source_period"}
        data_schema = output["properties"]["data"]
        assert data_schema["additionalProperties"] is False
        assert set(model.model_fields) == set(data_schema["properties"])
        assert set(data_schema["required"]) == {
            name for name, field in model.model_fields.items() if field.is_required()
        }
        if "items" in data_schema["properties"]:
            item_schema = data_schema["properties"]["items"]["items"]
            item_model = _LowStockItem if tool_id == "get_low_stock" else _ProductItem
            assert item_schema["additionalProperties"] is False
            assert set(item_model.model_fields) == set(item_schema["properties"])
            assert set(item_schema["required"]) == {
                name
                for name, field in item_model.model_fields.items()
                if field.is_required()
            }
