"""
=============================================================================
FILE: app/modules/contacts/schemas.py
MODULE: Contacts - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc quản lý danh bạ khẩn cấp:
      + Tạo mới, cập nhật, xem chi tiết và sắp xếp thứ tự ưu tiên (Priority 1, 2, 3...).
      + Priority 1 là số điện thoại được gọi trực tiếp bằng `url_launcher: tel:...` khi SOS kích hoạt.
      + Lưu trữ Telegram Chat ID để nhận thông báo cảnh báo kèm link Google Maps và file ghi âm.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/contact.py (ContactRelationship)
    - Sử dụng bởi: `app/modules/contacts/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: ContactResponse, ContactCreateRequest, ContactUpdateRequest, ContactReorderRequest.
=============================================================================
"""

from typing import Any, List, Optional
import re
from pydantic import BaseModel, Field, field_validator

from app.shared.enums.contact import ContactRelationship


def _required_telegram_id(value: Optional[str]) -> str:
    clean = (value or "").strip()
    if not re.fullmatch(r"-?\d{6,14}", clean, flags=re.ASCII):
        raise ValueError("Telegram Chat ID là bắt buộc và phải là dãy số từ 6 đến 14 chữ số.")
    return clean


class ContactResponse(BaseModel):
    """Thông tin chi tiết một người liên hệ khẩn cấp."""
    id: str = Field(..., description="Mã định danh duy nhất của liên hệ")
    user_id: str = Field(..., description="Firebase UID của chủ tài khoản")
    name: str = Field(..., description="Họ và tên người thân")
    relationship: ContactRelationship = Field(..., description="Mối quan hệ gia đình / bạn bè")
    phone: str = Field(..., description="Số điện thoại gọi khẩn cấp")
    telegram_id: Optional[str] = Field(None, description="Telegram Chat ID người nhận cảnh báo")
    priority: int = Field(1, ge=1, le=10, description="Thứ tự ưu tiên gọi (1 là người gọi chính)")
    is_active: bool = Field(True, description="Trạng thái kích hoạt")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật")


class ContactCreateRequest(BaseModel):
    """Payload thêm mới người liên hệ khẩn cấp."""
    name: str = Field(..., min_length=2, max_length=100, description="Họ và tên người thân")
    relationship: ContactRelationship = Field(..., description="Mối quan hệ")
    phone: str = Field(..., description="Số điện thoại di động Việt Nam (10 chữ số bắt đầu bằng 0)")
    telegram_id: str = Field(..., description="Telegram Chat ID bắt buộc")
    priority: Optional[int] = Field(None, ge=1, le=10, description="Mức ưu tiên (Nếu để trống sẽ tự gán cuối)")
    is_active: bool = Field(True, description="Kích hoạt nhận cảnh báo ngay")

    @field_validator("telegram_id")
    @classmethod
    def validate_telegram_id(cls, value: str) -> str:
        return _required_telegram_id(value)

    @field_validator("phone")
    @classmethod
    def validate_vn_phone(cls, v: str) -> str:
        clean = re.sub(r"[\s\-\.]", "", v.strip())
        if clean.startswith("+84"):
            clean = "0" + clean[3:]
        if not re.match(r"^0[35789]\d{8}$", clean):
            raise ValueError("Số điện thoại không hợp lệ! Vui lòng nhập số di động 10 chữ số bắt đầu bằng 0 (03, 05, 07, 08, 09).")
        return clean


class ContactUpdateRequest(BaseModel):
    """Payload cập nhật thông tin người liên hệ khẩn cấp."""
    name: Optional[str] = Field(None, min_length=2, max_length=100, description="Họ và tên")
    relationship: Optional[ContactRelationship] = Field(None, description="Mối quan hệ")
    phone: Optional[str] = Field(None, description="Số điện thoại di động Việt Nam (10 chữ số bắt đầu bằng 0)")
    telegram_id: Optional[str] = Field(None, description="Telegram Chat ID")
    priority: Optional[int] = Field(None, ge=1, le=10, description="Mức ưu tiên")
    is_active: Optional[bool] = Field(None, description="Trạng thái kích hoạt")

    @field_validator("telegram_id")
    @classmethod
    def validate_telegram_id(cls, value: Optional[str]) -> str:
        return _required_telegram_id(value)

    @field_validator("phone")
    @classmethod
    def validate_vn_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean = re.sub(r"[\s\-\.]", "", v.strip())
        if clean.startswith("+84"):
            clean = "0" + clean[3:]
        if not re.match(r"^0[35789]\d{8}$", clean):
            raise ValueError("Số điện thoại không hợp lệ! Vui lòng nhập số di động 10 chữ số bắt đầu bằng 0 (03, 05, 07, 08, 09).")
        return clean


class ContactReorderItem(BaseModel):
    """Cặp ID và mức ưu tiên mới."""
    id: str = Field(..., description="Mã liên hệ")
    priority: int = Field(..., ge=1, le=10, description="Mức ưu tiên mới")


class ContactReorderRequest(BaseModel):
    """Payload sắp xếp lại thứ tự ưu tiên của danh bạ."""
    orders: List[ContactReorderItem] = Field(..., min_length=1, description="Danh sách thứ tự ưu tiên mới")
