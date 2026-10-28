"""
=============================================================================
FILE: app/shared/schemas/location.py
MODULE: Shared - Location Schemas
ROLE / RESPONSIBILITY:
    - Định nghĩa cấu trúc dữ liệu tọa độ địa lý (GeoPoint).
    - Cung cấp hàm sinh đường dẫn Google Maps URL phục vụ gửi tin nhắn Telegram.
    - Đảm bảo tuân thủ ADR-005 (không ghi GPS tần số cao vào DB, chỉ lưu Checkpoint).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: Location module, Emergency module, Safety Check module, Telegram provider.

INPUT / OUTPUT:
    - GeoPointSchema: { latitude, longitude, accuracy_meters, captured_at, ... }.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OptionalCoordinatesRequest(BaseModel):
    """Accept no location, or one complete, finite coordinate pair."""
    model_config = ConfigDict(allow_inf_nan=False)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class GeoPointSchema(BaseModel):
    """Mô hình dữ liệu vị trí địa lý chuẩn hóa."""
    model_config = ConfigDict(allow_inf_nan=False)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Vĩ độ (-90 đến 90)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Kinh độ (-180 đến 180)")
    accuracy_meters: Optional[float] = Field(None, ge=0.0, description="Bán kính sai số theo mét")
    altitude: Optional[float] = Field(None, description="Độ cao so với mực nước biển")
    speed: Optional[float] = Field(None, ge=0.0, description="Tốc độ di chuyển (m/s)")
    heading: Optional[float] = Field(None, ge=0.0, le=360.0, description="Hướng di chuyển (độ)")
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Thời điểm ghi nhận tọa độ (UTC)",
    )

    def to_google_maps_url(self) -> str:
        """Sinh đường dẫn Google Maps ghim vị trí chuẩn."""
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"

    @property
    def maps_url(self) -> str:
        """Property tiện ích sinh đường dẫn Google Maps."""
        return self.to_google_maps_url()

    def to_display_string(self) -> str:
        """Chuỗi hiển thị ngắn gọn tọa độ."""
        return f"({self.latitude:.6f}, {self.longitude:.6f})"
