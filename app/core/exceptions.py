"""
=============================================================================
FILE: app/core/exceptions.py
MODULE: Core - Exception Handling & Standard Error Envelope
ROLE / RESPONSIBILITY:
    - Định nghĩa các custom exceptions có ngữ nghĩa domain cho Guardian AI.
    - Cung cấp hàm `register_exception_handlers(app)` để gắn các handler vào FastAPI.
    - Đảm bảo mọi lỗi (client lỗi, server lỗi, validation, 3rd party failure)
      đều trả về định dạng JSON thống nhất `{ success: false, error: {...} }`.

CONNECTIONS / DEPENDENCIES:
    - Sử dụng: FastAPI, starlette.exceptions, pydantic.RequestValidationError.
    - Gọi bởi: `app/main.py` khi khởi động server; các Service/Router ném lỗi.

INPUT / OUTPUT:
    - Input: Ngoại lệ phát sinh trong quá trình xử lý request.
    - Output: JSONResponse với HTTP status code và payload lỗi chuẩn hóa.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.logging import logger



class AppException(Exception):
    """Lớp Exception cơ sở cho toàn bộ Guardian AI."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundException(AppException):
    """Ngoại lệ khi không tìm thấy tài nguyên."""

    def __init__(self, message: str = "Tài nguyên không tồn tại", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="ENTITY_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class UnauthorizedException(AppException):
    """Ngoại lệ khi xác thực thất bại hoặc thiếu token."""

    def __init__(self, message: str = "Xác thực không thành công", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenException(AppException):
    """Ngoại lệ khi người dùng không có quyền truy cập tài nguyên."""

    def __init__(self, message: str = "Không có quyền thực hiện thao tác này", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ValidationException(AppException):
    """Ngoại lệ khi dữ liệu đầu vào không hợp lệ với business rules."""

    def __init__(self, message: str = "Dữ liệu không hợp lệ", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class ConflictException(AppException):
    """Ngoại lệ khi xung đột trạng thái (ví dụ đã có session đang chạy)."""

    def __init__(self, message: str = "Tài nguyên bị xung đột trạng thái", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="STATE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ProviderException(AppException):
    """Ngoại lệ khi dịch vụ bên thứ 3 (Telegram, Cloudflare R2, Firebase) gặp lỗi."""

    def __init__(self, message: str, provider: str, details: Optional[Dict[str, Any]] = None):
        combined_details = details or {}
        combined_details["provider"] = provider
        super().__init__(
            message=f"Lỗi nhà cung cấp dịch vụ {provider}: {message}",
            code="PROVIDER_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=combined_details,
        )


def _format_error_response(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tạo payload lỗi theo chuẩn giao tiếp chung."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Đăng ký toàn bộ exception handlers cho FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(f"AppException [{exc.code}]: {exc.message} - Path: {request.url.path}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_format_error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info(f"Validation error: {exc.errors()} - Path: {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_format_error_response(
                code="VALIDATION_ERROR",
                message="Dữ liệu yêu cầu không đúng định dạng",
                details={"errors": jsonable_encoder(exc.errors())},
            ),
        )



    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_format_error_response(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled server error: {str(exc)} - Path: {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_format_error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Đã xảy ra lỗi không mong muốn trên hệ thống máy chủ",
            ),
        )
