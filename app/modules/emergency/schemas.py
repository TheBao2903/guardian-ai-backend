"""
=============================================================================
FILE: app/modules/emergency/schemas.py
MODULE: Emergency - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc kích hoạt, truy vấn, hủy bỏ và giải quyết phiên khẩn cấp:
      + EmergencyTriggerRequest: Yêu cầu kích hoạt SOS từ người dùng hoặc hệ thống.
      + EmergencySessionResponse: Thông tin chi tiết vòng đời phiên khẩn cấp.
      + EmergencyCancelRequest & EmergencyResolveRequest: Yêu cầu kết thúc phiên khẩn cấp.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/emergency.py (EmergencyStatus, EmergencyTriggerType, EmergencySeverity)
    - app/shared/schemas/location.py (GeoPointSchema)
    - Sử dụng bởi: `app/modules/emergency/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: EmergencyTriggerRequest, EmergencySessionResponse, EmergencyCancelRequest, EmergencyResolveRequest.
=============================================================================
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.shared.enums.emergency import EmergencySeverity, EmergencyStatus, EmergencyTriggerType
from app.shared.schemas.location import GeoPointSchema


class EmergencyTriggerRequest(BaseModel):
    """Payload kích hoạt phiên khẩn cấp SOS."""
    trigger_type: EmergencyTriggerType = Field(
        EmergencyTriggerType.MANUAL_SOS,
        description="Nguồn kích hoạt (MANUAL_SOS, NATIVE_POWER_BUTTON, SCREAM_DETECTED...)",
    )
    severity: EmergencySeverity = Field(
        EmergencySeverity.CRITICAL,
        description="Mức độ nghiêm trọng của sự cố",
    )
    event_details: Optional[str] = Field(None, description="Chi tiết biến cố (ví dụ độ tự tin AI, nhịp tim...)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Vĩ độ GPS hiện tại")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Kinh độ GPS hiện tại")
    accuracy_meters: Optional[float] = Field(None, ge=0.0, description="Bán kính sai số vị trí (m)")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Mức pin thiết bị (%)")
    notes: Optional[str] = Field(None, max_length=500, description="Ghi chú khẩn cấp kèm theo")
    recording_id: Optional[str] = Field(None, description="Mã file ghi âm bằng chứng liên kết nếu có")


class EmergencyCancelRequest(BaseModel):
    """Payload hủy phiên báo động khẩn cấp.

    Yêu cầu `pin_code` bắt buộc (4 chữ số) để xác thực.
    PIN sẽ được verify với bcrypt hash trong user profile.
    - Safe PIN (đã đổi) → gửi All-Clear tới người thân.
    - Duress PIN (đã đổi) → gửi DURESS_COERCION alert đặc biệt.
    - Fallback '1234'/'9999' chỉ hoạt động khi user CHƯA từng đổi PIN tương ứng.
    """
    cancelled_reason: Optional[str] = Field("Người dùng đã hủy báo động an toàn.", description="Lý do hủy phiên")
    pin_code: str = Field(
        ..., min_length=4, max_length=4, pattern=r"^\d{4}$",
        description="Mã PIN 4 số bắt buộc để xác thực (Safe PIN hoặc Duress PIN)"
    )


class EmergencyResolveRequest(BaseModel):
    """Payload giải quyết / kết thúc phiên khẩn cấp sau khi đã an toàn."""
    resolved_note: Optional[str] = Field("Sự cố đã được xử lý / giải cứu an toàn.", description="Ghi chú giải quyết")


class EmergencySessionResponse(BaseModel):
    """Chi tiết đầy đủ của một phiên khẩn cấp SOS."""
    session_id: str = Field(..., description="Mã phiên khẩn cấp (UUID)")
    user_id: str = Field(..., description="Firebase UID của người dùng")
    status: EmergencyStatus = Field(..., description="Trạng thái phiên (CREATED, ACTIVE, RESOLVED, CANCELLED, EXPIRED)")
    trigger_type: EmergencyTriggerType = Field(..., description="Hình thức kích hoạt")
    severity: EmergencySeverity = Field(..., description="Mức độ nghiêm trọng")
    event_details: Optional[str] = Field(None, description="Chi tiết sự kiện")
    initial_location: Optional[GeoPointSchema] = Field(None, description="Vị trí ban đầu khi kích hoạt")
    latest_location: Optional[GeoPointSchema] = Field(None, description="Vị trí cập nhật mới nhất")
    maps_url: Optional[str] = Field(None, description="Đường dẫn Google Maps ghim vị trí")
    battery_level: Optional[int] = Field(None, description="Mức pin thiết bị")
    notes: Optional[str] = Field(None, description="Ghi chú khẩn cấp")
    recording_id: Optional[str] = Field(None, description="Mã file ghi âm liên kết")
    storage_key: Optional[str] = Field(None, description="Đường dẫn tương đối lưu trữ file ghi âm trên Cloudflare R2")
    cancelled_reason: Optional[str] = Field(None, description="Lý do hủy nếu đã hủy")
    cancelled_via: Optional[str] = Field(None, description="Hình thức hủy (SAFE_PIN hoặc DURESS_PIN)")
    resolved_note: Optional[str] = Field(None, description="Ghi chú an toàn nếu đã giải quyết")
    activated_at: Optional[Any] = Field(None, description="Thời điểm kích hoạt")
    resolved_at: Optional[Any] = Field(None, description="Thời điểm kết thúc phiên")
    created_at: Optional[Any] = Field(None, description="Thời điểm tạo")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật")
