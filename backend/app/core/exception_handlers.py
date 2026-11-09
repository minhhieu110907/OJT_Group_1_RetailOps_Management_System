"""Centralized FastAPI exception handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def _payload(code: str, message: str, details: object = None) -> dict[str, object]:
    return {"code": code, "message": message, "details": details}


def register_exception_handlers(application: FastAPI) -> None:
    """Install sanitized mappings for domain, validation, and unknown errors."""

    @application.exception_handler(AppException)
    async def handle_app_exception(
        _request: Request, error: AppException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_payload(error.code, error.message, error.details),
            headers=error.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "reason": item["type"],
            }
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_payload("VALIDATION_ERROR", "Dữ liệu không hợp lệ.", details),
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, error: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled application error type=%s",
            type(error).__name__,
            extra={"method": request.method, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=_payload("INTERNAL_SERVER_ERROR", "Đã xảy ra lỗi hệ thống."),
        )
