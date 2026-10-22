"""
=============================================================================
FILE: app/modules/location/schemas.py
MODULE: Location - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc ghi nhận và truy vấn các điểm chốt vị trí GPS (Checkpoints).
    - Tích hợp với `GeoPointSchema` và tự động sinh link Google Maps ghim vị trí.
    - Phân loại lý do ghi nhận tọa độ (`trigger_reason`) để phục vụ cứu hộ và điều tra.

CONNECTIONS / DEPENDENCIES:
    - app/shared/schemas/location.py (GeoPointSchema)
    - Sử dụng bởi: `app/modules/location/router.py`, `service.py`, `repository.py`.

INPUT / OUTPUT:
    - DTOs: LocationCheckpointCreateRequest, LocationCheckpointResponse, LatestLocationResponse.
=============================================================================
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.shared.schemas.location import GeoPointSchema


class LocationCheckpointCreateRequest(BaseModel):
    """Payload ghi nhận một mốc tọa độ GPS quan trọng."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Vĩ độ")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Kinh độ")
    accuracy_meters: Optional[float] = Field(None, ge=0.0, description="Bán kính sai số (m)")
    altitude: Optional[float] = Field(None, description="Độ cao so với mực nước biển (m)")
    speed: Optional[float] = Field(None, ge=0.0, description="Vận tốc di chuyển (m/s)")
    heading: Optional[float] = Field(None, ge=0.0, le=360.0, description="Hướng di chuyển (độ)")
    trigger_reason: str = Field(
        "MANUAL_CHECKPOINT",
        description="Lý do ghi nhận (SOS_TRIGGERED, SAFETY_CHECK_TIMEOUT, AI_AUDIO_SCREAM, MANUAL_CHECKPOINT)",
    )
    session_id: Optional[str] = Field(None, description="ID phiên khẩn cấp liên kết nếu có")
    address_text: Optional[str] = Field(None, description="Địa chỉ ước tính gần đúng nếu có")


class LocationCheckpointResponse(BaseModel):
    """Chi tiết một điểm mốc vị trí GPS đã lưu."""
    id: str = Field(..., description="Mã định danh duy nhất của checkpoint (UUID)")
    user_id: str = Field(..., description="Firebase UID của người dùng")
    session_id: Optional[str] = Field(None, description="Mã phiên khẩn cấp liên kết")
    trigger_reason: str = Field(..., description="Lý do ghi nhận mốc tọa độ")
    location: GeoPointSchema = Field(..., description="Tọa độ GPS chi tiết")
    maps_url: str = Field(..., description="Đường dẫn Google Maps ghim vị trí")
    address_text: Optional[str] = Field(None, description="Địa chỉ hoặc ghi chú vị trí")
    created_at: Optional[Any] = Field(None, description="Thời điểm ghi nhận")


class LatestLocationResponse(BaseModel):
    """Vị trí GPS mới nhất ghi nhận được của người dùng."""
    user_id: str = Field(..., description="Firebase UID")
    location: GeoPointSchema = Field(..., description="Tọa độ GPS mới nhất")
    maps_url: str = Field(..., description="Đường dẫn Google Maps")
    trigger_reason: str = Field(..., description="Lý do của mốc tọa độ gần nhất")
    created_at: Optional[Any] = Field(None, description="Thời điểm ghi nhận gần nhất")
