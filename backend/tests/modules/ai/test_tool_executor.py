from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import (
    DependencyUnavailableError,
    DomainValidationError,
    ForbiddenError,
)
from app.modules.ai.tool_executor import AIToolExecutor, ToolBudget, ToolContext
from app.modules.auth.models import UserRole, UserStatus


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.lookups = 0

    def get(self, model, actor_id):
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
    with pytest.raises(DomainValidationError):
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
    with pytest.raises(DomainValidationError):
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
    with pytest.raises(DomainValidationError):
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

    with pytest.raises(DependencyUnavailableError):
        executor(products=BrokenProducts()).execute(
            admin_session(),
            tool_id="get_slow_products",
            arguments={},
            context=context(),
        )
