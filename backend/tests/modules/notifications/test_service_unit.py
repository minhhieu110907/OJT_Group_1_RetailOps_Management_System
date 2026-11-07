"""Unit tests (no DB) for NotificationService, schemas, and transaction invariants."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.modules.notifications.models import AdminNotification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    EmptyPatchRequest,
    NotificationRead,
)
from app.modules.notifications.service import NotificationService

FORBIDDEN_SESSION_METHODS = frozenset(
    {"commit", "rollback", "close", "begin", "begin_nested"}
)


class GuardedFakeSession:
    """Fake Session that fails if any transaction boundary method is called."""

    def __getattr__(self, name: str) -> object:
        if name in FORBIDDEN_SESSION_METHODS:
            raise AssertionError(
                f"Forbidden transaction method called on Session: {name}()"
            )
        raise AttributeError(name)


class FakeNotificationRepository(NotificationRepository):
    """In-memory repository double preserving NotificationRepository contract."""

    def __init__(self) -> None:
        self._rows: list[AdminNotification] = []
        self._next_id = 1

    def add_if_absent(
        self,
        session: object,
        admin_user_id: int,
        approval_request_id: int,
        created_at: datetime,
    ) -> AdminNotification:
        existing = self.find_by_approval_request_id(session, approval_request_id)
        if existing is not None:
            return existing
        row = AdminNotification(
            id=self._next_id,
            admin_user_id=admin_user_id,
            approval_request_id=approval_request_id,
            created_at=created_at,
            read_at=None,
        )
        self._next_id += 1
        self._rows.append(row)
        return row

    def find_by_approval_request_id(
        self,
        session: object,
        approval_request_id: int,
    ) -> AdminNotification | None:
        for row in self._rows:
            if row.approval_request_id == approval_request_id:
                return row
        return None

    def get_owned(
        self,
        session: object,
        notification_id: int,
        admin_user_id: int,
    ) -> AdminNotification | None:
        for row in self._rows:
            if row.id == notification_id and row.admin_user_id == admin_user_id:
                return row
        return None

    def list_for_admin(
        self,
        session: object,
        admin_user_id: int,
        *,
        unread_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[AdminNotification], int]:
        filtered = [
            row
            for row in self._rows
            if row.admin_user_id == admin_user_id
            and (not unread_only or row.read_at is None)
        ]
        filtered.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        total = len(filtered)
        return filtered[offset : offset + limit], total

    def count_unread(
        self,
        session: object,
        admin_user_id: int,
    ) -> int:
        return sum(
            1
            for row in self._rows
            if row.admin_user_id == admin_user_id and row.read_at is None
        )

    def mark_read(
        self,
        session: object,
        notification_id: int,
        admin_user_id: int,
        read_at: datetime,
    ) -> int:
        for row in self._rows:
            if (
                row.id == notification_id
                and row.admin_user_id == admin_user_id
                and row.read_at is None
            ):
                row.read_at = read_at
                return 1
        return 0

    def mark_all_read(
        self,
        session: object,
        admin_user_id: int,
        read_at: datetime,
    ) -> int:
        updated = 0
        for row in self._rows:
            if row.admin_user_id == admin_user_id and row.read_at is None:
                row.read_at = read_at
                updated += 1
        return updated


class AdvancingClock:
    """Deterministic clock for testing timestamp preservation across repeated calls."""

    def __init__(self, start: datetime) -> None:
        self._current = start

    def __call__(self) -> datetime:
        value = self._current
        self._current = self._current + timedelta(minutes=5)
        return value


def test_create_for_approval_is_idempotent_and_preserves_timestamps() -> None:
    repo = FakeNotificationRepository()
    clock = AdvancingClock(datetime(2026, 11, 7, 9, 0, 0, tzinfo=UTC))
    service = NotificationService(repository=repo, clock=clock)
    session = GuardedFakeSession()

    first = service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=101,
    )
    assert first.id == 1
    assert first.created_at == datetime(2026, 11, 7, 9, 0, 0)
    assert first.read_at is None

    # Mark read, then call create_for_approval again for the same approval_request_id
    read_result = service.mark_read(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        notification_id=first.id,
    )
    assert read_result.read_at == datetime(2026, 11, 7, 9, 5, 0)

    second = service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=101,
    )
    assert second.id == first.id
    assert second.created_at == datetime(2026, 11, 7, 9, 0, 0)
    assert second.read_at == datetime(2026, 11, 7, 9, 5, 0)


def test_mark_read_is_idempotent_and_rejects_other_admin_with_404() -> None:
    repo = FakeNotificationRepository()
    clock = AdvancingClock(datetime(2026, 11, 7, 10, 0, 0, tzinfo=UTC))
    service = NotificationService(repository=repo, clock=clock)
    session = GuardedFakeSession()

    created = service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=202,
    )

    first_mark = service.mark_read(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        notification_id=created.id,
    )
    second_mark = service.mark_read(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        notification_id=created.id,
    )
    assert first_mark.read_at == datetime(2026, 11, 7, 10, 5, 0)
    assert second_mark.read_at == first_mark.read_at

    # Other Admin or unknown id must raise 404 RESOURCE_NOT_FOUND
    for admin_id, notif_id in ((2, created.id), (1, 9999)):
        with pytest.raises(AppException) as exc_info:
            service.mark_read(
                session,  # type: ignore[arg-type]
                admin_user_id=admin_id,
                notification_id=notif_id,
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "RESOURCE_NOT_FOUND"


def test_list_count_and_mark_all_read_are_scoped_to_owning_admin() -> None:
    repo = FakeNotificationRepository()
    clock = AdvancingClock(datetime(2026, 11, 7, 11, 0, 0, tzinfo=UTC))
    service = NotificationService(repository=repo, clock=clock)
    session = GuardedFakeSession()

    n1 = service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=301,
    )
    n2 = service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        approval_request_id=302,
    )
    service.create_for_approval(
        session,  # type: ignore[arg-type]
        admin_user_id=2,
        approval_request_id=303,
    )

    assert service.count_unread(session, admin_user_id=1).count == 2  # type: ignore[arg-type]
    assert service.count_unread(session, admin_user_id=2).count == 1  # type: ignore[arg-type]

    # Stable sort: created_at DESC, id DESC
    listed = service.list_for_admin(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        page=1,
        page_size=20,
        unread_only=False,
    )
    assert [item.id for item in listed.items] == [n2.id, n1.id]
    assert listed.total == 2

    # Mark first notification read and filter unread_only=True
    service.mark_read(session, admin_user_id=1, notification_id=n1.id)  # type: ignore[arg-type]
    unread_page = service.list_for_admin(
        session,  # type: ignore[arg-type]
        admin_user_id=1,
        page=1,
        page_size=20,
        unread_only=True,
    )
    assert [item.id for item in unread_page.items] == [n2.id]
    assert unread_page.total == 1
    assert service.count_unread(session, admin_user_id=1).count == 1  # type: ignore[arg-type]

    # Mark all read for Admin 1 transitions only the remaining unread row (1)
    bulk_first = service.mark_all_read(session, admin_user_id=1)  # type: ignore[arg-type]
    bulk_second = service.mark_all_read(session, admin_user_id=1)  # type: ignore[arg-type]
    assert bulk_first.updated_count == 1
    assert bulk_second.updated_count == 0
    assert service.count_unread(session, admin_user_id=1).count == 0  # type: ignore[arg-type]
    # Admin 2's unread notification is untouched
    assert service.count_unread(session, admin_user_id=2).count == 1  # type: ignore[arg-type]


def test_notification_schemas_whitelist_fields_and_forbid_extra() -> None:
    row = AdminNotification(
        id=10,
        admin_user_id=1,
        approval_request_id=500,
        created_at=datetime(2026, 11, 7, 12, 0, 0),
        read_at=None,
    )
    dumped = NotificationRead.model_validate(row).model_dump(mode="json")
    assert set(dumped.keys()) == {"id", "approval_request_id", "created_at", "read_at"}
    assert "admin_user_id" not in dumped
    assert dumped["created_at"] == "2026-11-07T12:00:00Z"
    assert dumped["read_at"] is None

    with pytest.raises(ValidationError):
        EmptyPatchRequest.model_validate({"unexpected": True})


def test_service_and_repository_never_call_transaction_boundary_methods() -> None:
    module_dir = (
        Path(__file__).resolve().parents[3] / "app" / "modules" / "notifications"
    )
    for filename in ("repository.py", "service.py"):
        source = (module_dir / filename).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=filename)
        called_attrs = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        forbidden_found = called_attrs & FORBIDDEN_SESSION_METHODS
        assert not forbidden_found, (
            f"{filename} must not call transaction methods, found: {forbidden_found}"
        )
