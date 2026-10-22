"""
=============================================================================
FILE: app/modules/recordings/__init__.py
MODULE: Recordings
ROLE / RESPONSIBILITY:
    - Module quản lý các đoạn ghi âm bằng chứng khẩn cấp (Emergency Audio Recordings).
    - Lưu trữ metadata trong Firestore và binary audio trên Cloudflare R2 (ADR-006).

CONNECTIONS / DEPENDENCIES:
    - app/modules/recordings/router.py
    - app/modules/recordings/service.py
    - app/modules/recordings/repository.py
    - app/infrastructure/storage/r2/client.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""
