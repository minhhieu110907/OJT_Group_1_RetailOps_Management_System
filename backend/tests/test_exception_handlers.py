"""API error envelope regression tests."""

import httpx
import pytest
from fastapi import APIRouter
from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import SessionInvalidError
from app.main import create_app


@pytest.mark.anyio
async def test_app_exception_uses_standard_error_envelope() -> None:
    settings = Settings(
        db_host="unused",
        db_name="unused",
        db_user="unused",
        db_password=SecretStr("unused"),
    )
    application = create_app(settings)
    test_router = APIRouter()

    @test_router.get("/failure")
    def failure() -> None:
        raise SessionInvalidError()

    application.include_router(test_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/failure")

    assert response.status_code == 401
    assert response.json() == {
        "code": "SESSION_INVALID",
        "message": "Phiên đăng nhập không hợp lệ.",
        "details": None,
    }
