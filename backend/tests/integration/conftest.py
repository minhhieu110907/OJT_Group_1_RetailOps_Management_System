"""Fixtures and safety guards for MySQL integration tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

from tests.integration.database_guard import (
    IntegrationDatabaseConfigurationError,
    load_test_database_url,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def integration_database_url() -> URL:
    try:
        return load_test_database_url(os.environ)
    except IntegrationDatabaseConfigurationError as error:
        pytest.fail(str(error), pytrace=False)


@pytest.fixture(scope="session")
def integration_engine(
    integration_database_url: URL,
) -> Generator[Engine]:
    engine = create_engine(
        integration_database_url,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def migrated_integration_engine(
    integration_database_url: URL,
    integration_engine: Engine,
) -> Generator[Engine]:
    """Upgrade the dedicated test database before model integration tests."""
    variable_values = {
        "RETAILOPS_DB_HOST": integration_database_url.host or "",
        "RETAILOPS_DB_PORT": str(integration_database_url.port or 3306),
        "RETAILOPS_DB_NAME": integration_database_url.database or "",
        "RETAILOPS_DB_USER": integration_database_url.username or "",
        "RETAILOPS_DB_PASSWORD": integration_database_url.password or "",
    }
    previous_values = {name: os.environ.get(name) for name in variable_values}
    os.environ.update(variable_values)

    from app.core.config import get_settings

    get_settings.cache_clear()
    alembic_config = Config(BACKEND_DIR / "alembic.ini")
    command.upgrade(alembic_config, "head")
    try:
        yield integration_engine
    finally:
        get_settings.cache_clear()
        for name, previous_value in previous_values.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value
