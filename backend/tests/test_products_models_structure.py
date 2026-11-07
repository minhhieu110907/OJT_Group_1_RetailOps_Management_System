"""Structure and metadata tests for Category, Product, and Inventory ORM models."""

import re

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME

from app.db.metadata import REGISTERED_MODELS
from app.modules.products.models import Category, Inventory, Product


def _normalize_sql(expr: str) -> str:
    return re.sub(r"\s+", " ", expr).strip()


def test_catalog_models_are_registered_in_metadata() -> None:
    assert Category in REGISTERED_MODELS
    assert Product in REGISTERED_MODELS
    assert Inventory in REGISTERED_MODELS


def test_category_columns_and_constraints_match_erd() -> None:
    table = Category.__table__
    assert table.name == "categories"
    assert set(table.columns.keys()) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
    }

    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key is True
    assert table.c.id.autoincrement is True

    assert isinstance(table.c.name.type, String)
    assert table.c.name.type.length == 120
    assert table.c.name.nullable is False

    assert isinstance(table.c.status.type, String)
    assert table.c.status.type.length == 8
    assert table.c.status.nullable is False
    assert str(table.c.status.server_default.arg).strip("'") == "ACTIVE"

    for dt_col in ("created_at", "updated_at"):
        assert isinstance(table.c[dt_col].type, DATETIME)
        assert table.c[dt_col].type.fsp == 6
        assert table.c[dt_col].nullable is False

    checks = {
        ck.name: _normalize_sql(str(ck.sqltext))
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }
    assert checks == {
        "ck_categories_status": "status IN ('ACTIVE','INACTIVE')",
    }


def test_product_columns_fks_indexes_and_checks_match_erd() -> None:
    table = Product.__table__
    assert table.name == "products"
    assert set(table.columns.keys()) == {
        "id",
        "category_id",
        "sku",
        "name",
        "status",
        "sale_price_vnd",
        "created_at",
        "updated_at",
    }

    assert isinstance(table.c.id.type, BigInteger)
    assert isinstance(table.c.category_id.type, BigInteger)
    assert isinstance(table.c.sku.type, String)
    assert table.c.sku.type.length == 64
    assert table.c.sku.type.collation == "ascii_bin"
    assert isinstance(table.c.name.type, String)
    assert table.c.name.type.length == 160
    assert isinstance(table.c.status.type, String)
    assert table.c.status.type.length == 8
    assert isinstance(table.c.sale_price_vnd.type, BigInteger)

    unique_constraints = {
        uc.name: [col.name for col in uc.columns]
        for uc in table.constraints
        if isinstance(uc, UniqueConstraint)
    }
    assert unique_constraints == {"uq_products_sku": ["sku"]}

    foreign_keys = {
        (fk.constraint.name, fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        ("fk_products_category_id_categories", "category_id", "categories.id"),
    }

    checks = {
        ck.name: _normalize_sql(str(ck.sqltext))
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }
    assert checks == {
        "ck_products_status_and_price": (
            "status IN ('ACTIVE','INACTIVE') AND sale_price_vnd > 0"
        ),
    }

    indexes = {
        idx.name: [col.name for col in idx.columns] for idx in table.indexes
    }
    assert indexes == {
        "ix_products_category_id_status_id": ["category_id", "status", "id"],
        "ix_products_status_id": ["status", "id"],
        "ix_products_name_id": ["name", "id"],
    }


def test_inventory_columns_fks_indexes_and_checks_match_erd() -> None:
    table = Inventory.__table__
    assert table.name == "inventory"
    assert set(table.columns.keys()) == {
        "product_id",
        "quantity",
        "stock_version",
        "first_stocked_at",
        "updated_at",
    }

    assert isinstance(table.c.product_id.type, BigInteger)
    assert table.c.product_id.primary_key is True
    assert isinstance(table.c.quantity.type, Integer)
    assert not isinstance(table.c.quantity.type, BigInteger)
    assert isinstance(table.c.stock_version.type, BigInteger)
    assert isinstance(table.c.first_stocked_at.type, DATETIME)
    assert table.c.first_stocked_at.nullable is True
    assert isinstance(table.c.updated_at.type, DATETIME)
    assert table.c.updated_at.nullable is False

    foreign_keys = {
        (fk.constraint.name, fk.parent.name, fk.target_fullname)
        for fk in table.foreign_keys
    }
    assert foreign_keys == {
        ("fk_inventory_product_id_products", "product_id", "products.id"),
    }

    checks = {
        ck.name: _normalize_sql(str(ck.sqltext))
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }
    assert checks == {
        "ck_inventory_qty_version_first_stocked": (
            "quantity >= 0 AND stock_version >= 0 "
            "AND (quantity = 0 OR first_stocked_at IS NOT NULL)"
        ),
    }

    indexes = {
        idx.name: [col.name for col in idx.columns] for idx in table.indexes
    }
    assert indexes == {
        "ix_inventory_quantity_product_id": ["quantity", "product_id"],
    }

