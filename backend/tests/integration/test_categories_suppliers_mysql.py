"""MySQL 8.4 integration tests for Category and Supplier.

Covers schema, check constraints, primary keys, idempotent seed, and isolated cleanup.
"""

from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import Connection, delete, event, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
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


class CatalogRowTracker:
    """Track and clean only the Category and Supplier primary keys created in scope."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.category_ids: set[int] = set()
        self.supplier_ids: set[int] = set()

    def _on_category_insert(
        self, _mapper: object, connection: Connection, target: Category
    ) -> None:
        if connection.engine is self.engine and target.id is not None:
            self.category_ids.add(int(target.id))

    def _on_supplier_insert(
        self, _mapper: object, connection: Connection, target: Supplier
    ) -> None:
        if connection.engine is self.engine and target.id is not None:
            self.supplier_ids.add(int(target.id))

    def start(self) -> None:
        event.listen(Category, "after_insert", self._on_category_insert)
        event.listen(Supplier, "after_insert", self._on_supplier_insert)

    def stop(self) -> None:
        if event.contains(Category, "after_insert", self._on_category_insert):
            event.remove(Category, "after_insert", self._on_category_insert)
        if event.contains(Supplier, "after_insert", self._on_supplier_insert):
            event.remove(Supplier, "after_insert", self._on_supplier_insert)

    def cleanup(self) -> None:
        """Delete strictly by primary key IDs recorded by this tracker instance."""
        if not self.category_ids and not self.supplier_ids:
            return
        with Session(self.engine) as session, session.begin():
            if self.category_ids:
                session.execute(
                    delete(Category).where(Category.id.in_(self.category_ids))
                )
            if self.supplier_ids:
                session.execute(
                    delete(Supplier).where(Supplier.id.in_(self.supplier_ids))
                )
        self.category_ids.clear()
        self.supplier_ids.clear()

    def __enter__(self) -> "CatalogRowTracker":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        try:
            self.stop()
        finally:
            self.cleanup()


@pytest.fixture(autouse=True)
def clean_test_rows(
    migrated_integration_engine: Engine,
) -> Generator[CatalogRowTracker, None, None]:
    """Isolate each test by deleting only the record IDs created during that test."""
    with CatalogRowTracker(migrated_integration_engine) as tracker:
        yield tracker


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
        with pytest.raises((IntegrityError, OperationalError)):
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
            status="INVALID",
            created_at=now,
            updated_at=now,
        )
        session.add(invalid_sup)
        with pytest.raises((IntegrityError, OperationalError)):
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
    """Verify seed functions insert missing default data and act as no-op on repeat."""
    default_cat_names = {item["name"] for item in DEFAULT_CATEGORIES}
    default_sup_names = {item["name"] for item in DEFAULT_SUPPLIERS}

    with Session(migrated_integration_engine) as session:
        initial_cat_count = session.scalar(select(func.count(Category.id))) or 0
        preexisting_default_cats = set(
            session.scalars(
                select(Category.name).where(Category.name.in_(default_cat_names))
            ).all()
        )
        expected_new_cats = len(default_cat_names - preexisting_default_cats)

        # Category seed run 1
        cat_run_1 = seed_categories(session)
        assert cat_run_1 == expected_new_cats
        session.commit()

        cat_count_1 = session.scalar(select(func.count(Category.id)))
        assert cat_count_1 == initial_cat_count + expected_new_cats

        # Category seed run 2 (idempotent no-op)
        cat_run_2 = seed_categories(session)
        assert cat_run_2 == 0
        session.commit()

        cat_count_2 = session.scalar(select(func.count(Category.id)))
        assert cat_count_2 == cat_count_1

        initial_sup_count = session.scalar(select(func.count(Supplier.id))) or 0
        preexisting_default_sups = set(
            session.scalars(
                select(Supplier.name).where(Supplier.name.in_(default_sup_names))
            ).all()
        )
        expected_new_sups = len(default_sup_names - preexisting_default_sups)

        # Supplier seed run 1
        sup_run_1 = seed_suppliers(session)
        assert sup_run_1 == expected_new_sups
        session.commit()

        sup_count_1 = session.scalar(select(func.count(Supplier.id)))
        assert sup_count_1 == initial_sup_count + expected_new_sups

        # Supplier seed run 2 (idempotent no-op)
        sup_run_2 = seed_suppliers(session)
        assert sup_run_2 == 0
        session.commit()

        sup_count_2 = session.scalar(select(func.count(Supplier.id)))
        assert sup_count_2 == sup_count_1


def test_seed_preserves_preexisting_default_records_and_is_idempotent_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify preexisting default-named records are preserved across seed & cleanup."""
    sentinel_time = datetime(2025, 1, 15, 8, 30, 0)
    default_cat_name = str(DEFAULT_CATEGORIES[0]["name"])
    default_sup_name = str(DEFAULT_SUPPLIERS[0]["name"])

    with Session(migrated_integration_engine) as setup_session:
        existing_cat = setup_session.scalar(
            select(Category).where(Category.name == default_cat_name)
        )
        if existing_cat is None:
            existing_cat = Category(
                name=default_cat_name,
                status=CategoryStatus.INACTIVE,
                created_at=sentinel_time,
                updated_at=sentinel_time,
            )
            setup_session.add(existing_cat)

        existing_sup = setup_session.scalar(
            select(Supplier).where(Supplier.name == default_sup_name)
        )
        if existing_sup is None:
            existing_sup = Supplier(
                name=default_sup_name,
                contact_email="preexisting-seed@example.com",
                contact_phone="0999888777",
                status=SupplierStatus.INACTIVE,
                created_at=sentinel_time,
                updated_at=sentinel_time,
            )
            setup_session.add(existing_sup)

        setup_session.commit()
        pre_cat_id = existing_cat.id
        pre_cat_status = existing_cat.status
        pre_cat_created_at = existing_cat.created_at
        pre_cat_updated_at = existing_cat.updated_at

        pre_sup_id = existing_sup.id
        pre_sup_status = existing_sup.status
        pre_sup_email = existing_sup.contact_email
        pre_sup_phone = existing_sup.contact_phone
        pre_sup_created_at = existing_sup.created_at
        pre_sup_updated_at = existing_sup.updated_at

    # Execute seed runs inside an inner isolated tracker scope to verify its cleanup
    # does NOT delete or alter the preexisting records with default seed names.
    with CatalogRowTracker(migrated_integration_engine) as inner_tracker:
        with Session(migrated_integration_engine, autoflush=False) as session:
            # First seed run: skips the preexisting default-named records
            cat_run_1 = seed_categories(session)
            sup_run_1 = seed_suppliers(session)
            session.commit()

            assert pre_cat_id not in inner_tracker.category_ids
            assert pre_sup_id not in inner_tracker.supplier_ids
            assert cat_run_1 == len(inner_tracker.category_ids)
            assert sup_run_1 == len(inner_tracker.supplier_ids)

            # Verify preexisting records were not modified after first seed run
            persisted_cat = session.get(Category, pre_cat_id)
            assert persisted_cat is not None
            assert persisted_cat.name == default_cat_name
            assert persisted_cat.status == pre_cat_status
            assert persisted_cat.created_at == pre_cat_created_at
            assert persisted_cat.updated_at == pre_cat_updated_at

            persisted_sup = session.get(Supplier, pre_sup_id)
            assert persisted_sup is not None
            assert persisted_sup.name == default_sup_name
            assert persisted_sup.status == pre_sup_status
            assert persisted_sup.contact_email == pre_sup_email
            assert persisted_sup.contact_phone == pre_sup_phone
            assert persisted_sup.created_at == pre_sup_created_at
            assert persisted_sup.updated_at == pre_sup_updated_at

            # Second seed run: idempotent no-op
            cat_run_2 = seed_categories(session)
            sup_run_2 = seed_suppliers(session)
            session.commit()

            assert cat_run_2 == 0
            assert sup_run_2 == 0

        inner_created_cat_ids = set(inner_tracker.category_ids)
        inner_created_sup_ids = set(inner_tracker.supplier_ids)

    # After inner_tracker cleanup finishes:
    # 1) All records created inside inner_tracker were removed
    # 2) Preexisting records with default seed names remain completely intact
    with Session(migrated_integration_engine) as verify_session:
        if inner_created_cat_ids:
            remaining_inner_cats = verify_session.scalars(
                select(Category.id).where(Category.id.in_(inner_created_cat_ids))
            ).all()
            assert remaining_inner_cats == []
        if inner_created_sup_ids:
            remaining_inner_sups = verify_session.scalars(
                select(Supplier.id).where(Supplier.id.in_(inner_created_sup_ids))
            ).all()
            assert remaining_inner_sups == []

        preserved_cat = verify_session.get(Category, pre_cat_id)
        assert preserved_cat is not None
        assert preserved_cat.name == default_cat_name
        assert preserved_cat.status == pre_cat_status
        assert preserved_cat.created_at == pre_cat_created_at
        assert preserved_cat.updated_at == pre_cat_updated_at

        preserved_sup = verify_session.get(Supplier, pre_sup_id)
        assert preserved_sup is not None
        assert preserved_sup.name == default_sup_name
        assert preserved_sup.status == pre_sup_status
        assert preserved_sup.contact_email == pre_sup_email
        assert preserved_sup.contact_phone == pre_sup_phone
        assert preserved_sup.created_at == pre_sup_created_at
        assert preserved_sup.updated_at == pre_sup_updated_at


