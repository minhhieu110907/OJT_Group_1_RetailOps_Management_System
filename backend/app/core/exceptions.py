"""Application exceptions exposed through the stable API error envelope."""

from typing import Any


class AppException(Exception):
    """A sanitized application error safe to map to an HTTP response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers
        super().__init__(message)


class RateLimitedError(AppException):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            "Too many requests. Please try again later.",
            429,
            headers={"Retry-After": str(max(1, retry_after))},
        )


class DependencyUnavailableError(AppException):
    def __init__(self) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            "Service temporarily unavailable.",
            503,
        )


class InvalidCredentialsError(AppException):
    def __init__(self) -> None:
        super().__init__(
            "INVALID_CREDENTIALS", "Thông tin đăng nhập không hợp lệ.", 401
        )


class SessionInvalidError(AppException):
    def __init__(self) -> None:
        super().__init__("SESSION_INVALID", "Phiên đăng nhập không hợp lệ.", 401)


class UnauthenticatedError(AppException):
    def __init__(self) -> None:
        super().__init__("UNAUTHENTICATED", "Yêu cầu xác thực.", 401)


class CsrfRejectedError(AppException):
    def __init__(self) -> None:
        super().__init__("CSRF_REJECTED", "Yêu cầu không hợp lệ.", 403)
