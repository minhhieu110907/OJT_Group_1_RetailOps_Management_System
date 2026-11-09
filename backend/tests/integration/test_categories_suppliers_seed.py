"""Idempotency tests for Category and Supplier seed scripts."""

from collections.abc import Generator

import pytest
from sqlalchemy import BigInteger, create_engine, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.modules.categories.models import Category, CategoryStatus
from app.modules.categories.seed import DEFAULT_CATEGORIES, seed_categories
from app.modules.suppliers.models import Supplier, SupplierStatus
from app.modules.suppliers.seed import DEFAULT_SUPPLIERS, seed_suppliers


@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    """Ensure SQLite maps BigInteger primary keys to INTEGER for autoincrement."""
    return "INTEGER"


@pytest.fixture
def db_session() -> Generator[Session]:
    """Provide an isolated in-memory SQLite database session for seed tests."""
    engine = create_engine("sqlite:///:memory:")
    Category.__table__.create(engine)
    Supplier.__table__.create(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def test_category_seed_is_idempotent(db_session: Session) -> None:
    """Verify seed_categories creates initial data and is idempotent on repeat."""
    # First execution: should insert all default categories
    first_run_created = seed_categories(db_session)
    assert first_run_created == len(DEFAULT_CATEGORIES)
    db_session.commit()

    categories = db_session.scalars(select(Category)).all()
    assert len(categories) == len(DEFAULT_CATEGORIES)
    for cat in categories:
        assert cat.status == CategoryStatus.ACTIVE
        assert cat.created_at is not None
        assert cat.updated_at is not None

    # Second execution: should be a clean no-op
    second_run_created = seed_categories(db_session)
    assert second_run_created == 0
    db_session.commit()

    total_count = db_session.scalar(select(func.count(Category.id)))
    assert total_count == len(DEFAULT_CATEGORIES)


def test_category_seed_custom_data_skips_existing(db_session: Session) -> None:
    """Verify custom seed list correctly skips existing names without error."""
    seed_categories(db_session, [{"name": "Đồ uống"}])
    db_session.commit()
    assert db_session.scalar(select(func.count(Category.id))) == 1

    custom_batch = [
        {"name": "Đồ uống"},  # already exists
        {"name": "Văn phòng phẩm"},  # new
        {"name": "Đồ chơi"},  # new
    ]
    created = seed_categories(db_session, custom_batch)
    db_session.commit()
    assert created == 2
    assert db_session.scalar(select(func.count(Category.id))) == 3


def test_category_seed_does_not_commit_and_respects_rollback(
    db_session: Session,
) -> None:
    """Verify seed_categories does not commit internally and honors rollback."""
    created = seed_categories(db_session, [{"name": "Rollback Category"}])
    assert created == 1
    db_session.rollback()

    assert db_session.scalar(select(func.count(Category.id))) == 0


def test_supplier_seed_is_idempotent(db_session: Session) -> None:
    """Verify seed_suppliers creates initial data and is idempotent on repeat."""
    # First execution: should insert all default suppliers
    first_run_created = seed_suppliers(db_session)
    assert first_run_created == len(DEFAULT_SUPPLIERS)
    db_session.commit()

    suppliers = db_session.scalars(select(Supplier)).all()
    assert len(suppliers) == len(DEFAULT_SUPPLIERS)
    for sup in suppliers:
        assert sup.status == SupplierStatus.ACTIVE
        assert sup.created_at is not None
        assert sup.updated_at is not None

    # Second execution: should be a clean no-op
    second_run_created = seed_suppliers(db_session)
    assert second_run_created == 0
    db_session.commit()

    total_count = db_session.scalar(select(func.count(Supplier.id)))
    assert total_count == len(DEFAULT_SUPPLIERS)


def test_supplier_seed_custom_data_skips_existing(db_session: Session) -> None:
    """Verify custom seed list correctly skips existing names without error."""
    initial_name = DEFAULT_SUPPLIERS[0]["name"]
    seed_suppliers(
        db_session,
        [{"name": initial_name, "contact_email": "test@example.com"}],
    )
    db_session.commit()
    assert db_session.scalar(select(func.count(Supplier.id))) == 1

    custom_batch = [
        {"name": initial_name},  # already exists
        {"name": "Nhà cung cấp Mới 1", "contact_phone": "0123456789"},  # new
        {"name": "Nhà cung cấp Mới 2"},  # new
    ]
    created = seed_suppliers(db_session, custom_batch)
    db_session.commit()
    assert created == 2
    assert db_session.scalar(select(func.count(Supplier.id))) == 3


def test_supplier_seed_does_not_commit_and_respects_rollback(
    db_session: Session,
) -> None:
    """Verify seed_suppliers does not commit internally and honors rollback."""
    created = seed_suppliers(db_session, [{"name": "Rollback Supplier"}])
    assert created == 1
    db_session.rollback()

    assert db_session.scalar(select(func.count(Supplier.id))) == 0


def test_seed_deduplicates_duplicate_names_in_same_batch_with_autoflush_false() -> None:
    """Verify duplicate names in one seed batch are deduplicated (autoflush=False)."""
    engine = create_engine("sqlite:///:memory:")
    Category.__table__.create(engine)
    Supplier.__table__.create(engine)
    try:
        with Session(engine, autoflush=False) as session:
            assert session.autoflush is False

            cat_batch = [
                {"name": "Đồ uống"},
                {"name": "Đồ uống"},
                {"name": "  Đồ uống  "},
                {"name": "Bánh kẹo"},
            ]
            created_cats = seed_categories(session, cat_batch)
            session.commit()
            assert created_cats == 2
            persisted_cats = session.scalars(select(Category.name)).all()
            assert persisted_cats == ["Đồ uống", "Bánh kẹo"]

            sup_batch = [
                {
                    "name": "Công ty TNHH Nước Giải Khát",
                    "contact_email": "first@example.com",
                },
                {
                    "name": "Công ty TNHH Nước Giải Khát",
                    "contact_email": "duplicate@example.com",
                },
                {"name": "  Công ty TNHH Nước Giải Khát  "},
                {"name": "Công ty Thực Phẩm Sạch"},
            ]
            created_sups = seed_suppliers(session, sup_batch)
            session.commit()
            assert created_sups == 2
            persisted_sups = session.scalars(select(Supplier)).all()
            assert [s.name for s in persisted_sups] == [
                "Công ty TNHH Nước Giải Khát",
                "Công ty Thực Phẩm Sạch",
            ]
            assert persisted_sups[0].contact_email == "first@example.com"
    finally:
        engine.dispose()
