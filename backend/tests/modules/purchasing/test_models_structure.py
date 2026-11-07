"""Structure and metadata tests for Purchasing ORM models (Phase A)."""

import re
from collections.abc import Generator
from importlib import import_module

import pytest
from sqlalchemy import BigInteger, CheckConstraint, Integer, String, inspect
from sqlalchemy.dialects.mysql import DATETIME

from app.db.base import Base

EXPECTED_RECEIPT_COLUMNS = {
    "id",
    "supplier_id",
    "supplier_name_snapshot",
    "status",
    "draft_version",
    "total_vnd",
    "created_by",
    "closed_by",
    "created_at",
    "updated_at",
    "closed_at",
}

EXPECTED_ITEM_COLUMNS = {
    "receipt_id",
    "product_id",
    "sku_snapshot",
    "product_name_snapshot",
    "quantity",
    "unit_cost_vnd",
    "line_total_vnd",
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


@pytest.fixture(scope="module")
def purchasing_models() -> Generator[tuple[type[Base], type[Base]]]:
    """Load Purchasing models without polluting global Alembic metadata."""
    from app.modules.purchasing.models import PurchaseReceipt, PurchaseReceiptItem

    models = (PurchaseReceipt, PurchaseReceiptItem)
    for model in models:
        table = model.__table__
        if table.name not in Base.metadata.tables:
            Base.metadata._add_table(table.name, table.schema, table)
    try:
        yield PurchaseReceipt, PurchaseReceiptItem
    finally:
        for model in reversed(models):
            table = model.__table__
            if (
                not _is_registered_for_alembic(model)
                and table.name in Base.metadata.tables
            ):
                Base.metadata.remove(table)


def test_purchase_receipt_columns_types_and_defaults_match_erd(
    purchasing_models: tuple[type[Base], type[Base]],
) -> None:
    """Verify PurchaseReceipt columns, types, nullability, and server defaults."""
    receipt_cls, _ = purchasing_models
    table = receipt_cls.__table__
    assert table.name == "purchase_receipts"
    assert set(table.columns.keys()) == EXPECTED_RECEIPT_COLUMNS

    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key is True
    assert table.c.id.autoincrement is True
    assert table.c.id.nullable is False

    assert isinstance(table.c.supplier_id.type, BigInteger)
    assert table.c.supplier_id.nullable is False

    assert isinstance(table.c.supplier_name_snapshot.type, String)
    assert table.c.supplier_name_snapshot.type.length == 160
    assert table.c.supplier_name_snapshot.nullable is True

    assert isinstance(table.c.status.type, String)
    assert table.c.status.type.length == 9
    assert table.c.status.nullable is False
    assert table.c.status.default is not None
    assert table.c.status.default.arg == "DRAFT"
    assert table.c.status.server_default is not None
    assert str(table.c.status.server_default.arg).strip("'") == "DRAFT"

    assert isinstance(table.c.draft_version.type, BigInteger)
    assert table.c.draft_version.nullable is False
    assert table.c.draft_version.default is not None
    assert table.c.draft_version.default.arg == 1
    assert table.c.draft_version.server_default is not None
    assert str(table.c.draft_version.server_default.arg).strip("'") == "1"

    assert isinstance(table.c.total_vnd.type, BigInteger)
    assert table.c.total_vnd.nullable is False
    assert table.c.total_vnd.default is not None
    assert table.c.total_vnd.default.arg == 0
    assert table.c.total_vnd.server_default is not None
    assert str(table.c.total_vnd.server_default.arg).strip("'") == "0"

    assert isinstance(table.c.created_by.type, BigInteger)
    assert table.c.created_by.nullable is False

    assert isinstance(table.c.closed_by.type, BigInteger)
    assert table.c.closed_by.nullable is True

    for dt_col_name, is_nullable in (
        ("created_at", False),
        ("updated_at", False),
        ("closed_at", True),
    ):
        col = table.c[dt_col_name]
        assert isinstance(col.type, DATETIME)
        assert col.type.fsp == 6
        assert col.nullable is is_nullable


def test_purchase_receipt_constraints_fks_and_indexes(
    purchasing_models: tuple[type[Base], type[Base]],
) -> None:
    """Verify PurchaseReceipt PK, FKs, CHECKs (exact 2), and 3 composite indexes."""
    receipt_cls, _ = purchasing_models
    table = receipt_cls.__table__

    assert table.primary_key.name == "pk_purchase_receipts"
    assert [col.name for col in table.primary_key.columns] == ["id"]

    foreign_keys = {
        (fk.constraint.name, fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        (
            "fk_purchase_receipts_supplier_id_suppliers",
            "supplier_id",
            "suppliers.id",
        ),
        (
            "fk_purchase_receipts_created_by_users",
            "created_by",
            "users.id",
        ),
        (
            "fk_purchase_receipts_closed_by_users",
            "closed_by",
            "users.id",
        ),
    }

    checks = {
        ck.name: _normalize_sql(str(ck.sqltext))
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }
    assert len(checks) == 2
    assert checks == {
        "ck_purchase_receipts_version_and_total": _normalize_sql(
            "draft_version >= 1 AND total_vnd >= 0"
        ),
        "ck_purchase_receipts_status_lifecycle": _normalize_sql(
            "(status = 'DRAFT' AND closed_by IS NULL AND closed_at IS NULL) "
            "OR (status IN ('CONFIRMED','CANCELLED') "
            "AND closed_by IS NOT NULL "
            "AND closed_at IS NOT NULL "
            "AND supplier_name_snapshot IS NOT NULL)"
        ),
    }

    indexes = {
        idx.name: (idx.unique, [col.name for col in idx.columns])
        for idx in table.indexes
    }
    assert indexes == {
        "ix_purchase_receipts_created_at_id": (
            False,
            ["created_at", "id"],
        ),
        "ix_purchase_receipts_status_created_at_id": (
            False,
            ["status", "created_at", "id"],
        ),
        "ix_purchase_receipts_supplier_id_created_at_id": (
            False,
            ["supplier_id", "created_at", "id"],
        ),
    }


def test_purchase_receipt_item_columns_pk_fks_and_check_match_erd(
    purchasing_models: tuple[type[Base], type[Base]],
) -> None:
    """Verify PurchaseReceiptItem columns, composite PK, FKs, and CHECK."""
    _, item_cls = purchasing_models
    table = item_cls.__table__
    assert table.name == "purchase_receipt_items"
    assert set(table.columns.keys()) == EXPECTED_ITEM_COLUMNS

    assert isinstance(table.c.receipt_id.type, BigInteger)
    assert table.c.receipt_id.nullable is False

    assert isinstance(table.c.product_id.type, BigInteger)
    assert table.c.product_id.nullable is False

    assert isinstance(table.c.sku_snapshot.type, String)
    assert table.c.sku_snapshot.type.length == 64
    assert table.c.sku_snapshot.nullable is False

    assert isinstance(table.c.product_name_snapshot.type, String)
    assert table.c.product_name_snapshot.type.length == 160
    assert table.c.product_name_snapshot.nullable is False

    assert isinstance(table.c.quantity.type, Integer)
    assert not isinstance(table.c.quantity.type, BigInteger)
    assert table.c.quantity.nullable is False

    assert isinstance(table.c.unit_cost_vnd.type, BigInteger)
    assert table.c.unit_cost_vnd.nullable is False

    assert isinstance(table.c.line_total_vnd.type, BigInteger)
    assert table.c.line_total_vnd.nullable is False

    assert table.primary_key.name == "pk_purchase_receipt_items"
    assert [col.name for col in table.primary_key.columns] == [
        "receipt_id",
        "product_id",
    ]

    foreign_keys = {
        (fk.constraint.name, fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        (
            "fk_purchase_receipt_items_receipt_id_purchase_receipts",
            "receipt_id",
            "purchase_receipts.id",
        ),
        (
            "fk_purchase_receipt_items_product_id_products",
            "product_id",
            "products.id",
        ),
    }

    checks = {
        ck.name: _normalize_sql(str(ck.sqltext))
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }
    assert checks == {
        "ck_purchase_receipt_items_qty_cost_line_total": _normalize_sql(
            "quantity > 0 AND unit_cost_vnd >= 0 "
            "AND line_total_vnd = CAST(quantity AS DECIMAL(30,0)) * unit_cost_vnd"
        )
    }


def test_purchasing_models_have_no_relationships(
    purchasing_models: tuple[type[Base], type[Base]],
) -> None:
    """Verify no ORM relationship() is defined on Purchasing models."""
    receipt_cls, item_cls = purchasing_models
    assert len(inspect(receipt_cls).relationships) == 0
    assert len(inspect(item_cls).relationships) == 0
