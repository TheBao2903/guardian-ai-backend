"""
=============================================================================
FILE: app/modules/auth/schemas.py
MODULE: Auth - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho xác thực: Đăng ký, Đăng nhập, Quên/Đổi mật khẩu, AuthenticatedUser.
    - Định nghĩa cơ chế Consent bắt buộc (5 điều khoản cam kết bảo mật & quyền riêng tư
      theo Nghị định 13/2023/NĐ-CP và chuẩn quốc tế).
    - Định nghĩa cấu trúc bản Privacy Policy cho Modal hiển thị trên Mobile.
    - Định nghĩa mô hình lịch sử đăng nhập (LoginLogItem) phục vụ kiểm toán an ninh.

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/auth/router.py`, `service.py`, `dependencies.py`,
      `app/modules/users/router.py`.

INPUT / OUTPUT:
    - DTOs: RegisterRequest, LoginRequest, ForgotPasswordRequest,
      ChangePasswordRequest, AuthenticatedUser, AuthResponse,
      PrivacyPolicyResponse, LoginLogItem.
=============================================================================
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    """Payload đăng ký tài khoản mới kèm cam kết bảo mật bắt buộc."""
    email: EmailStr = Field(..., description="Email người dùng")
    password: str = Field(..., min_length=6, description="Mật khẩu tối thiểu 6 ký tự")
    name: str = Field(..., min_length=2, max_length=100, description="Họ và tên")
    phone: Optional[str] = Field(None, max_length=20, description="Số điện thoại liên hệ")

    # 5 mục cam kết bảo mật bắt buộc phải được tick chọn toàn bộ
    accepted_terms: bool = Field(
        ...,
        description="Đồng ý với Điều khoản dịch vụ và tuân thủ Nghị định 13/2023/NĐ-CP",
    )
    accepted_privacy_policy: bool = Field(
        ...,
        description="Đồng ý với Chính sách bảo vệ dữ liệu cá nhân",
    )
    accepted_audio_processing: bool = Field(
        ...,
        description="Cam kết âm thanh: Chỉ xử lý buffer tạm thời cục bộ, không nghe lén 24/7, chỉ lưu khi nguy cấp",
    )
    accepted_location_tracking: bool = Field(
        ...,
        description="Cam kết GPS: Không theo dõi vị trí liên tục, chỉ trích xuất tọa độ khi SOS hoặc quá hạn Safety Check",
    )
    accepted_medical_data_sharing: bool = Field(
        ...,
        description="Cam kết dữ liệu y tế: Phân cấp 3 tầng bảo mật, chỉ chia sẻ cho người thân/cứu hộ khi khẩn cấp",
    )

    @model_validator(mode="after")
    def validate_all_consents_accepted(self) -> "RegisterRequest":
        """Ràng buộc: Bắt buộc người dùng phải tick chọn đồng ý TOÀN BỘ 5 cam kết."""
        if not (
            self.accepted_terms
            and self.accepted_privacy_policy
            and self.accepted_audio_processing
            and self.accepted_location_tracking
            and self.accepted_medical_data_sharing
        ):
            raise ValueError(
                "Bạn bắt buộc phải đọc và đồng ý với toàn bộ 5 điều khoản cam kết bảo mật "
                "và quyền riêng tư dữ liệu để hoàn tất đăng ký tài khoản."
            )
        return self


class LoginRequest(BaseModel):
    """Payload đăng nhập hoặc trao đổi Firebase ID Token."""
    id_token: Optional[str] = Field(None, description="Firebase ID Token nhận từ Flutter client")
    email: Optional[EmailStr] = Field(None, description="Email (nếu đăng nhập trực tiếp qua test API)")
    password: Optional[str] = Field(None, description="Mật khẩu (nếu đăng nhập trực tiếp qua test API)")


class ForgotPasswordRequest(BaseModel):
    """Payload yêu cầu đặt lại mật khẩu."""
    email: EmailStr = Field(..., description="Email tài khoản cần khôi phục")


class ChangePasswordRequest(BaseModel):
    """Payload đổi mật khẩu tài khoản đang đăng nhập."""
    current_password: Optional[str] = Field(None, description="Mật khẩu hiện tại cần xác thực")
    new_password: str = Field(..., min_length=6, description="Mật khẩu mới tối thiểu 6 ký tự")


class AuthenticatedUser(BaseModel):
    """Thông tin định danh của người dùng đã xác thực thành công qua Firebase."""
    uid: str = Field(..., description="Firebase Unique User ID")
    email: Optional[str] = Field(None, description="Email người dùng")
    name: Optional[str] = Field(None, description="Họ và tên hiển thị")
    phone: Optional[str] = Field(None, description="Số điện thoại")
    telegram_id: Optional[str] = Field(None, description="Telegram Chat ID cá nhân")
    telegram_enabled: bool = Field(False, description="Bật nhận thông báo qua Telegram cá nhân")
    device_info: Optional[dict] = Field(None, description="Thông tin thiết bị đã đăng ký")
    location_permission_granted: bool = Field(False, description="Đã ủy quyền vị trí nền khẩn cấp")
    last_known_location: Optional[dict] = Field(None, description="Tọa độ vị trí ghi nhận gần nhất")
    role: str = Field("user", description="Vai trò hệ thống: user | admin")
    status: str = Field("active", description="Trạng thái tài khoản: active | disabled")
    avatar_url: Optional[str] = Field(None, description="URL ảnh đại diện")
    created_at: Optional[Any] = Field(None, description="Thời điểm khởi tạo")
    last_login_at: Optional[Any] = Field(None, description="Thời điểm đăng nhập gần nhất")


class AuthResponse(BaseModel):
    """Phản hồi kết quả xác thực."""
    user: AuthenticatedUser
    access_token: Optional[str] = Field(None, description="Access Token dùng cho header Authorization Bearer")
    custom_token: Optional[str] = Field(None, description="Custom Token Firebase (nếu có)")
    token_type: str = Field("Bearer", description="Loại token")
    message: str = "Xác thực thành công"


class PrivacyCommitmentItem(BaseModel):
    """Từng mục cam kết trong bản thỏa thuận bảo vệ dữ liệu."""
    key: str
    title: str
    summary: str
    full_description: str
    is_mandatory: bool = True


class PrivacyPolicyResponse(BaseModel):
    """Cấu trúc dữ liệu chi tiết của bản Cam kết bảo mật hiển thị trên Modal."""
    version: str = "1.0"
    effective_date: str = "2026-10-08"
    app_name: str = "Guardian AI"
    legal_basis: str = "Nghị định 13/2023/NĐ-CP về Bảo vệ dữ liệu cá nhân & Chuẩn quyền riêng tư quốc tế"
    commitments: List[PrivacyCommitmentItem]


class LoginLogItem(BaseModel):
    """Bản ghi lịch sử đăng nhập phục vụ kiểm toán an ninh."""
    log_id: str
    timestamp: str
    ip_address: str
    user_agent: str
    login_method: str
    status: str
