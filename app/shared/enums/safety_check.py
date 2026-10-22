"""
=============================================================================
FILE: app/shared/enums/safety_check.py
MODULE: Shared - Safety Check Enums
ROLE / RESPONSIBILITY:
    - Định nghĩa trạng thái của phiên hẹn giờ kiểm tra an toàn (Safety Check State Machine).
    - Định nghĩa định danh chuẩn của 5 Template mặc định theo thiết kế ADR-031.

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/emergency/safety_check/`, Scheduler, Router, Schemas.

INPUT / OUTPUT:
    - Enums: SafetyCheckStatus, DefaultTemplateId.
=============================================================================
"""

from enum import Enum


class SafetyCheckStatus(str, Enum):
    """Trạng thái máy (State Machine) của một phiên Safety Check."""
    ACTIVE = "ACTIVE"                           # Đang đếm ngược bình thường
    CHECK_REQUIRED = "CHECK_REQUIRED"           # Hết giờ đếm ngược, đang trong Grace Period chờ người dùng xác nhận
    COMPLETED = "COMPLETED"                     # Người dùng đã bấm "Tôi an toàn" thành công
    CANCELLED = "CANCELLED"                     # Người dùng chủ động hủy phiên trước khi hết hạn
    ESCALATED = "ESCALATED"                     # Quá hạn Grace Period không có phản hồi -> Kích hoạt cảnh báo người thân


class DefaultTemplateId(str, Enum):
    """Mã định danh của 5 Safety Check Templates mặc định trong hệ thống."""
    WALKING_HOME = "tpl_walking_home"           # 🚶 Đi bộ về nhà (15-30 phút, Grace: 1 phút)
    COMMUTE_TRANSIT = "tpl_commute_transit"     # 🛵 Di chuyển bằng xe (30-60 phút, Grace: 2 phút)
    OUTDOOR_TREKKING = "tpl_outdoor_trekking"   # 🥾 Khám phá ngoài trời (1-4 giờ, Grace: 5-10 phút)
    ALONE_HOME = "tpl_alone_home"               # 🏠 Kiểm tra an toàn ở một mình (30 phút - 2 giờ, Grace: 2 phút)
    MEETING_STRANGER = "tpl_meeting_stranger"   # 👤 Cuộc gặp an toàn (30-60 phút, Grace: 1-2 phút)
