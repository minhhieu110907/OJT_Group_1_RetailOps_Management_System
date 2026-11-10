"""Structure and metadata tests for Product and Inventory ORM models."""

import re
from collections.abc import Generator
from importlib import import_module

import pytest
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME

from app.db.base import Base
from app.modules.categories.models import Category


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
def product_and_inventory_models() -> Generator[
    tuple[type[Base], type[Base], type[Base]]
]:
    """Load Category, Product, and Inventory without polluting Alembic metadata."""
    from app.modules.products.models import Inventory, Product

    models = (Category, Product, Inventory)
    for model in models:
        table = model.__table__
        if table.name not in Base.metadata.tables:
            Base.metadata._add_table(table.name, table.schema, table)
    try:
        yield Category, Product, Inventory
    finally:
        for model in reversed(models):
            table = model.__table__
            if (
                not _is_registered_for_alembic(model)
                and table.name in Base.metadata.tables
            ):
                Base.metadata.remove(table)


def test_products_module_does_not_define_duplicate_category() -> None:
    """Ensure products.models uses Category from categories.models as single source."""
    import app.modules.products.models as product_models

    assert not hasattr(product_models, "Category")
    assert Category.__module__ == "app.modules.categories.models"


def test_category_and_product_models_share_metadata_without_conflict(
    product_and_inventory_models: tuple[type[Base], type[Base], type[Base]],
) -> None:
    category_cls, product_cls, inventory_cls = product_and_inventory_models
    assert category_cls.__table__.metadata is Base.metadata
    assert product_cls.__table__.metadata is Base.metadata
    assert inventory_cls.__table__.metadata is Base.metadata
    assert "categories" in Base.metadata.tables
    assert "products" in Base.metadata.tables
    assert "inventory" in Base.metadata.tables


def test_product_columns_fks_indexes_and_checks_match_erd(
    product_and_inventory_models: tuple[type[Base], type[Base], type[Base]],
) -> None:
    _, product_cls, _ = product_and_inventory_models
    table = product_cls.__table__
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
    assert isinstance(table.c.created_at.type, DATETIME)
    assert isinstance(table.c.updated_at.type, DATETIME)

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

    indexes = {idx.name: [col.name for col in idx.columns] for idx in table.indexes}
    assert indexes == {
        "ix_products_category_id_status_id": ["category_id", "status", "id"],
        "ix_products_status_id": ["status", "id"],
        "ix_products_name_id": ["name", "id"],
    }


def test_inventory_columns_fks_indexes_and_checks_match_erd(
    product_and_inventory_models: tuple[type[Base], type[Base], type[Base]],
) -> None:
    _, _, inventory_cls = product_and_inventory_models
    table = inventory_cls.__table__
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

    indexes = {idx.name: [col.name for col in idx.columns] for idx in table.indexes}
    assert indexes == {
        "ix_inventory_quantity_product_id": ["quantity", "product_id"],
    }
