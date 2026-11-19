"""Tests for the process health endpoint."""

import httpx
import pytest
from fastapi import status
from pydantic import SecretStr

from app.api import router as api_router_module
from app.core.config import Settings
from app.main import create_app


@pytest.mark.anyio
async def test_health_returns_ok() -> None:
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}
    assert "X-RetailOps-Benchmark-Attestation" not in response.headers


@pytest.mark.anyio
async def test_health_attests_only_matching_actual_isolated_database(
    monkeypatch,
) -> None:
    settings = Settings(
        environment="test",
        db_host="unused",
        db_name="isolated",
        db_user="unused",
        db_password=SecretStr("unused"),
        benchmark_attestation_secret=SecretStr("s" * 32),
        benchmark_isolated_database="isolated",
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return "isolated"

    monkeypatch.setattr(
        api_router_module, "get_session_factory", lambda: lambda: FakeSession()
    )

    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"X-RetailOps-Benchmark-Challenge": "a" * 64},
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["X-RetailOps-Benchmark-Attestation"].startswith("v1:")


@pytest.mark.anyio
async def test_health_refuses_attestation_for_unexpected_actual_database(
    monkeypatch,
) -> None:
    settings = Settings(
        environment="test",
        db_host="unused",
        db_name="isolated",
        db_user="unused",
        db_password=SecretStr("unused"),
        benchmark_attestation_secret=SecretStr("s" * 32),
        benchmark_isolated_database="isolated",
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return "production"

    monkeypatch.setattr(
        api_router_module, "get_session_factory", lambda: lambda: FakeSession()
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"X-RetailOps-Benchmark-Challenge": "a" * 64},
        )

    assert response.status_code == status.HTTP_200_OK
    assert "X-RetailOps-Benchmark-Attestation" not in response.headers


@pytest.mark.parametrize(
    ("environment", "secret", "database"),
    [
        ("development", SecretStr("s" * 32), "isolated"),
        ("test", SecretStr("s" * 32), None),
        ("test", None, "isolated"),
    ],
)
def test_invalid_benchmark_attestation_configuration_is_rejected(
    environment: str, secret: SecretStr | None, database: str | None
) -> None:
    with pytest.raises(ValueError, match="Benchmark attestation"):
        Settings(
            environment=environment,
            db_host="unused",
            db_name="isolated",
            db_user="unused",
            db_password=SecretStr("unused"),
            benchmark_attestation_secret=secret,
            benchmark_isolated_database=database,
        )
