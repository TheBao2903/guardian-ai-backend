"""
=============================================================================
FILE: app/modules/location/service.py
MODULE: Location - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối nghiệp vụ ghi nhận và trích xuất các mốc vị trí quan trọng:
      + Nhận yêu cầu tạo checkpoint từ client hoặc từ các luồng khẩn cấp nội bộ (SOS, AI detection).
      + Chuẩn hóa tọa độ thành `GeoPointSchema` và sinh URL Google Maps.
      + Lưu trữ mốc tọa độ vào Firestore.
      + Cung cấp vị trí mới nhất cho màn hình theo dõi và thông báo Telegram.

CONNECTIONS / DEPENDENCIES:
    - app/modules/location/repository.py (LocationRepository)
    - app/modules/location/schemas.py (LocationCheckpointCreateRequest, LocationCheckpointResponse, LatestLocationResponse)
    - app/shared/schemas/location.py (GeoPointSchema)
    - app/core/exceptions.py (EntityNotFoundException)

INPUT / OUTPUT:
    - Input: user_id, LocationCheckpointCreateRequest.
    - Output: LocationCheckpointResponse, LatestLocationResponse, List[LocationCheckpointResponse].
=============================================================================
"""

import uuid
from typing import List, Optional

from app.core.exceptions import EntityNotFoundException
from app.modules.location.repository import LocationRepository
from app.modules.location.schemas import (
    LatestLocationResponse,
    LocationCheckpointCreateRequest,
    LocationCheckpointResponse,
)
from app.shared.schemas.location import GeoPointSchema


class LocationService:
    """Service điều phối nghiệp vụ vị trí và mốc tọa độ khẩn cấp."""

    def __init__(self, repository: Optional[LocationRepository] = None) -> None:
        self.repository = repository or LocationRepository()

    def _to_checkpoint_response(self, raw: dict) -> LocationCheckpointResponse:
        """Chuyển đổi dữ liệu thô sang DTO chuẩn."""
        loc_dict = raw.get("location", {})
        geo_point = GeoPointSchema(
            latitude=loc_dict.get("latitude", 0.0),
            longitude=loc_dict.get("longitude", 0.0),
            accuracy_meters=loc_dict.get("accuracy_meters"),
            altitude=loc_dict.get("altitude"),
            speed=loc_dict.get("speed"),
            heading=loc_dict.get("heading"),
            captured_at=loc_dict.get("captured_at") or raw.get("created_at"),
        )
        return LocationCheckpointResponse(
            id=raw["id"],
            user_id=raw["user_id"],
            session_id=raw.get("session_id"),
            trigger_reason=raw.get("trigger_reason", "MANUAL_CHECKPOINT"),
            location=geo_point,
            maps_url=geo_point.to_google_maps_url(),
            address_text=raw.get("address_text"),
            created_at=raw.get("created_at"),
        )

    async def record_checkpoint(
        self, user_id: str, request: LocationCheckpointCreateRequest
    ) -> LocationCheckpointResponse:
        """Ghi nhận một điểm mốc vị trí GPS mới."""
        checkpoint_id = str(uuid.uuid4())
        geo_point = GeoPointSchema(
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy_meters=request.accuracy_meters,
            altitude=request.altitude,
            speed=request.speed,
            heading=request.heading,
        )

        data = {
            "id": checkpoint_id,
            "user_id": user_id,
            "session_id": request.session_id,
            "trigger_reason": request.trigger_reason,
            "location": geo_point.model_dump(),
            "address_text": request.address_text,
        }

        saved = self.repository.create(checkpoint_id, data)
        return self._to_checkpoint_response(saved)

    async def get_latest_location(self, user_id: str) -> LatestLocationResponse:
        """Lấy mốc vị trí GPS gần nhất của người dùng."""
        raw = self.repository.get_latest_by_user(user_id)
        if not raw:
            raise EntityNotFoundException(f"Chưa có mốc vị trí nào được ghi nhận cho người dùng: {user_id}")

        loc_dict = raw.get("location", {})
        geo_point = GeoPointSchema(
            latitude=loc_dict.get("latitude", 0.0),
            longitude=loc_dict.get("longitude", 0.0),
            accuracy_meters=loc_dict.get("accuracy_meters"),
            altitude=loc_dict.get("altitude"),
            speed=loc_dict.get("speed"),
            heading=loc_dict.get("heading"),
            captured_at=loc_dict.get("captured_at") or raw.get("created_at"),
        )

        return LatestLocationResponse(
            user_id=user_id,
            location=geo_point,
            maps_url=geo_point.to_google_maps_url(),
            trigger_reason=raw.get("trigger_reason", "UNKNOWN"),
            created_at=raw.get("created_at"),
        )

    async def list_checkpoints(
        self, user_id: str, session_id: Optional[str] = None, limit: int = 50
    ) -> List[LocationCheckpointResponse]:
        """Lấy danh sách các mốc vị trí của người dùng."""
        raw_list = self.repository.list_by_user(user_id=user_id, session_id=session_id, limit=limit)
        return [self._to_checkpoint_response(item) for item in raw_list]
