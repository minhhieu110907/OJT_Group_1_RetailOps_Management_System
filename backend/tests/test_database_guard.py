"""Contract tests for integration database safety validation."""

import pytest

from tests.integration.database_guard import (
    IntegrationDatabaseConfigurationError,
    load_test_database_url,
)

VALID_ENVIRONMENT = {
    "RETAILOPS_TEST_DATABASE_URL": (
        "mysql+pymysql://retailops_test_runner:test-password@"
        "127.0.0.1:3306/retailops_test?charset=utf8mb4"
    ),
    "MYSQL_TEST_DATABASE": "retailops_test",
    "MYSQL_TEST_USER": "retailops_test_runner",
    "MYSQL_USER": "retailops_app",
}


def test_valid_local_test_database_url_is_accepted() -> None:
    url = load_test_database_url(VALID_ENVIRONMENT)
    assert url.host == "127.0.0.1"
    assert url.database == "retailops_test"
    assert url.username == "retailops_test_runner"


@pytest.mark.parametrize(
    ("override_name", "override_value"),
    [
        (
            "RETAILOPS_TEST_DATABASE_URL",
            "mysql+pymysql://retailops_test_runner:test-password@"
            "database.example.com:3306/retailops_test",
        ),
        (
            "RETAILOPS_TEST_DATABASE_URL",
            "mysql+mysqldb://retailops_test_runner:test-password@"
            "127.0.0.1:3306/retailops_test",
        ),
        (
            "RETAILOPS_TEST_DATABASE_URL",
            "mysql+pymysql://root:test-password@127.0.0.1:3306/retailops_test",
        ),
        (
            "RETAILOPS_TEST_DATABASE_URL",
            "mysql+pymysql://retailops_test_runner:test-password@"
            "127.0.0.1:3306/retailops",
        ),
        (
            "RETAILOPS_TEST_DATABASE_URL",
            "mysql+pymysql://retailops_app:test-password@127.0.0.1:3306/retailops_test",
        ),
        ("MYSQL_TEST_USER", "retailops_app"),
    ],
)
def test_unsafe_test_database_configuration_is_rejected(
    override_name: str,
    override_value: str,
) -> None:
    environment = VALID_ENVIRONMENT | {override_name: override_value}
    with pytest.raises(IntegrationDatabaseConfigurationError):
        load_test_database_url(environment)


def test_missing_test_database_configuration_fails_closed() -> None:
    with pytest.raises(IntegrationDatabaseConfigurationError):
        load_test_database_url({})


def test_malformed_url_fails_without_echoing_credentials() -> None:
    secret = "must-not-be-reported"
    environment = VALID_ENVIRONMENT | {
        "RETAILOPS_TEST_DATABASE_URL": f"not a url containing {secret}"
    }
    with pytest.raises(IntegrationDatabaseConfigurationError) as error:
        load_test_database_url(environment)
    assert secret not in str(error.value)
