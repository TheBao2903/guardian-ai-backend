"""
=============================================================================
FILE: app/modules/detection/router.py
MODULE: Detection - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint phục vụ tầng nhận diện âm thanh và thẩm định rủi ro:
      + POST /api/v1/detection/signals: Tiếp nhận các tín hiệu phát hiện âm thanh từ On-device AI.
      + POST /api/v1/detection/analyze-audio: Tiếp nhận đoạn âm thanh thô/đặc trưng để Server phân tích.
      + GET  /api/v1/detection/config: Truy vấn thông số cấu hình ngưỡng và các model AI khả dụng.
      + GET  /api/v1/detection/history: Lấy lịch sử các biến cố âm thanh đã ghi nhận của người dùng.
    - Bảo vệ nghiêm ngặt bằng dependency xác thực Firebase ID Token.
    - Tuân thủ ADR-009, ADR-010, ADR-014.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/detection/service.py (DetectionService)
    - app/modules/detection/schemas.py
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: DTO Requests.
    - Output: ApiResponse[DetectionIngestResponse | DetectionConfigResponse | List[DetectionEventRecordResponse]].
=============================================================================
"""

from typing import List
from fastapi import APIRouter, Depends, Query, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.detection.schemas import (
    AudioAnalyzeRequest,
    DetectionConfigResponse,
    DetectionEventRecordResponse,
    DetectionIngestResponse,
    DetectionSignalIngestRequest,
)
from app.modules.detection.service import DetectionService
from app.shared.schemas.envelope import ApiResponse

from app.modules.detection.alerts.router import router as alerts_router

router = APIRouter()
router.include_router(alerts_router)
detection_service = DetectionService()


@router.post(
    "/signals",
    response_model=ApiResponse[DetectionIngestResponse],
    status_code=status.HTTP_200_OK,
    summary="Tiếp nhận tín hiệu nhận diện âm thanh từ Client/Edge AI",
)
async def ingest_detection_signals(
    data: DetectionSignalIngestRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[DetectionIngestResponse]:
    """
    Tiếp nhận danh sách các frame nhận diện âm thanh từ On-device model (YAMNet/VocalBurst),
    tổng hợp qua cửa sổ trượt Temporal Aggregation để chống báo động giả, và tự động kích hoạt
    quy trình SOS khẩn cấp nếu phát hiện âm thanh nguy cấp thực sự (Scream, Gunshot...).
    """
    res = await detection_service.ingest_signals(current_user.uid, data)
    return ApiResponse.ok(data=res, message=res.message)


@router.post(
    "/analyze-audio",
    response_model=ApiResponse[DetectionIngestResponse],
    status_code=status.HTTP_200_OK,
    summary="Gửi đoạn âm thanh thô hoặc đặc trưng để Server AI phân loại",
)
async def analyze_audio_segment(
    data: AudioAnalyzeRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[DetectionIngestResponse]:
    """
    Phân tích đoạn âm thanh dạng base64 hoặc vector đặc trưng bằng các mô hình Backend AI
    (Google YAMNet và VocalBurst Scream Detector).
    """
    res = await detection_service.analyze_audio(current_user.uid, data)
    return ApiResponse.ok(data=res, message=res.message)


@router.get(
    "/config",
    response_model=ApiResponse[DetectionConfigResponse],
    summary="Lấy thông số cấu hình và danh sách Detector Models",
)
async def get_detection_configuration(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[DetectionConfigResponse]:
    """Trả về các ngưỡng quyết định rủi ro, độ rộng cửa sổ thời gian và thời gian giãn cách Cooldown."""
    cfg = detection_service.get_config()
    return ApiResponse.ok(data=cfg, message="Lấy cấu hình thành công")


@router.get(
    "/history",
    response_model=ApiResponse[List[DetectionEventRecordResponse]],
    summary="Lấy lịch sử phát hiện âm thanh của người dùng",
)
async def get_detection_history(
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[DetectionEventRecordResponse]]:
    """Truy vấn các sự kiện âm thanh bất thường đã được hệ thống ghi nhận gần đây."""
    history = detection_service.list_history(current_user.uid, limit=limit)
    return ApiResponse.ok(data=history, message="Lấy lịch sử phát hiện thành công")
