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
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


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


class ForbiddenError(AppException):
    def __init__(
        self,
        message: str = "Chỉ quản trị viên mới có quyền thực hiện thao tác.",
        details: Any = None,
    ) -> None:
        super().__init__("FORBIDDEN", message, 403, details)


class ResourceNotFoundError(AppException):
    def __init__(
        self,
        message: str = "Không tìm thấy tài nguyên.",
        details: Any = None,
    ) -> None:
        super().__init__("RESOURCE_NOT_FOUND", message, 404, details)


class ConflictError(AppException):
    def __init__(
        self,
        code: str = "CONFLICT",
        message: str = "Dữ liệu xung đột.",
        details: Any = None,
    ) -> None:
        super().__init__(code, message, 409, details)


class DuplicateSkuError(ConflictError):
    def __init__(
        self,
        message: str = "Mã SKU đã tồn tại.",
        details: Any = None,
    ) -> None:
        super().__init__("DUPLICATE_SKU", message, details)


class InvalidStateError(ConflictError):
    def __init__(
        self,
        message: str = "Trạng thái không hợp lệ để thực hiện thao tác này.",
        details: Any = None,
    ) -> None:
        super().__init__("INVALID_STATE", message, details)


class DomainValidationError(AppException):
    def __init__(
        self,
        message: str = "Dữ liệu không hợp lệ.",
        details: Any = None,
    ) -> None:
        super().__init__("VALIDATION_ERROR", message, 422, details)
