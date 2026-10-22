"""
=============================================================================
FILE: app/modules/notifications/providers/base.py
MODULE: Notifications - Base Notification Provider Interface
ROLE / RESPONSIBILITY:
    - Định nghĩa lớp cơ sở trừu tượng (Abstract Base Class) cho tất cả các nhà cung cấp thông báo.
    - Đảm bảo tính mở rộng (Open/Closed Principle - ADR-015, ADR-016):
      Có thể bổ sung FCM Push, Twilio SMS, Zalo ZNS mà không cần sửa đổi Emergency Service.
    - Định nghĩa các hành động cảnh báo chuẩn: SOS Alert, Safety Check Timeout, All-Clear và Audio Evidence.

CONNECTIONS / DEPENDENCIES:
    - app/modules/notifications/schemas.py (SosAlertPayload, SafetyCheckAlertPayload, AllClearPayload, NotificationResult)
    - Kế thừa bởi: `TelegramBotProvider`, `FcmPushProvider`...

INPUT / OUTPUT:
    - Input: recipient string, alert payloads.
    - Output: NotificationResult.
=============================================================================
"""

from abc import ABC, abstractmethod

from app.modules.notifications.schemas import (
    AllClearPayload,
    NotificationResult,
    SafetyCheckAlertPayload,
    SosAlertPayload,
)


class BaseNotificationProvider(ABC):
    """Giao diện chuẩn cho tất cả các kênh thông báo khẩn cấp."""

    @abstractmethod
    async def send_sos_alert(self, recipient: str, payload: SosAlertPayload) -> NotificationResult:
        """Gửi cảnh báo SOS khẩn cấp tới người nhận."""
        pass

    @abstractmethod
    async def send_safety_check_alert(
        self, recipient: str, payload: SafetyCheckAlertPayload
    ) -> NotificationResult:
        """Gửi cảnh báo quá hạn kiểm tra an toàn."""
        pass

    @abstractmethod
    async def send_all_clear(self, recipient: str, payload: AllClearPayload) -> NotificationResult:
        """Gửi thông báo người dùng đã an toàn / hủy báo động."""
        pass

    @abstractmethod
    async def send_audio_evidence(
        self, recipient: str, audio_bytes: bytes, filename: str, caption: str
    ) -> NotificationResult:
        """Gửi file âm thanh bằng chứng ghi âm qua tin nhắn thoại/tệp đính kèm."""
        pass

    @abstractmethod
    async def send_text(self, recipient: str, text: str) -> NotificationResult:
        """Gửi tin nhắn văn bản thông thường / thử nghiệm."""
        pass
