"""
=============================================================================
FILE: app/modules/emergency/__init__.py
MODULE: Emergency
ROLE / RESPONSIBILITY:
    - Module trung tâm điều phối phản ứng khẩn cấp (Emergency Core Workflow).
    - Quản lý vòng đời phiên khẩn cấp (Emergency Session Lifecycle).
    - Cung cấp cơ chế chống trùng lặp Idempotent khi bấm nút SOS liên tục.
    - Xâu chuỗi pipeline: Kích hoạt -> Ghi vị trí -> Lấy danh bạ -> Gửi cảnh báo Telegram -> Stream WebSocket.

CONNECTIONS / DEPENDENCIES:
    - app/modules/emergency/router.py
    - app/modules/emergency/service.py
    - app/modules/emergency/repository.py
    - app/modules/emergency/schemas.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""
