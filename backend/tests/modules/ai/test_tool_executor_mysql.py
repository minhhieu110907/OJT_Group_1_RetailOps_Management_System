"""Read-only smoke test on the dedicated MySQL integration fixture only."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai.tool_executor import bind_authenticated_request
from app.modules.auth.dependencies import CurrentPrincipal
from app.modules.auth.models import User, UserRole, UserStatus
from tests.integration.conftest import (
    integration_database_url,
    integration_engine,
    migrated_integration_engine,
)

pytestmark = pytest.mark.integration
__all__ = [
    "integration_database_url",
    "integration_engine",
    "migrated_integration_engine",
]


def test_real_read_services_leave_database_unmodified(migrated_integration_engine):
    with Session(migrated_integration_engine) as session:
        admin = session.scalar(
            select(User).where(
                User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
            )
        )
        if admin is None:
            pytest.skip("Dedicated test database has no authenticated ADMIN fixture")
        bound = bind_authenticated_request(
            CurrentPrincipal(user=admin, session_id=uuid4()),
            request_id="ai-mysql-smoke",
        )
        for tool_id in ("get_sales_summary", "get_top_products", "get_low_stock"):
            result = bound.executor.execute(
                session, tool_id=tool_id, arguments={}, context=bound.context
            )
            assert result.tool_id == tool_id
        assert not session.new and not session.dirty and not session.deleted
