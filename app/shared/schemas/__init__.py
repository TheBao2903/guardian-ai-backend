"""
=============================================================================
FILE: app/shared/schemas/__init__.py
MODULE: Shared - Schemas Package
ROLE / RESPONSIBILITY:
    - Re-export toàn bộ Schemas dùng chung của hệ thống Guardian AI.

CONNECTIONS / DEPENDENCIES:
    - app/shared/schemas/envelope.py
    - app/shared/schemas/location.py
    - app/shared/schemas/detection_signal.py

INPUT / OUTPUT:
    - Expose ApiResponse, PaginatedResponse, GeoPointSchema, DetectionSignal.
=============================================================================
"""

from app.shared.schemas.detection_signal import DetectionSignal
from app.shared.schemas.envelope import ApiResponse, PaginatedResponse
from app.shared.schemas.location import GeoPointSchema

__all__ = [
    "ApiResponse",
    "PaginatedResponse",
    "GeoPointSchema",
    "DetectionSignal",
]
