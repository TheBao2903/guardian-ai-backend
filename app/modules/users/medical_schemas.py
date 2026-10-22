"""
=============================================================================
FILE: app/modules/users/medical_schemas.py
MODULE: Users - Emergency Medical Profile Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc xem và cập nhật hồ sơ y tế khẩn cấp (Emergency Medical Profile).
    - Hỗ trợ 3 cấp độ bảo mật y tế (Medical Privacy Tiers):
      + Private: Đầy đủ thông tin cho chủ tài khoản đã đăng nhập.
      + Emergency Sharable: Thông tin gửi kèm khi SOS kích hoạt.
      + Lock-Screen Public: Dữ liệu tối thiểu cho người sơ cứu ngoài màn hình khóa.
    - Tuân thủ quy định bảo mật y tế và Nghị định 13/2023/NĐ-CP (ADR-017).

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/user.py (BloodType, MedicalPrivacyLevel)
    - Sử dụng bởi: `app/modules/users/medical_repository.py`, `medical_service.py`, `router.py`.

INPUT / OUTPUT:
    - DTOs: MedicalProfileResponse, UpdateMedicalProfileRequest, PublicEmergencyProfileResponse.
=============================================================================
"""

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from app.shared.enums.user import BloodType, MedicalPrivacyLevel


class MedicalProfileResponse(BaseModel):
    """Hồ sơ y tế khẩn cấp đầy đủ (Dành riêng cho chủ tài khoản đã đăng nhập - Tier 1 Private)."""
    uid: str = Field(..., description="Firebase Unique User ID")
    blood_type: BloodType = Field(BloodType.UNKNOWN, description="Nhóm máu (A, B, AB, O và Rh +/-)")
    height_cm: Optional[float] = Field(None, ge=30.0, le=280.0, description="Chiều cao cơ thể (cm)")
    weight_kg: Optional[float] = Field(None, ge=1.0, le=350.0, description="Cân nặng cơ thể (kg)")
    allergies: List[str] = Field(default_factory=list, description="Danh sách các chất gây dị ứng nghiêm trọng")
    medications: List[str] = Field(default_factory=list, description="Danh sách các loại thuốc đang sử dụng thường xuyên")
    chronic_conditions: List[str] = Field(default_factory=list, description="Các bệnh lý nền / mãn tính (tiểu đường, tim mạch...)")
    organ_donor: bool = Field(False, description="Tình nguyện hiến tạng trong trường hợp y tế rủi ro")
    medical_notes: Optional[str] = Field(None, max_length=1000, description="Ghi chú y tế đặc biệt cho đội cứu hộ")
    privacy_level: MedicalPrivacyLevel = Field(
        MedicalPrivacyLevel.EMERGENCY_SHARABLE,
        description="Cấp độ bảo mật tổng thể (PRIVATE, EMERGENCY_SHARABLE, LOCK_SCREEN_PUBLIC)"
    )
    share_blood_type_on_lock_screen: bool = Field(True, description="Cho phép hiện nhóm máu trên màn hình khóa")
    share_allergies_on_lock_screen: bool = Field(True, description="Cho phép hiện dị ứng trên màn hình khóa")
    share_medications_on_lock_screen: bool = Field(False, description="Cho phép hiện thuốc trên màn hình khóa")
    share_chronic_conditions_on_lock_screen: bool = Field(False, description="Cho phép hiện bệnh nền trên màn hình khóa")
    share_organ_donor_on_lock_screen: bool = Field(True, description="Cho phép hiện trạng thái hiến tạng trên màn hình khóa")
    share_notes_on_lock_screen: bool = Field(False, description="Cho phép hiện ghi chú trên màn hình khóa")
    updated_at: Optional[Any] = Field(None, description="Thời điểm cập nhật hồ sơ y tế gần nhất")


class UpdateMedicalProfileRequest(BaseModel):
    """Payload cập nhật hồ sơ y tế khẩn cấp (Người dùng tùy chỉnh)."""
    blood_type: Optional[BloodType] = Field(None, description="Nhóm máu")
    height_cm: Optional[float] = Field(None, ge=30.0, le=280.0, description="Chiều cao (cm)")
    weight_kg: Optional[float] = Field(None, ge=1.0, le=350.0, description="Cân nặng (kg)")
    allergies: Optional[List[str]] = Field(None, description="Danh sách dị ứng")
    medications: Optional[List[str]] = Field(None, description="Danh sách thuốc đang dùng")
    chronic_conditions: Optional[List[str]] = Field(None, description="Bệnh nền")
    organ_donor: Optional[bool] = Field(None, description="Tình nguyện hiến tạng")
    medical_notes: Optional[str] = Field(None, max_length=1000, description="Ghi chú cứu hộ")
    privacy_level: Optional[MedicalPrivacyLevel] = Field(None, description="Cấp độ phân quyền bảo mật")
    share_blood_type_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị nhóm máu màn hình khóa")
    share_allergies_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị dị ứng màn hình khóa")
    share_medications_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị thuốc màn hình khóa")
    share_chronic_conditions_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị bệnh nền màn hình khóa")
    share_organ_donor_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị hiến tạng màn hình khóa")
    share_notes_on_lock_screen: Optional[bool] = Field(None, description="Bật/tắt hiển thị ghi chú màn hình khóa")


class EmergencyContactQuickDial(BaseModel):
    """Thông tin liên hệ rút gọn cho màn hình khóa hoặc đội sơ cứu."""
    name: str = Field(..., description="Họ tên người thân")
    relationship: str = Field(..., description="Mối quan hệ")
    phone: str = Field(..., description="Số điện thoại gọi khẩn cấp")
    priority: int = Field(1, description="Mức ưu tiên gọi")


class PublicEmergencyProfileResponse(BaseModel):
    """Hồ sơ y tế công khai ngoài màn hình khóa (Tier 3 Lock-Screen Public) cho nhân viên y tế / người đi đường."""
    user_id: str = Field(..., description="ID người dùng gặp sự cố")
    display_name: Optional[str] = Field(None, description="Tên người gặp sự cố")
    age: Optional[int] = Field(None, description="Tuổi")
    blood_type: Optional[str] = Field(None, description="Nhóm máu (nếu được phép chia sẻ)")
    allergies: List[str] = Field(default_factory=list, description="Dị ứng (nếu được phép chia sẻ)")
    medications: List[str] = Field(default_factory=list, description="Thuốc quan trọng (nếu được phép chia sẻ)")
    chronic_conditions: List[str] = Field(default_factory=list, description="Bệnh nền nguy cấp (nếu được phép chia sẻ)")
    organ_donor: Optional[bool] = Field(None, description="Hiến tạng (nếu được phép chia sẻ)")
    medical_notes: Optional[str] = Field(None, description="Ghi chú khẩn cấp (nếu được phép chia sẻ)")
    emergency_contacts: List[EmergencyContactQuickDial] = Field(default_factory=list, description="Danh bạ gọi nhanh")
    is_private: bool = Field(False, description="True nếu người dùng chọn ẩn toàn bộ hồ sơ y tế")
    disclaimer: str = Field(
        "Thông tin phục vụ sơ cứu khẩn cấp, tuân thủ Nghị định 13/2023/NĐ-CP và thiết lập quyền riêng tư của chủ thiết bị.",
        description="Cam kết pháp lý bảo mật y tế"
    )
