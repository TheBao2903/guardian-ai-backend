"""
=============================================================================
FILE: app/modules/location/__init__.py
MODULE: Location
ROLE / RESPONSIBILITY:
    - Quản lý các mốc vị trí quan trọng (Location Checkpoints) khi có sự cố.
    - Lưu trữ có kiểm soát trong Firestore theo ADR-005 (không ghi telemetry tần số cao).

CONNECTIONS / DEPENDENCIES:
    - app/modules/location/router.py
    - app/modules/location/service.py
    - app/modules/location/repository.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""
