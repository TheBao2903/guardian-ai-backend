"""
=============================================================================
FILE: app/modules/emergency/router.py
MODULE: Emergency - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint cốt lõi của quy trình ứng phó khẩn cấp:
      + POST /api/v1/emergency/sos: Kích hoạt SOS khẩn cấp (Idempotent chống spam duplicate).
      + POST /api/v1/emergency/cancel: Hủy báo động (Người dùng bấm nhầm / Đã an toàn).
      + POST /api/v1/emergency/resolve: Đánh dấu sự cố đã được xử lý / giải cứu.
      + GET  /api/v1/emergency/active: Lấy thông tin phiên đang ACTIVE hiện tại.
      + GET  /api/v1/emergency/sessions: Lấy lịch sử các phiên khẩn cấp của người dùng.
      + GET  /api/v1/emergency/sessions/{session_id}: Xem chi tiết một phiên khẩn cấp.
    - Toàn bộ endpoints được bảo vệ bởi dependency xác thực Firebase ID Token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/emergency/service.py (EmergencyService)
    - app/modules/emergency/schemas.py (EmergencyTriggerRequest, EmergencyCancelRequest, EmergencyResolveRequest, EmergencySessionResponse)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: EmergencyTriggerRequest, EmergencyCancelRequest, EmergencyResolveRequest.
    - Output: ApiResponse[EmergencySessionResponse | Optional[EmergencySessionResponse] | List].
=============================================================================
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.emergency.schemas import (
    EmergencyCancelRequest,
    EmergencyResolveRequest,
    EmergencySessionResponse,
    EmergencyTriggerRequest,
)
from app.modules.emergency.service import EmergencyService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
emergency_service = EmergencyService()


@router.post(
    "/sos",
    response_model=ApiResponse[EmergencySessionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Kích hoạt khẩn cấp SOS (Idempotent - Chống trùng lặp khi bấm liên tục)",
)
async def trigger_emergency_sos(
    data: EmergencyTriggerRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[EmergencySessionResponse]:
    """
    Kích hoạt báo động khẩn cấp:
    - Tạo phiên khẩn cấp trong Firestore (nếu chưa có phiên ACTIVE).
    - Lưu mốc tọa độ Location Checkpoint.
    - Gửi cảnh báo Telegram tức thời tới toàn bộ người thân.
    - Phát stream WebSocket tới các quan sát viên.
    - Nếu đã có phiên ACTIVE, cập nhật vị trí mới và trả về phiên hiện có (Idempotent).
    """
    session = await emergency_service.trigger_sos(current_user.uid, data)
    return ApiResponse.ok(data=session, message="Đã kích hoạt phản ứng khẩn cấp thành công")


@router.post(
    "/cancel",
    response_model=ApiResponse[EmergencySessionResponse],
    summary="Hủy phiên báo động khẩn cấp (Người dùng an toàn / Bấm nhầm)",
)
async def cancel_emergency_sos(
    data: EmergencyCancelRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[EmergencySessionResponse]:
    """Hủy phiên khẩn cấp đang diễn ra và gửi tin báo an toàn All-Clear cho người thân."""
    session = await emergency_service.cancel_emergency(current_user.uid, data)
    return ApiResponse.ok(data=session, message="Đã hủy báo động khẩn cấp thành công")


@router.post(
    "/resolve",
    response_model=ApiResponse[EmergencySessionResponse],
    summary="Giải quyết / Kết thúc phiên khẩn cấp sau khi đã an toàn",
)
async def resolve_emergency_sos(
    data: EmergencyResolveRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[EmergencySessionResponse]:
    """Đánh dấu sự cố đã được xử lý xong và gửi thông báo All-Clear cho người thân."""
    session = await emergency_service.resolve_emergency(current_user.uid, data)
    return ApiResponse.ok(data=session, message="Đã giải quyết phiên khẩn cấp thành công")


@router.get(
    "/active",
    response_model=ApiResponse[Optional[EmergencySessionResponse]],
    summary="Kiểm tra phiên khẩn cấp đang kích hoạt của người dùng",
)
async def get_active_emergency(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Optional[EmergencySessionResponse]]:
    """Trả về chi tiết phiên đang ACTIVE hoặc null nếu người dùng đang an toàn."""
    active_session = await emergency_service.get_active_session(current_user.uid)
    return ApiResponse.ok(
        data=active_session,
        message="Lấy trạng thái khẩn cấp thành công"
        if active_session
        else "Người dùng hiện không có phiên khẩn cấp nào",
    )


@router.get(
    "/sessions",
    response_model=ApiResponse[List[EmergencySessionResponse]],
    summary="Lấy danh sách các phiên khẩn cấp lịch sử của người dùng",
)
async def list_emergency_sessions(
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[EmergencySessionResponse]]:
    """Trả về danh sách lịch sử các phiên SOS của tài khoản."""
    sessions = await emergency_service.list_user_sessions(current_user.uid, limit=limit)
    return ApiResponse.ok(data=sessions, message="Lấy lịch sử phiên khẩn cấp thành công")


@router.get(
    "/sessions/{session_id}",
    response_model=ApiResponse[EmergencySessionResponse],
    summary="Xem chi tiết một phiên khẩn cấp",
)
async def get_emergency_session_detail(
    session_id: str = Path(..., description="ID của phiên khẩn cấp"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[EmergencySessionResponse]:
    """Xem thông tin chi tiết một phiên khẩn cấp (kiểm tra quyền sở hữu)."""
    session = await emergency_service.get_session_by_id(current_user.uid, session_id)
    return ApiResponse.ok(data=session, message="Lấy thông tin phiên khẩn cấp thành công")
