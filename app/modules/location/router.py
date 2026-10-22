"""
=============================================================================
FILE: app/modules/location/router.py
MODULE: Location - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint phục vụ quản lý mốc vị trí GPS (Checkpoints):
      + POST /api/v1/location/checkpoints: Ghi nhận một điểm mốc vị trí mới.
      + GET  /api/v1/location/latest: Lấy tọa độ mốc vị trí gần nhất của người dùng.
      + GET  /api/v1/location/checkpoints: Lấy danh sách lịch sử các điểm mốc vị trí.
    - Toàn bộ endpoints được bảo vệ bởi dependency xác thực Firebase ID Token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/location/service.py (LocationService)
    - app/modules/location/schemas.py (LocationCheckpointCreateRequest, LocationCheckpointResponse, LatestLocationResponse)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: LocationCheckpointCreateRequest, Query params.
    - Output: ApiResponse[LocationCheckpointResponse | LatestLocationResponse | List].
=============================================================================
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.location.schemas import (
    LatestLocationResponse,
    LocationCheckpointCreateRequest,
    LocationCheckpointResponse,
)
from app.modules.location.service import LocationService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
location_service = LocationService()


@router.post(
    "/checkpoints",
    response_model=ApiResponse[LocationCheckpointResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Ghi nhận mốc vị trí GPS quan trọng (SOS / Sự kiện nguy hiểm)",
)
async def create_location_checkpoint(
    data: LocationCheckpointCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[LocationCheckpointResponse]:
    """Ghi nhận một tọa độ checkpoint vào hệ thống."""
    checkpoint = await location_service.record_checkpoint(current_user.uid, data)
    return ApiResponse.ok(data=checkpoint, message="Ghi nhận mốc vị trí thành công")


@router.get(
    "/latest",
    response_model=ApiResponse[LatestLocationResponse],
    summary="Lấy mốc vị trí GPS gần nhất của người dùng",
)
async def get_my_latest_location(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[LatestLocationResponse]:
    """Trả về tọa độ và đường dẫn Google Maps của mốc vị trí mới nhất."""
    latest = await location_service.get_latest_location(current_user.uid)
    return ApiResponse.ok(data=latest, message="Lấy mốc vị trí gần nhất thành công")


@router.get(
    "/checkpoints",
    response_model=ApiResponse[List[LocationCheckpointResponse]],
    summary="Lấy danh sách các mốc vị trí GPS đã lưu",
)
async def list_my_checkpoints(
    session_id: Optional[str] = Query(None, description="Lọc theo ID phiên khẩn cấp nếu có"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[LocationCheckpointResponse]]:
    """Trả về danh sách các mốc vị trí theo thứ tự thời gian mới nhất."""
    checkpoints = await location_service.list_checkpoints(
        user_id=current_user.uid, session_id=session_id, limit=limit
    )
    return ApiResponse.ok(data=checkpoints, message="Lấy danh sách mốc vị trí thành công")
