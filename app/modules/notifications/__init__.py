"""
=============================================================================
FILE: app/modules/notifications/__init__.py
MODULE: Notifications
ROLE / RESPONSIBILITY:
    - Cung cấp kiến trúc phát tán cảnh báo khẩn cấp đa kênh (Multi-channel Notification System).
    - Hỗ trợ Telegram Bot Provider là kênh thông báo người thân chính (ADR-016).
    - Thiết kế extensible sẵn sàng tích hợp FCM Push, SMS trong tương lai (ADR-015).

CONNECTIONS / DEPENDENCIES:
    - app/modules/notifications/providers/
    - app/modules/notifications/service.py
    - app/modules/notifications/schemas.py

INPUT / OUTPUT:
    - Package exports.
=============================================================================
"""
