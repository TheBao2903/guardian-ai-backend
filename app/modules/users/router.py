"""
=============================================================================
FILE: app/modules/users/router.py
MODULE: Users - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint quản lý hồ sơ cá nhân và hồ sơ y tế khẩn cấp:
      + GET  /api/v1/users/me: Lấy thông tin hồ sơ của tài khoản hiện tại.
      + PUT  /api/v1/users/me: Cập nhật thông tin cá nhân (Họ tên, tuổi, ngày sinh, SĐT, avatar, telegram).
      + GET  /api/v1/users/me/medical: Xem hồ sơ y tế chi tiết của chính chủ (Tier 1 Private).
      + PUT  /api/v1/users/me/medical: Cập nhật hồ sơ y tế và quyền chia sẻ màn hình khóa (Tier 2).
      + GET  /api/v1/users/{user_id}/public-emergency: Hồ sơ y tế công khai ngoài màn hình khóa (Tier 3 Lock-Screen Public).
      + GET  /api/v1/users/me/login-history: Xem lịch sử đăng nhập (Audit log phục vụ bảo mật).
      + PUT  /api/v1/users/me/pins: Cập nhật mã PIN an toàn & mã PIN cưỡng bức (Phase 2).
      + DELETE /api/v1/users/me/data: Xóa dữ liệu cá nhân theo Quyền được lãng quên (Right to be Forgotten).
    - Bảo vệ thông tin y tế nhạy cảm theo Nghị định 13/2023/NĐ-CP và ADR-017.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser, LoginLogItem)
    - app/modules/users/service.py (UserService)
    - app/modules/users/medical_service.py (MedicalProfileService)
    - app/modules/users/schemas.py (UserProfileResponse, UpdateProfileRequest)
    - app/modules/users/medical_schemas.py (MedicalProfileResponse, UpdateMedicalProfileRequest, PublicEmergencyProfileResponse)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: UpdateProfileRequest, UpdateMedicalProfileRequest, Query params (limit).
    - Output: ApiResponse[UserProfileResponse | MedicalProfileResponse | PublicEmergencyProfileResponse | List[LoginLogItem] | Dict].
=============================================================================
"""

from typing import Dict, List
from fastapi import APIRouter, Depends, Path, Query

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser, LoginLogItem
from app.modules.users.medical_schemas import (
    MedicalProfileResponse,
    PublicEmergencyProfileResponse,
    UpdateMedicalProfileRequest,
)
from app.modules.users.medical_service import MedicalProfileService
from app.modules.users.schemas import (
    UpdateDeviceLocationRequest,
    UpdateProfileRequest,
    UserPinsResponse,
    UserPinsUpdateRequest,
    UserProfileResponse,
)
from app.modules.users.schemas import UserPinVerifyRequest
from app.modules.users.service import UserService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
user_service = UserService()
medical_service = MedicalProfileService()


@router.get(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    summary="Lấy chi tiết hồ sơ cá nhân của người dùng hiện tại",
)
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[UserProfileResponse]:
    """Trả về chi tiết hồ sơ cá nhân bao gồm họ tên, tuổi, ngày sinh, số điện thoại, telegram."""
    profile = await user_service.get_profile(current_user.uid)
    return ApiResponse.ok(data=profile, message="Lấy hồ sơ cá nhân thành công")


