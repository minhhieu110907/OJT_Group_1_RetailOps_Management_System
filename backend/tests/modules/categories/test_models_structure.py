"""Structure and metadata tests for Category ORM model."""

import re
from importlib import import_module

from sqlalchemy import BigInteger, CheckConstraint, String, inspect
from sqlalchemy.dialects.mysql import DATETIME

from app.db.base import Base
from app.modules.categories.models import Category

EXPECTED_COLUMNS = {
    "id",
    "name",
    "status",
    "created_at",
    "updated_at",
}
FORBIDDEN_COLUMNS = {
    "description",
    "parent_id",
    "is_active",
    "code",
    "category_code",
}


def _normalize_sql(expr: str) -> str:
    return re.sub(r"\s+", " ", expr).strip()


def _is_registered_for_alembic(model: type[Base]) -> bool:
    """Return True if the model is registered in the central Alembic metadata."""
    try:
        metadata_module = import_module("app.db.metadata")
    except ModuleNotFoundError:
        return False
    registered = getattr(metadata_module, "REGISTERED_MODELS", ())
    return model in registered


def test_category_columns_and_types_match_erd() -> None:
    """Verify table name, exact columns, types, nullability, and defaults."""
    table = Category.__table__
    assert table.name == "categories"

    actual_columns = set(table.columns.keys())
    assert actual_columns == EXPECTED_COLUMNS
    assert actual_columns.isdisjoint(FORBIDDEN_COLUMNS)

    id_col = table.columns["id"]
    assert isinstance(id_col.type, BigInteger)
    assert not id_col.nullable
    assert id_col.primary_key

    name_col = table.columns["name"]
    assert isinstance(name_col.type, String)
    assert name_col.type.length == 120
    assert not name_col.nullable

    status_col = table.columns["status"]
    assert isinstance(status_col.type, String)
    assert status_col.type.length == 8
    assert not status_col.nullable
    assert status_col.server_default is not None
    assert "'ACTIVE'" in str(status_col.server_default.arg)

    created_at_col = table.columns["created_at"]
    assert isinstance(created_at_col.type, DATETIME)
    assert created_at_col.type.fsp == 6
    assert not created_at_col.nullable

    updated_at_col = table.columns["updated_at"]
    assert isinstance(updated_at_col.type, DATETIME)
    assert updated_at_col.type.fsp == 6
    assert not updated_at_col.nullable


def test_category_pk_check_constraints_and_no_unique_on_name() -> None:
    """Verify primary key, check constraints, and assert NO unique on name."""
    table = Category.__table__

    assert [col.name for col in table.primary_key.columns] == ["id"]
    assert table.primary_key.name == "pk_categories"

    check_constraints = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert len(check_constraints) == 1
    ck = check_constraints[0]
    assert ck.name == "ck_categories_status"
    assert "status IN ('ACTIVE', 'INACTIVE')" in _normalize_sql(str(ck.sqltext))

    # Invariant: ERD does NOT have UNIQUE on name
    for uc in table.constraints:
        if hasattr(uc, "columns") and not isinstance(uc, CheckConstraint):
            col_names = [col.name for col in uc.columns]
            assert "name" not in col_names, (
                "Name column must NOT have a unique constraint"
            )

    for idx in table.indexes:
        if idx.unique:
            col_names = [col.name for col in idx.columns]
            assert "name" not in col_names, "Name column must NOT have a unique index"


def test_category_has_no_relationships() -> None:
    """Ensure Category model avoids implicit cross-module coupling."""
    mapper = inspect(Category)
    assert len(mapper.relationships) == 0


def test_category_is_registered_for_alembic() -> None:
    """Ensure Category model is exported in app.db.metadata.REGISTERED_MODELS."""
    assert _is_registered_for_alembic(Category)
