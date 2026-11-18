"""Authenticated HTTP binding for the AI executor (no AI endpoint here)."""

from typing import Annotated
from uuid import uuid4

from fastapi import Depends

from app.modules.ai.tool_executor import BoundToolRequest, bind_authenticated_request
from app.modules.auth.dependencies import CurrentPrincipal, get_current_principal


def get_bound_tool_request(
    principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
) -> BoundToolRequest:
    """Bind a fresh budget to the live, server-authenticated request principal."""
    return bind_authenticated_request(principal, request_id=uuid4().hex)