def test_forced_failure_still_cleans_up_committed_rows_safely_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify forced failure after commits cleans up only test-created rows."""
    now = datetime(2026, 11, 7, 11, 0, 0)

    # Preexisting records outside the failing test scope
    with Session(migrated_integration_engine) as pre_session:
        pre_cat = Category(
            name=f"{TEST_PREFIX}preexisting_before_failure_cat",
            status=CategoryStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        pre_sup = Supplier(
            name=f"{TEST_PREFIX}preexisting_before_failure_sup",
            status=SupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        pre_session.add_all([pre_cat, pre_sup])
        pre_session.commit()
        pre_cat_id = pre_cat.id
        pre_sup_id = pre_sup.id

    committed_cat_ids: list[int] = []
    committed_sup_ids: list[int] = []

    with (
        pytest.raises(RuntimeError, match="forced failure after commit"),
        CatalogRowTracker(migrated_integration_engine),
    ):
        # Session 1 commits records
        with Session(migrated_integration_engine) as session_1:
            c1 = Category(
                name=f"{TEST_PREFIX}failed_scope_cat_1",
                status=CategoryStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            s1 = Supplier(
                name=f"{TEST_PREFIX}failed_scope_sup_1",
                status=SupplierStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            session_1.add_all([c1, s1])
            session_1.commit()
            committed_cat_ids.append(c1.id)
            committed_sup_ids.append(s1.id)

        # Session 2 commits additional records, then raises a forced error
        with Session(migrated_integration_engine) as session_2:
            c2 = Category(
                name=f"{TEST_PREFIX}failed_scope_cat_2",
                status=CategoryStatus.INACTIVE,
                created_at=now,
                updated_at=now,
            )
            s2 = Supplier(
                name=f"{TEST_PREFIX}failed_scope_sup_2",
                status=SupplierStatus.INACTIVE,
                created_at=now,
                updated_at=now,
            )
            session_2.add_all([c2, s2])
            session_2.commit()
            committed_cat_ids.append(c2.id)
            committed_sup_ids.append(s2.id)

            raise RuntimeError("forced failure after commit")

    with Session(migrated_integration_engine) as verify_session:
        # Committed rows inside the failed scope must be cleaned up
        leaked_cats = verify_session.scalars(
            select(Category.id).where(Category.id.in_(committed_cat_ids))
        ).all()
        leaked_sups = verify_session.scalars(
            select(Supplier.id).where(Supplier.id.in_(committed_sup_ids))
        ).all()
        assert leaked_cats == []
        assert leaked_sups == []

        # Preexisting rows outside the failed scope must remain untouched
        assert verify_session.get(Category, pre_cat_id) is not None
        assert verify_session.get(Supplier, pre_sup_id) is not None


def test_seed_duplicate_batch_input_with_autoflush_false_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify duplicate names in one seed batch are deduplicated (autoflush=False)."""
    dup_cat_name = f"{TEST_PREFIX}batch_dup_cat"
    unique_cat_name = f"{TEST_PREFIX}batch_unique_cat"
    dup_sup_name = f"{TEST_PREFIX}batch_dup_sup"
    unique_sup_name = f"{TEST_PREFIX}batch_unique_sup"

    with Session(migrated_integration_engine, autoflush=False) as session:
        assert session.autoflush is False

        cat_created = seed_categories(
            session,
            [
                {"name": dup_cat_name},
                {"name": dup_cat_name},
                {"name": f"  {dup_cat_name}  "},
                {"name": unique_cat_name},
            ],
        )
        sup_created = seed_suppliers(
            session,
            [
                {"name": dup_sup_name, "contact_email": "first@example.com"},
                {"name": dup_sup_name, "contact_email": "second@example.com"},
                {"name": f"  {dup_sup_name}  "},
                {"name": unique_sup_name},
            ],
        )
        session.commit()

        assert cat_created == 2
        assert sup_created == 2

        cat_rows = session.scalars(
            select(Category).where(Category.name.in_([dup_cat_name, unique_cat_name]))
        ).all()
        assert len(cat_rows) == 2

        sup_rows = session.scalars(
            select(Supplier).where(Supplier.name.in_([dup_sup_name, unique_sup_name]))
        ).all()
        assert len(sup_rows) == 2


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
