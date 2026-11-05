"""Fail-closed validation for the dedicated local integration database."""

from collections.abc import Mapping

from sqlalchemy import URL
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

SUPPORTED_DRIVER = "mysql+pymysql"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
ADMINISTRATIVE_USERS = frozenset(
    {"root", "mysql.sys", "mysql.session", "mysql.infoschema"}
)


class IntegrationDatabaseConfigurationError(ValueError):
    """Raised when integration database configuration is missing or unsafe."""


def load_test_database_url(environment: Mapping[str, str]) -> URL:
    """Load and validate the local test URL without exposing its credentials."""
    required_names = (
        "RETAILOPS_TEST_DATABASE_URL",
        "MYSQL_TEST_DATABASE",
        "MYSQL_TEST_USER",
        "MYSQL_USER",
    )
    missing_names = [name for name in required_names if not environment.get(name)]
    if missing_names:
        raise IntegrationDatabaseConfigurationError(
            "Dedicated integration database configuration is incomplete"
        )

    try:
        url = make_url(environment["RETAILOPS_TEST_DATABASE_URL"])
    except ArgumentError as error:
        raise IntegrationDatabaseConfigurationError(
            "Integration database URL is invalid"
        ) from error
    expected_database = environment["MYSQL_TEST_DATABASE"]
    expected_user = environment["MYSQL_TEST_USER"]
    development_user = environment["MYSQL_USER"]
    username = url.username or ""
    hostname = (url.host or "").lower()

    if url.drivername != SUPPORTED_DRIVER:
        raise IntegrationDatabaseConfigurationError(
            "Unsupported integration database driver"
        )
    if hostname not in ALLOWED_HOSTS:
        raise IntegrationDatabaseConfigurationError(
            "Integration database host is not allowed"
        )
    if url.database != expected_database:
        raise IntegrationDatabaseConfigurationError(
            "Integration database identity mismatch"
        )
    if username != expected_user:
        raise IntegrationDatabaseConfigurationError(
            "Integration database user mismatch"
        )
    if username.lower() in ADMINISTRATIVE_USERS:
        raise IntegrationDatabaseConfigurationError(
            "Administrative MySQL users are forbidden for integration tests"
        )
    if username == development_user:
        raise IntegrationDatabaseConfigurationError(
            "Integration tests must not use the development application user"
        )
    if not url.password:
        raise IntegrationDatabaseConfigurationError(
            "Integration database password must be configured"
        )
    return url
