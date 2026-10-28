"""
=============================================================================
FILE: app/modules/emergency/safety_check/schemas.py
MODULE: Safety Check - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc quản lý các mẫu kiểm tra an toàn (Templates) và các phiên đếm ngược (Instances).
    - Hỗ trợ thời gian gia hạn, thời lượng ân hạn (Grace Period) và vị trí cập nhật.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/safety_check.py (SafetyCheckStatus, DefaultTemplateId)
    - app/shared/schemas/location.py (GeoPointSchema)
    - Sử dụng bởi: `app/modules/emergency/safety_check/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: SafetyCheckTemplateResponse, CreateCustomTemplateRequest, StartSafetyCheckRequest,
            ExtendSafetyCheckRequest, ConfirmSafeRequest, CancelSafetyCheckRequest,
            SafetyCheckInstanceResponse.
=============================================================================
"""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums.safety_check import SafetyCheckStatus
from app.shared.schemas.location import GeoPointSchema, OptionalCoordinatesRequest


class SafetyCheckTemplateResponse(BaseModel):
    """Thông tin một mẫu hẹn giờ an toàn."""
    template_id: str = Field(..., description="Mã định danh template")
    name: str = Field(..., description="Tên template (ví dụ: Đi bộ về nhà)")
    description: Optional[str] = Field(None, description="Mô tả mục đích template")
    default_duration_minutes: int = Field(..., description="Thời lượng mặc định (phút)")
    default_grace_period_seconds: int = Field(60, description="Thời gian ân hạn mặc định (giây)")
    icon: Optional[str] = Field(None, description="Biểu tượng giao diện")
    is_system: bool = Field(True, description="True nếu là mẫu mặc định của hệ thống")
    created_by: Optional[str] = Field(None, description="UID người tạo nếu là mẫu tùy chỉnh")
    preset_durations: Optional[list[int]] = None


class CreateCustomTemplateRequest(BaseModel):
    """Payload tạo mẫu hẹn giờ tùy chỉnh của người dùng."""
    name: str = Field(..., min_length=2, max_length=100, description="Tên mẫu hẹn giờ")
    description: Optional[str] = Field(None, max_length=300, description="Mô tả hoạt động")
    default_duration_minutes: int = Field(30, ge=1, le=1440, description="Thời lượng đếm ngược (1 - 1440 phút)")
    default_grace_period_seconds: int = Field(60, ge=30, le=1800, description="Thời gian ân hạn (30 - 1800 giây)")
    icon: Optional[str] = Field("shield", description="Tên biểu tượng icon")
    preset_durations: Optional[list[int]] = Field(None, min_length=5, max_length=5)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("preset_durations")
    @classmethod
    def validate_presets(cls, value):
        if value is not None:
            if len(set(value)) != 5 or any(v < 1 or v > 1440 for v in value):
                raise ValueError("Cần 5 mốc phút khác nhau trong khoảng 1–1440.")
            return sorted(value)
        return value


class StartSafetyCheckRequest(OptionalCoordinatesRequest):
    """Payload bắt đầu một phiên hẹn giờ an toàn mới."""
    template_id: Optional[str] = Field(None, description="ID template chọn (nếu dùng template)")
    custom_name: Optional[str] = Field(None, description="Tên tùy chỉnh nếu không dùng template")
    duration_minutes: int = Field(..., ge=1, le=1440, description="Thời lượng đếm ngược (phút)")
    grace_period_seconds: Optional[int] = Field(None, ge=30, le=1800, description="Thời gian ân hạn (giây)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Vĩ độ xuất phát")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Kinh độ xuất phát")
    notes: Optional[str] = Field(None, max_length=500, description="Ghi chú điểm đến hoặc người đi cùng")


class ExtendSafetyCheckRequest(BaseModel):
    """Payload xin gia hạn thêm thời gian cho phiên đang chạy."""
    extend_minutes: int = Field(15, ge=5, le=120, description="Số phút muốn gia hạn thêm")


class ConfirmSafeRequest(BaseModel):
    """Payload xác nhận an toàn (Bấm nút 'Tôi an toàn')."""
    pin_code: Optional[str] = Field(None, description="Mã PIN an toàn nếu có thiết lập")
    note: Optional[str] = Field(None, description="Ghi chú xác nhận an toàn")


class CancelSafetyCheckRequest(BaseModel):
    """Payload người dùng chủ động hủy phiên hẹn giờ trước khi hết hạn."""
    reason: Optional[str] = Field("Người dùng đã chủ động hủy phiên hẹn giờ an toàn.", description="Lý do hủy")


class UpdateLocationCheckpointRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    """Payload cập nhật vị trí hiện tại trong quá trình đếm ngược."""
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy_meters: Optional[float] = Field(None, ge=0.0)


class SafetyCheckInstanceResponse(BaseModel):
    """Chi tiết đầy đủ của một phiên hẹn giờ kiểm tra an toàn."""
    instance_id: str = Field(..., description="Mã định danh duy nhất của phiên (UUID)")
    user_id: str = Field(..., description="Firebase UID của người dùng")
    template_id: Optional[str] = Field(None, description="Mã template đã chọn nếu có")
    name: str = Field(..., description="Tên hoạt động an toàn")
    status: SafetyCheckStatus = Field(..., description="Trạng thái phiên (ACTIVE, CHECK_REQUIRED, COMPLETED, CANCELLED, ESCALATED)")
    duration_minutes: int = Field(..., description="Thời lượng ban đầu (phút)")
    grace_period_seconds: int = Field(..., description="Thời gian ân hạn (giây)")
    started_at: Optional[Any] = Field(None, description="Thời điểm bắt đầu đếm ngược")
    expires_at: Optional[Any] = Field(None, description="Thời điểm hết giờ countdown chính thức")
    grace_period_until: Optional[Any] = Field(None, description="Thời điểm chót hết hạn Grace Period (Escalate)")
    extension_count: int = Field(0, description="Số lần đã gia hạn")
    max_extensions: int = Field(3, description="Số lần gia hạn tối đa cho phép")
    latest_location: Optional[GeoPointSchema] = Field(None, description="Tọa độ GPS ghi nhận gần nhất")
    maps_url: Optional[str] = Field(None, description="Đường link Google Maps ghim vị trí")
    notes: Optional[str] = Field(None, description="Ghi chú phiên")
    completed_at: Optional[Any] = Field(None, description="Thời điểm xác nhận an toàn thành công")
    escalated_at: Optional[Any] = Field(None, description="Thời điểm bị quá hạn leo thang cảnh báo")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật")
