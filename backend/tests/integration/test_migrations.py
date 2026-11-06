"""Alembic integration tests against the dedicated test database."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL, inspect
from sqlalchemy.engine import Engine

from app.db.metadata import metadata

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_alembic_upgrade_head(
    integration_database_url: URL,
    migrated_integration_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETAILOPS_DB_HOST", integration_database_url.host or "")
    monkeypatch.setenv("RETAILOPS_DB_PORT", str(integration_database_url.port or 3306))
    monkeypatch.setenv("RETAILOPS_DB_NAME", integration_database_url.database or "")
    monkeypatch.setenv("RETAILOPS_DB_USER", integration_database_url.username or "")
    monkeypatch.setenv("RETAILOPS_DB_PASSWORD", integration_database_url.password or "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    alembic_config = Config(BACKEND_DIR / "alembic.ini")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)

    required_tables = {"alembic_version", *metadata.tables}
    actual_tables = set(inspect(migrated_integration_engine).get_table_names())
    assert required_tables <= actual_tables
    with migrated_integration_engine.connect() as connection:
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    assert expected_head is not None
    assert current_revision == expected_head
    get_settings.cache_clear()
