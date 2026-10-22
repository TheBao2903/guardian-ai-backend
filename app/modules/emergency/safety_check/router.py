"""
=============================================================================
FILE: app/modules/emergency/safety_check/router.py
MODULE: Safety Check - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint phục vụ tính năng Hẹn giờ kiểm tra an toàn:
      + GET  /api/v1/safety-check/templates: Lấy danh sách 5 mẫu mặc định và mẫu tự tạo.
      + POST /api/v1/safety-check/templates: Tạo mẫu hẹn giờ tùy chỉnh mới.
      + POST /api/v1/safety-check/start: Bắt đầu một phiên đếm ngược hẹn giờ an toàn mới.
      + GET  /api/v1/safety-check/current: Lấy thông tin phiên đang hoạt động của tôi.
      + POST /api/v1/safety-check/instances/{instance_id}/confirm-safe: Bấm "Tôi an toàn".
      + POST /api/v1/safety-check/instances/{instance_id}/extend: Gia hạn thêm thời gian (tối đa 3 lần).
      + POST /api/v1/safety-check/instances/{instance_id}/cancel: Hủy phiên hẹn giờ.
      + POST /api/v1/safety-check/instances/{instance_id}/checkpoint-location: Cập nhật vị trí hiện tại.
    - Toàn bộ endpoints được bảo vệ bởi dependency xác thực Firebase ID Token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/emergency/safety_check/service.py (SafetyCheckService)
    - app/modules/emergency/safety_check/schemas.py
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: DTO Requests.
    - Output: ApiResponse[SafetyCheckTemplateResponse | SafetyCheckInstanceResponse | List].
=============================================================================
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Path, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.emergency.safety_check.schemas import (
    CancelSafetyCheckRequest,
    ConfirmSafeRequest,
    CreateCustomTemplateRequest,
    ExtendSafetyCheckRequest,
    SafetyCheckInstanceResponse,
    SafetyCheckTemplateResponse,
    StartSafetyCheckRequest,
    UpdateLocationCheckpointRequest,
)
from app.modules.emergency.safety_check.service import SafetyCheckService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
safety_check_service = SafetyCheckService()


@router.get(
    "/templates",
    response_model=ApiResponse[List[SafetyCheckTemplateResponse]],
    summary="Lấy danh sách các mẫu hẹn giờ an toàn (Templates)",
)
async def list_safety_check_templates(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[SafetyCheckTemplateResponse]]:
    """Trả về danh sách 5 mẫu mặc định của hệ thống và các mẫu tùy chỉnh của người dùng."""
    templates = await safety_check_service.list_templates(current_user.uid)
    return ApiResponse.ok(data=templates, message="Lấy danh sách mẫu hẹn giờ thành công")


@router.post(
    "/templates",
    response_model=ApiResponse[SafetyCheckTemplateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Tạo mẫu hẹn giờ an toàn tùy chỉnh mới",
)
async def create_custom_template(
    data: CreateCustomTemplateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckTemplateResponse]:
    """Tạo mẫu hẹn giờ riêng của người dùng với thời lượng và thời gian ân hạn tùy chọn."""
    tpl = await safety_check_service.create_custom_template(current_user.uid, data)
    return ApiResponse.ok(data=tpl, message="Tạo mẫu tùy chỉnh thành công")


@router.put("/templates/{template_id}", response_model=ApiResponse[SafetyCheckTemplateResponse])
async def update_template(
    template_id: str,
    data: CreateCustomTemplateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckTemplateResponse]:
    template = await safety_check_service.update_template(current_user.uid, template_id, data)
    return ApiResponse.ok(data=template, message="Đã cập nhật kịch bản")


@router.delete("/templates/{template_id}", response_model=ApiResponse[dict])
async def delete_template(
    template_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[dict]:
    await safety_check_service.delete_template(current_user.uid, template_id)
    return ApiResponse.ok(data={"deleted": True}, message="Đã xóa kịch bản")


@router.post(
    "/start",
    response_model=ApiResponse[SafetyCheckInstanceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Bắt đầu một phiên hẹn giờ an toàn mới",
)
async def start_safety_check(
    data: StartSafetyCheckRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckInstanceResponse]:
    """Bắt đầu phiên đếm ngược an toàn (chặn nếu đang có phiên ACTIVE)."""
    instance = await safety_check_service.start_safety_check(current_user.uid, data)
    return ApiResponse.ok(data=instance, message="Bắt đầu phiên hẹn giờ an toàn thành công")


@router.get(
    "/current",
    response_model=ApiResponse[Optional[SafetyCheckInstanceResponse]],
    summary="Lấy phiên hẹn giờ an toàn đang hoạt động của người dùng",
)
async def get_current_safety_check(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Optional[SafetyCheckInstanceResponse]]:
    """Trả về chi tiết phiên đang đếm ngược hoặc null nếu không có phiên nào."""
    instance = await safety_check_service.get_current_instance(current_user.uid)
    return ApiResponse.ok(
        data=instance,
        message="Lấy phiên đang hoạt động thành công"
        if instance
        else "Hiện không có phiên hẹn giờ an toàn nào đang chạy",
    )


@router.post(
    "/instances/{instance_id}/confirm-safe",
    response_model=ApiResponse[SafetyCheckInstanceResponse],
    summary="Xác nhận an toàn (Bấm nút 'Tôi an toàn')",
)
async def confirm_safe(
    data: ConfirmSafeRequest,
    instance_id: str = Path(..., description="ID của phiên hẹn giờ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckInstanceResponse]:
    """Kết thúc phiên thành công (COMPLETED). Nếu đã bị Escalate, tự động gửi All-Clear cho người thân."""
    instance = await safety_check_service.confirm_safe(current_user.uid, instance_id, data)
    return ApiResponse.ok(data=instance, message="Đã xác nhận an toàn thành công")


@router.post(
    "/instances/{instance_id}/extend",
    response_model=ApiResponse[SafetyCheckInstanceResponse],
    summary="Gia hạn thêm thời gian cho phiên đang đếm ngược",
)
async def extend_safety_check_timer(
    data: ExtendSafetyCheckRequest,
    instance_id: str = Path(..., description="ID của phiên hẹn giờ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckInstanceResponse]:
    """Cộng thêm số phút muốn gia hạn (tối đa 3 lần)."""
    instance = await safety_check_service.extend_timer(current_user.uid, instance_id, data)
    return ApiResponse.ok(data=instance, message="Gia hạn thời gian thành công")


@router.post(
    "/instances/{instance_id}/cancel",
    response_model=ApiResponse[SafetyCheckInstanceResponse],
    summary="Người dùng chủ động hủy phiên hẹn giờ an toàn",
)
async def cancel_safety_check(
    data: CancelSafetyCheckRequest,
    instance_id: str = Path(..., description="ID của phiên hẹn giờ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckInstanceResponse]:
    """Hủy phiên hẹn giờ đang chạy trước khi hết hạn."""
    instance = await safety_check_service.cancel_instance(current_user.uid, instance_id, data)
    return ApiResponse.ok(data=instance, message="Đã hủy phiên hẹn giờ an toàn")


@router.post(
    "/instances/{instance_id}/checkpoint-location",
    response_model=ApiResponse[SafetyCheckInstanceResponse],
    summary="Cập nhật tọa độ GPS mới nhất trong quá trình hẹn giờ",
)
async def update_instance_location(
    data: UpdateLocationCheckpointRequest,
    instance_id: str = Path(..., description="ID của phiên hẹn giờ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[SafetyCheckInstanceResponse]:
    """Cập nhật vị trí GPS phục vụ ghim vị trí cứu hộ nếu quá hạn."""
    instance = await safety_check_service.update_location(
        current_user.uid, instance_id, data.latitude, data.longitude, data.accuracy_meters
    )
    return ApiResponse.ok(data=instance, message="Cập nhật vị trí thành công")
