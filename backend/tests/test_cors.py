"""Settings and API tests for the exact CORS allowlist."""

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.main import create_app


def make_settings(
    cors_origins: str,
    *,
    environment: str = "development",
) -> Settings:
    return Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
        environment=environment,
        cors_origins=cors_origins,
    )


@pytest.mark.parametrize(
    "origins",
    ["*", "https://*.example.com", "https://example.com/path"],
)
def test_settings_rejects_wildcard_or_non_origin_values(origins: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(origins)


@pytest.mark.anyio
async def test_cors_allows_configured_origin_with_credentials() -> None:
    transport = httpx.ASGITransport(
        app=create_app(make_settings("http://127.0.0.1:5173"))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("http://127.0.0.1:5173")
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.anyio
async def test_cors_does_not_allow_unconfigured_origin() -> None:
    transport = httpx.ASGITransport(
        app=create_app(make_settings("http://127.0.0.1:5173"))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-origin" not in response.headers


def test_development_uses_approved_origin_when_not_configured() -> None:
    settings = make_settings("")

    assert settings.cors_origin_allowlist == ["http://127.0.0.1:5173"]


@pytest.mark.anyio
async def test_production_does_not_enable_localhost_when_not_configured() -> None:
    settings = make_settings("", environment="production")
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert settings.cors_origin_allowlist == []
    assert "access-control-allow-origin" not in response.headers


def test_production_accepts_an_explicit_exact_origin() -> None:
    settings = make_settings(
        "https://retailops.example.com",
        environment="production",
    )

    assert settings.cors_origin_allowlist == ["https://retailops.example.com"]
