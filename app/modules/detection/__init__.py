"""
=============================================================================
FILE: app/modules/detection/__init__.py
MODULE: Detection Package
ROLE / RESPONSIBILITY:
    - Khởi tạo package cho Module Nhận diện âm thanh bất thường và Thẩm định rủi ro
      (AI Audio Detection & Decision Layer).
    - Cung cấp Router, Service, Repository, Schemas và Detectors.

CONNECTIONS / DEPENDENCIES:
    - app/modules/detection/router.py
    - app/modules/detection/service.py
    - app/modules/detection/schemas.py
    - app/modules/detection/repository.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""

from app.modules.detection.router import router as detection_router
from app.modules.detection.service import DetectionService

__all__ = ["detection_router", "DetectionService"]
