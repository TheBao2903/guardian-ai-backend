"""
=============================================================================
FILE: app/shared/enums/user.py
MODULE: Shared - User & Medical Profile Enums
ROLE / RESPONSIBILITY:
    - Định nghĩa các nhóm máu chuẩn y tế (Rh+ / Rh-).
    - Định nghĩa 3 cấp độ bảo vệ thông tin y tế theo nguyên tắc Medical Privacy (ADR-017).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/users/`, Medical Profile Schemas.

INPUT / OUTPUT:
    - Enums: BloodType, MedicalPrivacyLevel.
=============================================================================
"""

from enum import Enum


class BloodType(str, Enum):
    """Nhóm máu và hệ kháng nguyên Rhesus (Rh)."""
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "UNKNOWN"


class MedicalPrivacyLevel(str, Enum):
    """3 cấp độ phân quyền chia sẻ dữ liệu y tế của người dùng."""
    PRIVATE = "PRIVATE"                         # Riêng tư: Chỉ hiển thị trong app khi đã đăng nhập
    EMERGENCY_SHARABLE = "EMERGENCY_SHARABLE"   # Chia sẻ khẩn cấp: Gửi kèm cho người thân khi kích hoạt SOS
    LOCK_SCREEN_PUBLIC = "LOCK_SCREEN_PUBLIC"   # Công khai màn hình khóa: Cho phép nhân viên y tế xem khi máy bị khóa
