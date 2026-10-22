"""
=============================================================================
FILE: app/shared/enums/contact.py
MODULE: Shared - Emergency Contact Enums
ROLE / RESPONSIBILITY:
    - Định nghĩa các mối quan hệ gia đình / bạn bè cho danh bạ khẩn cấp.
    - Định nghĩa các kênh thông báo cảnh báo (ADR-015, ADR-016, ADR-035).

CONNECTIONS / DEPENDENCIES:
    - Sử dụng bởi: `app/modules/contacts/`, `app/modules/notifications/`, Schemas.

INPUT / OUTPUT:
    - Enums: ContactRelationship, NotificationChannel.
=============================================================================
"""

from enum import Enum


class ContactRelationship(str, Enum):
    """Mối quan hệ của người liên hệ khẩn cấp với chủ tài khoản."""
    PARENT = "PARENT"                           # Bố / Mẹ
    SPOUSE = "SPOUSE"                           # Vợ / Chồng
    CHILD = "CHILD"                             # Con cái
    SIBLING = "SIBLING"                         # Anh / Chị / Em
    PARTNER = "PARTNER"                         # Người yêu / Bạn đời
    FRIEND = "FRIEND"                           # Bạn bè thân thiết
    COLLEAGUE = "COLLEAGUE"                     # Đồng nghiệp
    DOCTOR = "DOCTOR"                           # Bác sĩ gia đình
    OTHER = "OTHER"                             # Mối quan hệ khác


class NotificationChannel(str, Enum):
    """Các kênh phân phối thông báo khẩn cấp trong hệ thống."""
    TELEGRAM = "TELEGRAM"                       # Kênh chính cho người thân: Telegram Bot API
    LOCAL_NOTIFICATION = "LOCAL_NOTIFICATION"   # Kênh chính cho người dùng: Native Local Notification
    DIRECT_PHONE_CALL = "DIRECT_PHONE_CALL"     # Gọi điện trực tiếp số ưu tiên trên thiết bị di động
    FCM_PUSH = "FCM_PUSH"                       # Kênh mở rộng: Firebase Cloud Messaging Push
    SMS = "SMS"                                 # Kênh mở rộng: Tin nhắn SMS viễn thông
