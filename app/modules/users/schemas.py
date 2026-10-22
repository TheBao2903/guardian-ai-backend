"""
=============================================================================
FILE: app/modules/users/schemas.py
MODULE: Users - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc xem và cập nhật hồ sơ cá nhân người dùng (Họ tên, tuổi, ngày sinh, SĐT...).
    - Khớp chính xác với mô tả khách hàng trong file Word (Họ_tên, Tuổi, Ngày tháng năm sinh).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/users/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: UserProfileResponse, UpdateProfileRequest.
=============================================================================
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """Thông tin hồ sơ cá nhân chi tiết của người dùng."""
    uid: str = Field(..., description="Firebase Unique User ID")
    email: Optional[str] = Field(None, description="Email người dùng")
    name: Optional[str] = Field(None, description="Họ và tên")
    display_name: Optional[str] = Field(None, description="Tên hiển thị")
    phone: Optional[str] = Field(None, description="Số điện thoại")
    age: Optional[int] = Field(None, ge=0, le=150, description="Tuổi người dùng")
    date_of_birth: Optional[str] = Field(None, description="Ngày tháng năm sinh (YYYY-MM-DD)")
    avatar_url: Optional[str] = Field(None, description="URL ảnh đại diện")
    telegram_id: Optional[str] = Field(None, description="Telegram Chat ID cá nhân")
    telegram_enabled: bool = Field(False, description="Bật nhận thông báo qua Telegram cá nhân")
    device_info: Optional[dict] = Field(None, description="Thông tin thiết bị tin cậy đã đăng ký")
    location_permission_granted: bool = Field(False, description="Đã ủy quyền vị trí nền khẩn cấp")
    last_known_location: Optional[dict] = Field(None, description="Tọa độ vị trí ghi nhận gần nhất")
    role: str = Field("user", description="Vai trò hệ thống")
    status: str = Field("active", description="Trạng thái tài khoản")
    blood_type: Optional[str] = Field(None, description="Nhóm máu")
    allergies: Optional[Any] = Field(None, description="Tiền sử dị ứng")
    medical_notes: Optional[str] = Field(None, description="Ghi chú y tế & Bệnh nền")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật")


class UpdateProfileRequest(BaseModel):
    """Payload cập nhật thông tin hồ sơ cá nhân."""
    name: Optional[str] = Field(None, min_length=2, max_length=100, description="Họ và tên")
    phone: Optional[str] = Field(None, max_length=20, description="Số điện thoại")
    age: Optional[int] = Field(None, ge=0, le=150, description="Tuổi")
    date_of_birth: Optional[str] = Field(None, description="Ngày tháng năm sinh (YYYY-MM-DD)")
    avatar_url: Optional[str] = Field(None, description="URL ảnh đại diện")
    telegram_id: Optional[str] = Field(None, description="Telegram Chat ID cá nhân")
    telegram_enabled: Optional[bool] = Field(None, description="Bật/tắt thông báo Telegram cá nhân")


class UpdateDeviceLocationRequest(BaseModel):
    """Payload đăng ký thiết bị và ủy quyền vị trí khẩn cấp."""
    device_name: str = Field(..., description="Tên thiết bị (ví dụ: Apple iPhone 15 Pro, Windows PC Chrome)")
    platform: Optional[str] = Field("Web", description="Nền tảng (iOS, Android, Windows, Web)")
    os_version: Optional[str] = Field(None, description="Phiên bản hệ điều hành")
    location_permission_granted: bool = Field(True, description="Trạng thái đã cấp quyền vị trí nền")
    latitude: Optional[float] = Field(None, description="Vĩ độ GPS hiện tại")
    longitude: Optional[float] = Field(None, description="Kinh độ GPS hiện tại")
    accuracy: Optional[float] = Field(None, description="Độ chính xác GPS (mét)")
    address: Optional[str] = Field(None, description="Địa chỉ ước tính")


# ============================================================================
# PIN MANAGEMENT (PLAN_PIN_VERIFICATION_OVERHAUL.md)
# ============================================================================

class UserPinsUpdateRequest(BaseModel):
    """Payload cập nhật mã PIN an toàn và/hoặc mã PIN cưỡng bức.

    - `sos_pin`: Mã PIN 4 số dùng để hủy SOS an toàn.
    - `duress_pin`: Mã PIN 4 số bí mật - khi nhập sẽ kích hoạt cảnh báo DURESS_COERCION.

    Có thể cập nhật 1 hoặc cả 2 trong cùng 1 request.
    PIN được hash bằng bcrypt trước khi lưu vào Firestore.
    """
    sos_pin: Optional[str] = Field(
        None, min_length=4, max_length=4, pattern=r"^\d{4}$",
        description="Mã PIN an toàn 4 số hủy SOS (mặc định fallback '1234' nếu chưa đổi)"
    )
    duress_pin: Optional[str] = Field(
        None, min_length=4, max_length=4, pattern=r"^\d{4}$",
        description="Mã PIN cưỡng bức 4 số (mặc định fallback '9999' nếu chưa đổi)"
    )


class UserPinsResponse(BaseModel):
    """Response trả về khi cập nhật PIN thành công.

    QUAN TRỌNG: KHÔNG trả về PIN thật (chỉ trả về mask '****' + has_changed flag).
    Lý do: tránh lộ PIN qua API response, log, network inspection.
    """
    sos_pin_set: bool = Field(..., description="True nếu user đã từng đổi SOS PIN")
    duress_pin_set: bool = Field(..., description="True nếu user đã từng đổi Duress PIN")
    sos_pin_masked: str = Field("****", description="Mask 4 số - chỉ mang tính hiển thị")
    duress_pin_masked: str = Field("****", description="Mask 4 số - chỉ mang tính hiển thị")
    has_changed_sos_pin: bool = Field(..., description="Cờ đánh dấu fallback '1234' đã bị vô hiệu hóa")
    has_changed_duress_pin: bool = Field(..., description="Cờ đánh dấu fallback '9999' đã bị vô hiệu hóa")


class UserPinVerifyRequest(BaseModel):
    pin_code: str = Field(min_length=4, max_length=4, pattern=r'^[0-9]{4}$')
    duress: bool = False
