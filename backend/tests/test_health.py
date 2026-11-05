"""Tests for the process health endpoint."""

import httpx
import pytest
from fastapi import status
from pydantic import SecretStr

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
