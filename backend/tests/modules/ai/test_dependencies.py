"""Verify the AI binding is wired to the live Auth dependency."""

from inspect import signature
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

from fastapi.params import Depends

from app.modules.ai.dependencies import get_bound_tool_request
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal
from app.modules.auth.models import UserRole, UserStatus


def test_http_factory_depends_on_live_principal_and_is_request_scoped():
    parameter = signature(get_bound_tool_request).parameters["principal"]
    assert any(
        isinstance(item, Depends) and item.dependency is get_current_principal
        for item in get_args(parameter.annotation)
    )
    principal = CurrentPrincipal(
        user=SimpleNamespace(id=7, role=UserRole.ADMIN, status=UserStatus.ACTIVE),
        session_id=uuid4(),
    )
    first = get_bound_tool_request(principal)
    second = get_bound_tool_request(principal)
    assert first.context.actor_id == 7
    assert first.context.request_id != second.context.request_id
    assert first.budget is not second.budget
