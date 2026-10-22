"""
=============================================================================
FILE: app/shared/schemas/envelope.py
MODULE: Shared - API Envelope Schemas
ROLE / RESPONSIBILITY:
    - Cung cấp generic response model cho toàn bộ các API endpoint trong backend.
    - Đảm bảo tính nhất quán của phản hồi: mọi response thành công đều bọc trong
      ApiResponse[T] kèm timestamp UTC.
    - Cung cấp PaginatedResponse[T] cho các danh sách có phân trang.

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: Toàn bộ Routers trong `app/modules/`.

INPUT / OUTPUT:
    - ApiResponse[T]: { success, data, message, timestamp }.
    - PaginatedResponse[T]: { items, total, page, size, has_next }.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Chuẩn cấu trúc phản hồi dữ liệu API thống nhất của Guardian AI."""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def ok(cls, data: Optional[T] = None, message: Optional[str] = None) -> "ApiResponse[T]":
        """Hàm tiện ích tạo phản hồi thành công nhanh."""
        return cls(success=True, data=data, message=message)


class PaginatedResponse(BaseModel, Generic[T]):
    """Cấu trúc dữ liệu phân trang cho các danh sách."""
    items: List[T]
    total: int = Field(..., ge=0, description="Tổng số bản ghi")
    page: int = Field(..., ge=1, description="Trang hiện tại (1-indexed)")
    size: int = Field(..., ge=1, description="Số lượng bản ghi mỗi trang")
    has_next: bool = Field(..., description="Có trang kế tiếp hay không")
