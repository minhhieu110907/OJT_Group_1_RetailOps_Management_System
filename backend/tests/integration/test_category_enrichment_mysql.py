"""MySQL evidence for paginated category product counts and query shape."""

import json
from datetime import datetime

import pytest
from sqlalchemy import delete, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository
from app.modules.products.models import Product

pytestmark = pytest.mark.integration
PREFIX = "ENRICHMENT-CATEGORY-"


@pytest.fixture(autouse=True)
def clean_rows(migrated_integration_engine: Engine) -> None:
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        category_ids = list(
            session.scalars(select(Category.id).where(Category.name.like(f"{PREFIX}%")))
        )
        if category_ids:
            session.execute(
                delete(Product).where(Product.category_id.in_(category_ids))
            )
            session.execute(delete(Category).where(Category.id.in_(category_ids)))


def test_product_count_pagination_no_n_plus_one_and_explain(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 16, 8, 0)
    with Session(migrated_integration_engine) as session, session.begin():
        categories = [
            Category(
                name=f"{PREFIX}{index}",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
            for index in range(3)
        ]
        session.add_all(categories)
        session.flush()
        session.add_all(
            (
                Product(
                    category_id=categories[0].id,
                    sku=f"{PREFIX}SKU-1",
                    name="Active product",
                    status="ACTIVE",
                    sale_price_vnd=1_000,
                    created_at=now,
                    updated_at=now,
                ),
                Product(
                    category_id=categories[0].id,
                    sku=f"{PREFIX}SKU-2",
                    name="Inactive product",
                    status="INACTIVE",
                    sale_price_vnd=1_000,
                    created_at=now,
                    updated_at=now,
                ),
                Product(
                    category_id=categories[1].id,
                    sku=f"{PREFIX}SKU-3",
                    name="Second category product",
                    status="INACTIVE",
                    sale_price_vnd=1_000,
                    created_at=now,
                    updated_at=now,
                ),
            )
        )

    select_count = 0

    def count_selects(_conn, _cursor, statement, _params, _context, _many):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(migrated_integration_engine, "before_cursor_execute", count_selects)
    try:
        with Session(migrated_integration_engine) as session:
            rows, total = CategoryRepository().list_paginated(
                session, page=1, page_size=2, search=PREFIX
            )
    finally:
        event.remove(
            migrated_integration_engine, "before_cursor_execute", count_selects
        )

    assert total == 3
    assert [count for _category, count in rows] == [2, 1]
    assert select_count == 2

    with migrated_integration_engine.connect() as connection:
        plan_raw = connection.execute(
            text(
                "EXPLAIN FORMAT=JSON SELECT c.id, "
                "COALESCE(pc.product_count, 0) FROM categories c LEFT JOIN "
                "(SELECT category_id, COUNT(id) AS product_count FROM products "
                "GROUP BY category_id) pc ON pc.category_id = c.id "
                "WHERE c.name LIKE :prefix ORDER BY c.id LIMIT 2"
            ),
            {"prefix": f"{PREFIX}%"},
        ).scalar_one()
    plan = json.loads(plan_raw)
    assert "query_block" in plan
    assert "products" in plan_raw
