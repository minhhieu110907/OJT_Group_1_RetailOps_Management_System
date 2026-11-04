"""Fixtures and safety guards for MySQL integration tests."""

import os
from collections.abc import Generator

import pytest
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

from tests.integration.database_guard import (
    IntegrationDatabaseConfigurationError,
    load_test_database_url,
)


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
