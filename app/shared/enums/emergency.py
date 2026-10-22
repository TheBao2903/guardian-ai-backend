"""
=============================================================================
FILE: app/shared/enums/emergency.py
MODULE: Shared - Emergency Enums
ROLE / RESPONSIBILITY:
    - Định nghĩa các trạng thái của phiên khẩn cấp (Emergency Session Lifecycle).
    - Định nghĩa các nguồn kích hoạt khẩn cấp (Manual, Native, Audio AI, Safety Check).
    - Định nghĩa mức độ nghiêm trọng (Severity) để thông báo cho người thân.
    - Đảm bảo tuân thủ ADR-014 (Emergency is a Workflow), ADR-018 (Power Button), ADR-031 (Safety Check).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/emergency/`, `app/modules/notifications/`,
      các Schemas và Repositories.

INPUT / OUTPUT:
    - Enums: EmergencyStatus, EmergencyTriggerType, EmergencySeverity.
=============================================================================
"""

from enum import Enum


class EmergencyStatus(str, Enum):
    """Vòng đời trạng thái của một phiên khẩn cấp."""
    CREATED = "CREATED"                         # Vừa tạo phiên (đang thu thập vị trí / dữ liệu ngữ cảnh)
    ACTIVE = "ACTIVE"                           # Đang kích hoạt (đang thông báo người thân, phát tín hiệu)
    CANCELLED = "CANCELLED"                     # Người dùng chủ động hủy (nhập mã PIN hoặc bấm hủy)
    RESOLVED = "RESOLVED"                       # Sự cố đã được xử lý / giải quyết an toàn
    EXPIRED = "EXPIRED"                         # Phiên tự động kết thúc sau thời gian quy định


class EmergencyTriggerType(str, Enum):
    """Nguồn phát sinh sự kiện khẩn cấp."""
    MANUAL_SOS = "MANUAL_SOS"                   # Người dùng bấm nút SOS trên màn hình app
    NATIVE_POWER_BUTTON = "NATIVE_POWER_BUTTON" # Người dùng nhấn nhanh nút nguồn vật lý (>= 5 lần)
    SCREAM_DETECTED = "SCREAM_DETECTED"         # AI phát hiện tiếng la hét / cầu cứu vượt ngưỡng
    AI_SCREAM_DETECTED = "AI_SCREAM_DETECTED"   # AI phát hiện tiếng la hét (alias tương thích mobile)
    ABNORMAL_SOUND_DETECTED = "ABNORMAL_SOUND_DETECTED" # AI phát hiện âm thanh nguy hiểm (súng, kính vỡ, ẩu đả)
    SAFETY_CHECK_TIMEOUT = "SAFETY_CHECK_TIMEOUT" # Hết giờ hẹn kiểm tra an toàn mà không có phản hồi


class EmergencySeverity(str, Enum):
    """Mức độ khẩn cấp của sự cố để quyết định kịch bản phản ứng."""
    LOW = "LOW"                                 # Nhẹ (Ví dụ: Nhắc nhở an toàn)
    MEDIUM = "MEDIUM"                           # Trung bình (Safety Check timeout mức thông thường)
    HIGH = "HIGH"                               # Cao (Phát hiện tiếng hét hoặc va chạm lớn)
    CRITICAL = "CRITICAL"                       # Tối khẩn (Manual SOS hoặc tiếng súng / đột nhập)
