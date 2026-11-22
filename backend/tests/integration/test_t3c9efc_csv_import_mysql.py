"""Real MySQL 8 integration tests for Bonus T3C9EFC — CSV Product Import."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.categories.models import Category, CategoryStatus
from app.modules.products.import_service import ProductImportService
from app.modules.products.models import Inventory, Product
from tests.integration.test_products_integration import ProductRowTracker

pytestmark = pytest.mark.integration


def test_t3c9efc_csv_import_partial_success_and_zero_stock_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Verify valid rows persist with zero-stock Inventory while bad rows skip."""
    run_id = uuid4().hex[:8]
    tracker = ProductRowTracker(migrated_integration_engine).start()
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    try:
        active_name = f"T3C9EFC_ACTIVE_{run_id}"
        with Session(migrated_integration_engine) as session, session.begin():
            cat_active = Category(
                name=active_name,
                status=CategoryStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            cat_inactive = Category(
                name=f"T3C9EFC_INACTIVE_{run_id}",
                status=CategoryStatus.INACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            session.add_all([cat_active, cat_inactive])
            session.flush()
            active_id, inactive_id = cat_active.id, cat_inactive.id

        csv_bytes = (
            "\ufeffsku,name,category,sale_price_vnd\r\n"
            f"T3C9EFC-{run_id}-1,Valid Item One,{active_name},25000\r\n"
            f"T3C9EFC-{run_id}-BAD1,Negative Price,{active_id},-100\r\n"
            f"T3C9EFC-{run_id}-BAD2,Inactive Cat,{inactive_id},20000\r\n"
            f"T3C9EFC-{run_id}-1,In-file Duplicate,{active_id},25000\r\n"
            f"T3C9EFC-{run_id}-2,Valid Item Two,{active_id},40000\r\n"
        ).encode()

        service = ProductImportService()
        with Session(migrated_integration_engine) as session:
            report = service.import_csv(session, csv_bytes, filename="import.csv")

        assert report.total_rows == 5
        assert report.imported_count == 2
        assert report.skipped_count == 3
        assert report.error_count == 3
        assert [e.row_number for e in report.errors] == [3, 4, 5]

        with Session(migrated_integration_engine) as session:
            p1 = session.scalar(
                select(Product).where(Product.sku == f"T3C9EFC-{run_id}-1")
            )
            p2 = session.scalar(
                select(Product).where(Product.sku == f"T3C9EFC-{run_id}-2")
            )
            assert p1 is not None and p1.sale_price_vnd == 25000
            assert p2 is not None and p2.sale_price_vnd == 40000
            inv1 = session.get(Inventory, p1.id)
            inv2 = session.get(Inventory, p2.id)
            assert inv1 is not None and inv1.quantity == 0 and inv1.stock_version == 0
            assert inv2 is not None and inv2.quantity == 0 and inv2.stock_version == 0
            assert (
                session.scalar(
                    select(Product).where(Product.sku == f"T3C9EFC-{run_id}-BAD1")
                )
                is None
            )
    finally:
        tracker.cleanup()


def test_t3c9efc_csv_import_concurrent_duplicate_sku_race_in_mysql(
    migrated_integration_engine: Engine,
) -> None:
    """Two concurrent CSV imports on same SKU: 1 succeeds, 1 reports row error."""
    run_id = uuid4().hex[:8]
    tracker = ProductRowTracker(migrated_integration_engine).start()
    now = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

    try:
        with Session(migrated_integration_engine) as session, session.begin():
            cat = Category(
                name=f"T3C9EFC_RACE_{run_id}",
                status=CategoryStatus.ACTIVE.value,
                created_at=now,
                updated_at=now,
            )
            session.add(cat)
            session.flush()
            cat_id = cat.id

        race_sku = f"T3C9EFC-RACE-{run_id}"
        csv_bytes = (
            f"sku,name,category_id,price\n{race_sku},Race Product,{cat_id},30000\n"
        ).encode()
        barrier = Barrier(2)

        def _worker():
            svc = ProductImportService()
            with Session(migrated_integration_engine) as session:
                barrier.wait(timeout=10)
                return svc.import_csv(session, csv_bytes, filename="race.csv")

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_worker)
            f2 = pool.submit(_worker)
            r1, r2 = f1.result(timeout=20), f2.result(timeout=20)

        assert sorted([r1.imported_count, r2.imported_count]) == [0, 1]
        assert sorted([r1.error_count, r2.error_count]) == [0, 1]

        with Session(migrated_integration_engine) as session:
            matches = list(
                session.scalars(select(Product).where(Product.sku == race_sku))
            )
            assert len(matches) == 1
            inv = session.get(Inventory, matches[0].id)
            assert inv is not None and inv.quantity == 0
    finally:
        tracker.cleanup()
