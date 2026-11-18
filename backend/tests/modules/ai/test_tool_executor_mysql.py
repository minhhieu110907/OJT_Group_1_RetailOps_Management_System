"""Read-only smoke test on the dedicated MySQL integration fixture only."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event, select
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
    with Session(migrated_integration_engine) as session, session.begin():
        admin = session.scalar(
            select(User).where(
                User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE
            )
        )
        if admin is None:
            now = datetime.now(UTC).replace(tzinfo=None)
            admin = User(
                email_normalized=f"ai-integration-{uuid4().hex}@example.test",
                password_hash="integration-fixture-no-login",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                admin_slot=1,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            session.flush()
        writes = []

        def record_write(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().split(maxsplit=1)[0].upper() not in {
                "SELECT",
                "WITH",
            }:
                writes.append(statement.split(maxsplit=1)[0])

        event.listen(migrated_integration_engine, "before_cursor_execute", record_write)
        try:
            # The contract permits three calls per request; exercise all four
            # real services across two independently bound requests.
            for index, tool_id in enumerate(
                (
                    "get_sales_summary",
                    "get_top_products",
                    "get_slow_products",
                    "get_low_stock",
                )
            ):
                if index % 3 == 0:
                    bound = bind_authenticated_request(
                        CurrentPrincipal(user=admin, session_id=uuid4()),
                        request_id=f"ai-mysql-smoke-{index}",
                    )
                result = bound.executor.execute(
                    session, tool_id=tool_id, arguments={}, context=bound.context
                )
                assert result.tool_id == tool_id
        finally:
            event.remove(
                migrated_integration_engine, "before_cursor_execute", record_write
            )
        assert writes == []
        assert not session.new and not session.dirty and not session.deleted
        session.rollback()  # discard only the deterministic ADMIN fixture, if created