@router.put(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    summary="Cập nhật hồ sơ cá nhân của người dùng hiện tại",
)
async def update_my_profile(
    data: UpdateProfileRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[UserProfileResponse]:
    """Cập nhật các trường thông tin cá nhân được gửi lên."""
    updated_profile = await user_service.update_profile(current_user.uid, data)
    return ApiResponse.ok(data=updated_profile, message="Cập nhật hồ sơ thành công")


@router.put(
    "/me/device-location",
    response_model=ApiResponse[UserProfileResponse],
    summary="Đăng ký thiết bị và ủy quyền vị trí khẩn cấp (Pre-Authorization)",
)
async def update_device_location(
    data: UpdateDeviceLocationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[UserProfileResponse]:
    """Cập nhật thông tin thiết bị đang dùng và ủy quyền vị trí nền phục vụ SOS 1-chạm."""
    updated_profile = await user_service.update_device_location(current_user.uid, data)
    return ApiResponse.ok(data=updated_profile, message="Đăng ký thiết bị và ủy quyền vị trí thành công")


@router.get(
    "/me/medical",
    response_model=ApiResponse[MedicalProfileResponse],
    summary="Lấy hồ sơ y tế khẩn cấp chi tiết (Tier 1 Private - Đầy đủ cho chính chủ)",
)
async def get_my_medical_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[MedicalProfileResponse]:
    """Trả về toàn bộ thông tin y tế cá nhân: nhóm máu, dị ứng, bệnh nền, thuốc và cấu hình bảo mật."""
    medical_profile = await medical_service.get_medical_profile(current_user.uid)
    return ApiResponse.ok(data=medical_profile, message="Lấy hồ sơ y tế khẩn cấp thành công")


@router.put(
    "/me/medical",
    response_model=ApiResponse[MedicalProfileResponse],
    summary="Cập nhật hồ sơ y tế khẩn cấp và quyền riêng tư màn hình khóa (Tier 2)",
)
async def update_my_medical_profile(
    data: UpdateMedicalProfileRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[MedicalProfileResponse]:
    """Cập nhật các trường y tế (nhóm máu, dị ứng, thuốc...) và tùy chọn hiển thị màn hình khóa."""
    updated_medical = await medical_service.update_medical_profile(current_user.uid, data)
    return ApiResponse.ok(data=updated_medical, message="Cập nhật hồ sơ y tế thành công")


@router.get(
    "/{user_id}/public-emergency",
    response_model=ApiResponse[PublicEmergencyProfileResponse],
    summary="Hồ sơ y tế công khai ngoài màn hình khóa / Đội sơ cứu (Tier 3 Lock-Screen Public)",
)
async def get_public_emergency_info(
    user_id: str = Path(..., description="Firebase UID của người gặp nạn"),
) -> ApiResponse[PublicEmergencyProfileResponse]:
    """
    Endpoint công khai dành cho nhân viên y tế / người sơ cứu tiếp cận khi điện thoại khóa.
    Tuân thủ Nghị định 13/2023/NĐ-CP: Giấu các dữ liệu nhạy cảm nếu người dùng đặt riêng tư hoặc không cho phép.
    """
    public_profile = await medical_service.get_public_emergency_profile(user_id)
    return ApiResponse.ok(data=public_profile, message="Lấy thông tin y tế công khai khẩn cấp thành công")


@router.get(
    "/me/login-history",
    response_model=ApiResponse[List[LoginLogItem]],
    summary="Xem lịch sử đăng nhập gần nhất (Kiểm toán an ninh tài khoản)",
)
async def get_my_login_history(
    limit: int = Query(10, ge=1, le=50, description="Số lượng bản ghi tối đa"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[LoginLogItem]]:
    """Trả về danh sách các lần đăng nhập gần nhất (thời gian, IP, thiết bị)."""
    logs = await user_service.get_login_history(current_user.uid, limit=limit)
    return ApiResponse.ok(data=logs, message="Lấy lịch sử đăng nhập thành công")


@router.put(
    "/me/pins",
    response_model=ApiResponse[UserPinsResponse],
    summary="Cập nhật mã PIN an toàn và/hoặc mã PIN cưỡng bức (PLAN_PIN_VERIFICATION_OVERHAUL.md)",
)
async def update_my_pins(
    data: UserPinsUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[UserPinsResponse]:
    """
    Cập nhật mã PIN 4 số dùng để hủy SOS.

    - **sos_pin**: Mã PIN an toàn (mặc định fallback `'1234'` nếu chưa từng đổi).
    - **duress_pin**: Mã PIN cưỡng bức (mặc định fallback `'9999'` nếu chưa từng đổi).

    Sau khi đổi, fallback tương ứng bị vô hiệu hóa vĩnh viễn.
    PIN được hash bằng `bcrypt` (rounds=10, ~100ms) trước khi lưu vào Firestore.
    Plain text PIN **không bao giờ** được lưu hoặc trả về qua API.
    Có thể cập nhật 1 hoặc cả 2 PIN trong cùng 1 request.
    """
    pins = await user_service.update_user_pins(current_user.uid, data)
    return ApiResponse.ok(data=pins, message="Cập nhật mã PIN thành công")


@router.delete(
    "/me/data",
    response_model=ApiResponse[Dict[str, str]],
    summary="Yêu cầu xóa toàn bộ dữ liệu cá nhân (Quyền được lãng quên theo Nghị định 13 / GDPR)",
)
async def delete_my_data(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Dict[str, str]]:
    """Thực thi quyền xóa dữ liệu cá nhân hoàn toàn khỏi hệ thống."""
    await user_service.delete_user_data(current_user.uid)
    return ApiResponse.ok(
        data={"uid": current_user.uid},
        message="Toàn bộ dữ liệu cá nhân và y tế của bạn đã được xóa vĩnh viễn khỏi hệ thống",
    )


@router.post('/me/pins/verify', response_model=ApiResponse[dict])
async def verify_my_pin(
    data: UserPinVerifyRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[dict]:
    # Checking the settings PIN never cancels SOS or triggers a duress message.
    from app.core.exceptions import UnauthorizedException
    try:
        await user_service.verify_user_pin(current_user.uid, data.pin_code, duress=data.duress)
    except UnauthorizedException:
        # A wrong PIN is not an expired Firebase login session.
        return ApiResponse.ok(data={'verified': False})
    return ApiResponse.ok(data={'verified': True})
