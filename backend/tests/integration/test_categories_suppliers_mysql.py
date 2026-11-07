"""MySQL 8.4 integration tests for Category and Supplier.

Covers schema, check constraints, primary keys, and idempotent seed.
"""

from datetime import datetime

import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.categories.models import Category, CategoryStatus
from app.modules.categories.seed import DEFAULT_CATEGORIES, seed_categories
from app.modules.suppliers.models import Supplier, SupplierStatus
from app.modules.suppliers.seed import DEFAULT_SUPPLIERS, seed_suppliers
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

TEST_PREFIX = "t3c9d63_test_"


@pytest.fixture(autouse=True)
def clean_test_rows(migrated_integration_engine: Engine) -> None:
    """Clean test and default seed rows after each test run."""
    yield
    default_cat_names = [item["name"] for item in DEFAULT_CATEGORIES]
    default_sup_names = [item["name"] for item in DEFAULT_SUPPLIERS]
    with Session(migrated_integration_engine) as session, session.begin():
        session.execute(
            delete(Category).where(
                Category.name.like(f"{TEST_PREFIX}%")
                | Category.name.in_(default_cat_names)
            )
        )
        session.execute(
            delete(Supplier).where(
                Supplier.name.like(f"{TEST_PREFIX}%")
                | Supplier.name.in_(default_sup_names)
            )
        )


def test_categories_suppliers_tables_and_columns_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify tables, columns, PK, nullability, and NO unique on name in MySQL 8.4."""
    inspector = inspect(migrated_integration_engine)
    table_names = inspector.get_table_names()
    assert "categories" in table_names
    assert "suppliers" in table_names

    # 1. Categories table verification
    cat_columns = {col["name"]: col for col in inspector.get_columns("categories")}
    assert set(cat_columns.keys()) == {
        "id",
        "name",
        "status",
        "created_at",
        "updated_at",
    }
    assert not cat_columns["id"]["nullable"]
    assert not cat_columns["name"]["nullable"]
    assert not cat_columns["status"]["nullable"]
    assert not cat_columns["created_at"]["nullable"]
    assert not cat_columns["updated_at"]["nullable"]

    cat_pk = inspector.get_pk_constraint("categories")
    assert cat_pk["constrained_columns"] == ["id"]

    for uc in inspector.get_unique_constraints("categories"):
        assert "name" not in uc["column_names"], (
            "categories.name must not have UNIQUE constraint"
        )

    for idx in inspector.get_indexes("categories"):
        if idx.get("unique"):
            assert "name" not in idx["column_names"], (
                "categories.name must not have unique index"
            )

    # 2. Suppliers table verification
    sup_columns = {col["name"]: col for col in inspector.get_columns("suppliers")}
    assert set(sup_columns.keys()) == {
        "id",
        "name",
        "contact_email",
        "contact_phone",
        "status",
        "created_at",
        "updated_at",
    }
    assert not sup_columns["id"]["nullable"]
    assert not sup_columns["name"]["nullable"]
    assert sup_columns["contact_email"]["nullable"]
    assert sup_columns["contact_phone"]["nullable"]
    assert not sup_columns["status"]["nullable"]
    assert not sup_columns["created_at"]["nullable"]
    assert not sup_columns["updated_at"]["nullable"]

    sup_pk = inspector.get_pk_constraint("suppliers")
    assert sup_pk["constrained_columns"] == ["id"]

    for uc in inspector.get_unique_constraints("suppliers"):
        assert "name" not in uc["column_names"], (
            "suppliers.name must not have UNIQUE constraint"
        )

    for idx in inspector.get_indexes("suppliers"):
        if idx.get("unique"):
            assert "name" not in idx["column_names"], (
                "suppliers.name must not have unique index"
            )


def test_categories_suppliers_check_constraints_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify MySQL 8.4 enforces CHECK constraints for status values."""
    now = datetime(2026, 11, 7, 10, 0, 0)

    # 1. Categories check constraint
    with Session(migrated_integration_engine) as session:
        invalid_cat = Category(
            name=f"{TEST_PREFIX}invalid_cat",
            status="INVALID",
            created_at=now,
            updated_at=now,
        )
        session.add(invalid_cat)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Valid transitions
        active_cat = Category(
            name=f"{TEST_PREFIX}active_cat",
            status=CategoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        inactive_cat = Category(
            name=f"{TEST_PREFIX}inactive_cat",
            status=CategoryStatus.INACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add_all([active_cat, inactive_cat])
        session.commit()

    # 2. Suppliers check constraint
    with Session(migrated_integration_engine) as session:
        invalid_sup = Supplier(
            name=f"{TEST_PREFIX}invalid_sup",
            status="SUSPENDED",
            created_at=now,
            updated_at=now,
        )
        session.add(invalid_sup)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Valid transitions
        active_sup = Supplier(
            name=f"{TEST_PREFIX}active_sup",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        inactive_sup = Supplier(
            name=f"{TEST_PREFIX}inactive_sup",
            status=SupplierStatus.INACTIVE,
            created_at=now,
            updated_at=now,
        )
        session.add_all([active_sup, inactive_sup])
        session.commit()


def test_categories_suppliers_seed_idempotency_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify seed functions insert initial data and act as no-op on repeat."""
    with Session(migrated_integration_engine) as session:
        # Category seed run 1
        cat_run_1 = seed_categories(session)
        assert cat_run_1 == len(DEFAULT_CATEGORIES)
        session.commit()

        cat_count_1 = session.scalar(select(func.count(Category.id)))
        assert cat_count_1 == len(DEFAULT_CATEGORIES)

        # Category seed run 2 (idempotent no-op)
        cat_run_2 = seed_categories(session)
        assert cat_run_2 == 0
        session.commit()

        cat_count_2 = session.scalar(select(func.count(Category.id)))
        assert cat_count_2 == len(DEFAULT_CATEGORIES)

        # Supplier seed run 1
        sup_run_1 = seed_suppliers(session)
        assert sup_run_1 == len(DEFAULT_SUPPLIERS)
        session.commit()

        sup_count_1 = session.scalar(select(func.count(Supplier.id)))
        assert sup_count_1 == len(DEFAULT_SUPPLIERS)

        # Supplier seed run 2 (idempotent no-op)
        sup_run_2 = seed_suppliers(session)
        assert sup_run_2 == 0
        session.commit()

        sup_count_2 = session.scalar(select(func.count(Supplier.id)))
        assert sup_count_2 == len(DEFAULT_SUPPLIERS)


def test_seed_transaction_boundary_rollback_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify seed functions only add/flush and do not commit on rollback."""
    cat_name = f"{TEST_PREFIX}rollback_cat"
    sup_name = f"{TEST_PREFIX}rollback_sup"

    with Session(migrated_integration_engine) as session:
        created_cat = seed_categories(session, [{"name": cat_name}])
        assert created_cat == 1
        created_sup = seed_suppliers(session, [{"name": sup_name}])
        assert created_sup == 1

        # Caller explicitly rolls back
        session.rollback()

    with Session(migrated_integration_engine) as verify_session:
        found_cat = verify_session.scalar(
            select(Category).where(Category.name == cat_name)
        )
        assert found_cat is None

        found_sup = verify_session.scalar(
            select(Supplier).where(Supplier.name == sup_name)
        )
        assert found_sup is None
