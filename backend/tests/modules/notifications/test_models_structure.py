"""Structure and metadata tests for AdminNotification ORM model (Phase A)."""

from sqlalchemy import BigInteger, UniqueConstraint, inspect
from sqlalchemy.dialects.mysql import DATETIME

from app.modules.notifications.models import AdminNotification

EXPECTED_COLUMNS = {
    "id",
    "admin_user_id",
    "approval_request_id",
    "created_at",
    "read_at",
}
FORBIDDEN_COLUMNS = {
    "title",
    "message",
    "url",
    "is_read",
    "updated_at",
}


def test_admin_notification_columns_and_types_match_erd() -> None:
    """Verify table name, exact 5 columns, types, nullability, and defaults."""
    table = AdminNotification.__table__
    assert table.name == "admin_notifications"

    actual_columns = set(table.columns.keys())
    assert len(actual_columns) == 5
    assert actual_columns == EXPECTED_COLUMNS
    assert actual_columns.isdisjoint(FORBIDDEN_COLUMNS)

    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key is True
    assert table.c.id.autoincrement is True
    assert table.c.id.nullable is False

    assert isinstance(table.c.admin_user_id.type, BigInteger)
    assert table.c.admin_user_id.nullable is False
    assert table.c.admin_user_id.default is None
    assert table.c.admin_user_id.server_default is None

    assert isinstance(table.c.approval_request_id.type, BigInteger)
    assert table.c.approval_request_id.nullable is False
    assert table.c.approval_request_id.default is None
    assert table.c.approval_request_id.server_default is None

    assert isinstance(table.c.created_at.type, DATETIME)
    assert table.c.created_at.type.fsp == 6
    assert table.c.created_at.nullable is False
    assert table.c.created_at.default is None
    assert table.c.created_at.server_default is None

    assert isinstance(table.c.read_at.type, DATETIME)
    assert table.c.read_at.type.fsp == 6
    assert table.c.read_at.nullable is True
    assert table.c.read_at.default is None
    assert table.c.read_at.server_default is None


def test_admin_notification_pk_unique_fk_and_index() -> None:
    """Verify explicit PK, UNIQUE, FK target_fullname, and composite index."""
    table = AdminNotification.__table__

    assert table.primary_key.name == "pk_admin_notifications"
    assert [col.name for col in table.primary_key.columns] == ["id"]

    unique_constraints = {
        uc.name: [col.name for col in uc.columns]
        for uc in table.constraints
        if isinstance(uc, UniqueConstraint)
    }
    assert unique_constraints == {
        "uq_admin_notifications_approval_request_id": ["approval_request_id"]
    }

    foreign_keys = {
        (fk.constraint.name, fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        (
            "fk_admin_notifications_admin_user_id_users",
            "admin_user_id",
            "users.id",
        ),
        (
            "fk_admin_notifications_approval_request_id",
            "approval_request_id",
            "staff_approval_requests.id",
        ),
    }

    indexes = {
        idx.name: (idx.unique, [col.name for col in idx.columns])
        for idx in table.indexes
    }
    assert indexes == {
        "ix_admin_notifications_admin_user_id_read_at_created_at_id": (
            False,
            ["admin_user_id", "read_at", "created_at", "id"],
        )
    }


def test_admin_notification_has_no_relationships() -> None:
    """Verify no ORM relationship() is defined on AdminNotification."""
    mapper = inspect(AdminNotification)
    assert len(mapper.relationships) == 0

