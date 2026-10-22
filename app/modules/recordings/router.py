"""
=============================================================================
FILE: app/modules/recordings/router.py
MODULE: Recordings - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint phục vụ quản lý file ghi âm bằng chứng khẩn cấp:
      + POST   /api/v1/recordings/upload: Upload file audio từ thiết bị di động (Flutter app).
      + GET    /api/v1/recordings: Danh sách các đoạn ghi âm bằng chứng của tài khoản.
      + GET    /api/v1/recordings/{recording_id}: Xem thông tin metadata của bản ghi âm.
      + GET    /api/v1/recordings/{recording_id}/playback-url: Lấy presigned URL để nghe lại.
      + DELETE /api/v1/recordings/{recording_id}: Xóa bản ghi âm khỏi Cloudflare R2 và Firestore.
    - Toàn bộ endpoints được bảo vệ bởi dependency xác thực Firebase ID Token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/recordings/service.py (RecordingService)
    - app/modules/recordings/schemas.py (RecordingMetadataResponse, PresignedAudioUrlResponse)
    - app/shared/schemas/envelope import ApiResponse

INPUT / OUTPUT:
    - Input: Multipart UploadFile, Form fields, Query params.
    - Output: ApiResponse[RecordingMetadataResponse | PresignedAudioUrlResponse | List | Dict].
=============================================================================
"""

from functools import lru_cache
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.recordings.schemas import PresignedAudioUrlResponse, RecordingMetadataResponse
from app.modules.recordings.service import RecordingService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
@lru_cache(maxsize=1)
def get_recording_service():
    return RecordingService()


@router.post(
    "/upload",
    response_model=ApiResponse[RecordingMetadataResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Tải lên file ghi âm bằng chứng khẩn cấp (Upload Multipart)",
)
async def upload_recording(
    file: UploadFile = File(..., description="File âm thanh ghi âm từ thiết bị"),
    event_id: Optional[str] = Form(None, description="Mã sự kiện khẩn cấp liên kết nếu có"),
    session_id: Optional[str] = Form(None, description="Mã phiên SOS liên kết nếu có"),
    event_type: Optional[str] = Form(None, description="Loại sự kiện: SCREAM, DISTRESS_CRY, GUNSHOT..."),
    confidence: Optional[float] = Form(None, ge=0.0, le=1.0, description="Độ tin cậy của detector (0.0-1.0)"),
    pre_event_seconds: Optional[float] = Form(None, ge=0.0, le=5.0, description="Thời lượng pre-roll (tối đa 5s)"),
    post_event_seconds: Optional[float] = Form(None, ge=0.0, le=5.0, description="Thời lượng post-roll (tối đa 5s)"),
    duration_seconds: Optional[float] = Form(None, description="Thời lượng bản ghi (giây)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[RecordingMetadataResponse]:
    """
    Tiếp nhận stream âm thanh, đẩy vào Cloudflare R2 và lưu metadata vào Firestore.

    Hỗ trợ clip metadata cho audio event clips:
    - event_id: Định danh duy nhất của sự kiện (dùng cho idempotency)
    - session_id: Phiên SOS liên kết
    - event_type: Loại sự kiện (SCREAM, DISTRESS_CRY, GUNSHOT...)
    - confidence: Độ tin cậy của detector
    - pre/post_event_seconds: Thời lượng pre-roll và post-roll
    """
    audio_content = await file.read()
    content_type = file.content_type or "audio/webm"
    original_filename = file.filename or "recording.webm"

    result = await get_recording_service().upload_audio_recording(
        user_id=current_user.uid,
        audio_bytes=audio_content,
        original_filename=original_filename,
        content_type=content_type,
        event_id=event_id,
        session_id=session_id,
        event_type=event_type,
        confidence=confidence,
        pre_event_seconds=pre_event_seconds,
        post_event_seconds=post_event_seconds,
        duration_seconds=duration_seconds,
    )
    return ApiResponse.ok(data=result, message="Tải lên bản ghi âm bằng chứng thành công")


@router.get(
    "",
    response_model=ApiResponse[List[RecordingMetadataResponse]],
    summary="Lấy danh sách các đoạn ghi âm bằng chứng của người dùng",
)
async def list_my_recordings(
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi tối đa"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[RecordingMetadataResponse]]:
    """Trả về danh sách metadata các file ghi âm của người dùng, sắp xếp mới nhất lên đầu."""
    recordings = await get_recording_service().list_recordings(current_user.uid, limit=limit)
    return ApiResponse.ok(data=recordings, message="Lấy danh sách bản ghi âm thành công")


@router.get(
    "/{recording_id}",
    response_model=ApiResponse[RecordingMetadataResponse],
    summary="Xem metadata chi tiết của một bản ghi âm",
)
async def get_recording_detail(
    recording_id: str = Path(..., description="ID của bản ghi âm"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[RecordingMetadataResponse]:
    """Xem thông tin chi tiết một bản ghi âm (kiểm tra quyền sở hữu)."""
    rec = await get_recording_service().get_recording(current_user.uid, recording_id)
    return ApiResponse.ok(data=rec, message="Lấy thông tin bản ghi âm thành công")


@router.get(
    "/{recording_id}/playback-url",
    response_model=ApiResponse[PresignedAudioUrlResponse],
    summary="Lấy đường dẫn URL có chữ ký bảo mật (Presigned) để nghe lại file âm thanh",
)
async def get_recording_playback_url(
    recording_id: str = Path(..., description="ID của bản ghi âm"),
    expires_in: int = Query(3600, ge=60, le=86400, description="Thời gian hiệu lực URL (giây)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[PresignedAudioUrlResponse]:
    """Sinh link presigned URL thời hạn để nghe lại file âm thanh trên Cloudflare R2."""
    playback = await get_recording_service().get_playback_url(
        user_id=current_user.uid,
        recording_id=recording_id,
        expires_in=expires_in,
    )
    return ApiResponse.ok(data=playback, message="Sinh URL phát lại bản ghi âm thành công")


@router.delete(
    "/{recording_id}",
    response_model=ApiResponse[Dict[str, str]],
    summary="Xóa vĩnh viễn bản ghi âm khỏi Cloudflare R2 và Firestore",
)
async def delete_recording(
    recording_id: str = Path(..., description="ID của bản ghi âm"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Dict[str, str]]:
    """Xóa file binary trên Cloudflare R2 và xóa metadata trong Firestore."""
    await get_recording_service().delete_recording(current_user.uid, recording_id)
    return ApiResponse.ok(
        data={"recording_id": recording_id},
        message="Đã xóa bản ghi âm bằng chứng thành công",
    )
