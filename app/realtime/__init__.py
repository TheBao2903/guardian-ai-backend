"""
=============================================================================
FILE: app/realtime/__init__.py
MODULE: Realtime
ROLE / RESPONSIBILITY:
    - Module truyền thông thời gian thực qua WebSocket (FastAPI + asyncio theo ADR-007).
    - Phục vụ truyền nhận GPS stream và cập nhật trạng thái phiên khẩn cấp tức thời.

CONNECTIONS / DEPENDENCIES:
    - app/realtime/manager.py (ConnectionManager)
    - app/realtime/router.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""
