"""
=============================================================================
FILE: app/modules/notifications/schemas.py
MODULE: Notifications - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO payload cho các loại thông báo cảnh báo khẩn cấp:
      + SOS Alert: Kích hoạt khẩn cấp (nút bấm, AI tiếng thét, phím nguồn, timeout).
      + Safety Check Alert: Hẹn giờ an toàn quá hạn chưa xác nhận (Escalated).
      + All Clear: Hủy báo động / Đã an toàn (Báo người thân yên tâm).
      + Audio Evidence: File ghi âm bằng chứng đính kèm.
    - Định nghĩa cấu trúc kết quả gửi thông báo `NotificationResult`.

CONNECTIONS / DEPENDENCIES:
    - app/shared/schemas/location.py (GeoPointSchema)
    - app/shared/enums/contact.py (NotificationChannel)
    - app/shared/enums/emergency.py (EmergencyTriggerType)
    - app/shared/enums/detection.py (AudioEventType)

INPUT / OUTPUT:
    - DTOs: SosAlertPayload, SafetyCheckAlertPayload, AllClearPayload, NotificationResult, TestNotificationRequest.
=============================================================================
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from app.shared.enums.contact import NotificationChannel
from app.shared.schemas.location import GeoPointSchema


class SosAlertPayload(BaseModel):
    """Payload dữ liệu gửi cảnh báo SOS khẩn cấp tới người thân."""
    user_name: str = Field(..., description="Họ tên người gặp sự cố")
    user_phone: Optional[str] = Field(None, description="Số điện thoại của người gặp sự cố")
    trigger_type: str = Field("MANUAL_BUTTON", description="Cách kích hoạt (MANUAL_BUTTON, AI_DETECTION...)")
    event_type: Optional[str] = Field(None, description="Loại biến cố âm thanh nếu có (SCREAM, DISTRESS_CRY...)")
    location: Optional[GeoPointSchema] = Field(None, description="Tọa độ GPS điểm xảy ra sự cố")
    maps_url: Optional[str] = Field(None, description="Đường link Google Maps ghim vị trí")
    navigation_url: Optional[str] = Field(None, description="Đường link Google Maps chỉ đường khẩn cấp")
    device_name: Optional[str] = Field(None, description="Tên thiết bị gửi tín hiệu SOS")
    audio_url: Optional[str] = Field(None, description="Đường link nghe đoạn ghi âm bằng chứng")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Phần trăm pin điện thoại")
    notes: Optional[str] = Field(None, description="Ghi chú khẩn cấp hoặc địa chỉ ước tính")
    # Thông tin y tế sơ cứu khẩn cấp (Emergency Medical Info)
    blood_type: Optional[str] = Field(None, description="Nhóm máu của người gặp nạn (nếu cho phép chia sẻ)")
    allergies: Optional[List[str]] = Field(default_factory=list, description="Danh sách tiền sử dị ứng thuốc/thực phẩm")
    medications: Optional[List[str]] = Field(default_factory=list, description="Danh sách thuốc đang dùng")
    chronic_conditions: Optional[List[str]] = Field(default_factory=list, description="Danh sách bệnh nền mãn tính")
    medical_notes: Optional[str] = Field(None, description="Ghi chú y tế sơ cứu đặc biệt")
    medical_profile_url: Optional[str] = Field(None, description="Đường link hồ sơ y tế khẩn cấp công khai")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Thời điểm kích hoạt cảnh báo"
    )


class SafetyCheckAlertPayload(BaseModel):
    """Payload dữ liệu khi hết thời gian kiểm tra an toàn (Safety Check Timeout)."""
    user_name: str = Field(..., description="Họ tên người dùng")
    template_name: str = Field("Hẹn giờ an toàn", description="Tên hoạt động (Đi bộ về nhà, Đi xe...)")
    duration_minutes: int = Field(..., description="Thời lượng hẹn giờ dự kiến")
    location: Optional[GeoPointSchema] = Field(None, description="Tọa độ GPS gần nhất ghi nhận được")
    maps_url: Optional[str] = Field(None, description="Đường link Google Maps")
    # Thông tin y tế sơ cứu khẩn cấp nếu có
    blood_type: Optional[str] = Field(None, description="Nhóm máu của người dùng")
    allergies: Optional[List[str]] = Field(default_factory=list, description="Danh sách dị ứng")
    chronic_conditions: Optional[List[str]] = Field(default_factory=list, description="Bệnh nền")
    medical_notes: Optional[str] = Field(None, description="Ghi chú y tế")
    medical_profile_url: Optional[str] = Field(None, description="Đường link hồ sơ y tế khẩn cấp công khai")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Thời điểm hết hạn kiểm tra"
    )


class AllClearPayload(BaseModel):
    """Payload thông báo người dùng đã an toàn / hủy phiên cảnh báo (All-Clear)."""
    user_name: str = Field(..., description="Họ tên người dùng")
    reason: Optional[str] = Field("Người dùng đã nhập mã PIN xác nhận an toàn.", description="Lý do an toàn")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Thời điểm hủy báo động"
    )


class DuressAlertPayload(BaseModel):
    """Payload cảnh báo DURESS_COERCION - khi user nhập mã PIN cưỡng bức.

    Phân biệt với AllClear:
    - AllClear: "Đã an toàn, yên tâm" → người thân thở phào.
    - DuressAlert: "BỊ ÉP BUỘC! CẦN ỨNG CỨU KHẨN CẤP!" → người thân/ công an cần can thiệp.

    Ngữ cảnh kích hoạt:
    - User bị kẻ xấu khống chế, ép nhập PIN để tắt còi báo động.
    - User nhập Duress PIN (mã bí mật) thay vì Safe PIN.
    - Hệ thống âm thầm tắt UI để không kích động kẻ xấu, nhưng NGAY LẬP TỨC gửi cảnh báo.
    """
    user_name: str = Field(..., description="Họ tên người dùng")
    note: Optional[str] = Field(
        "Người dùng vừa nhập mã PIN cưỡng bức - có thể bị ép buộc!",
        description="Ghi chú tình huống"
    )
    location: Optional["GeoPointSchema"] = Field(None, description="Vị trí cuối cùng ghi nhận được")
    maps_url: Optional[str] = Field(None, description="Đường link Google Maps vị trí")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Thời điểm kích hoạt cảnh báo"
    )


class NotificationResult(BaseModel):
    retryable: bool = False
    retry_after_seconds: int | None = None
    delivery_uncertain: bool = False
    error_code: str | None = None
    """Kết quả gửi thông báo tới một người nhận."""
    success: bool = Field(..., description="Trạng thái gửi thành công hay thất bại")
    channel: NotificationChannel = Field(NotificationChannel.TELEGRAM, description="Kênh gửi")
    recipient: str = Field(..., description="Địa chỉ người nhận (Telegram Chat ID, SĐT, Device Token)")
    message_id: Optional[str] = Field(None, description="ID tin nhắn trả về từ nhà cung cấp")
    error_message: Optional[str] = Field(None, description="Chi tiết lỗi nếu gửi thất bại")


class TestNotificationRequest(BaseModel):
    """Payload gửi thử thông báo kiểm tra kết nối Telegram Bot."""
    telegram_id: str = Field(..., description="Telegram Chat ID của người nhận")
    message: Optional[str] = Field(None, description="Tin nhắn thử nghiệm tùy chọn")
