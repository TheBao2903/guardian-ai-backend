"""
=============================================================================
FILE: app/modules/recordings/schemas.py
MODULE: Recordings - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc quản lý metadata của các đoạn ghi âm bằng chứng khẩn cấp:
      + Thông tin file (tên, kích thước, định dạng, độ dài thời gian).
      + Khóa lưu trữ trên Cloudflare R2 (Storage Key).
      + Đường link URL có chữ ký bảo mật (Presigned Playback URL) cho phép nghe lại.
      + Clip-specific metadata cho audio event clips (event_type, confidence, pre/post roll).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/recordings/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: RecordingMetadataResponse, PresignedAudioUrlResponse.
=============================================================================
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class RecordingMetadataResponse(BaseModel):
    """Metadata thông tin đoạn ghi âm bằng chứng khẩn cấp."""
    recording_id: str = Field(..., description="Mã định danh duy nhất của bản ghi âm (UUID)")
    user_id: str = Field(..., description="Firebase UID của người dùng")
    event_id: Optional[str] = Field(None, description="Mã sự kiện khẩn cấp liên kết (nếu có)")
    session_id: Optional[str] = Field(None, description="Mã phiên SOS liên kết (nếu có)")
    file_name: str = Field(..., description="Tên file gốc hoặc định dạng chuẩn")
    storage_key: str = Field(..., description="Đường dẫn lưu trữ trên Cloudflare R2")
    duration_seconds: Optional[float] = Field(None, description="Thời lượng bản ghi âm (giây)")
    file_size_bytes: int = Field(..., description="Dung lượng file tính theo bytes")
    content_type: str = Field("audio/webm", description="MIME type của file âm thanh")
    created_at: Optional[Any] = Field(None, description="Thời điểm upload file")
    # Clip-specific fields
    event_type: Optional[str] = Field(None, description="Loại sự kiện: SCREAM, DISTRESS_CRY, GUNSHOT...")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Độ tin cậy của detector (0.0-1.0)")
    pre_event_seconds: Optional[float] = Field(None, description="Thời lượng pre-roll (giây)")
    post_event_seconds: Optional[float] = Field(None, description="Thời lượng post-roll (giây)")
    upload_status: Optional[str] = Field(None, description="Trạng thái upload: pending, uploading, uploaded, failed")


class PresignedAudioUrlResponse(BaseModel):
    """Thông tin đường dẫn phát lại file ghi âm bằng chứng có chữ ký bảo mật."""
    recording_id: str = Field(..., description="Mã bản ghi âm")
    playback_url: str = Field(..., description="Đường dẫn phát lại có chữ ký bảo mật thời hạn")
    expires_in_seconds: int = Field(3600, description="Thời gian hiệu lực của liên kết (giây)")
