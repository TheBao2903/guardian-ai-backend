"""
=============================================================================
FILE: app/modules/notifications/service.py
MODULE: Notifications - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối phát tán thông báo khẩn cấp tới danh bạ người thân:
      + Phân phối tin nhắn theo các kênh đăng ký của từng contact (Telegram, v.v.).
      + Gửi cảnh báo SOS đồng loạt cho tất cả các liên hệ đang hoạt động (`is_active=True`).
      + Gửi cảnh báo quá hạn Safety Check khi hết Grace Period.
      + Gửi thông báo an toàn All-Clear khi người dùng hủy phiên hoặc nhập PIN giải cứu.
      + Kiểm tra kết nối Telegram Bot qua tin nhắn thử nghiệm.
      + Lưu vết kiểm toán lịch sử thông báo vào Firestore collection `notifications`.

CONNECTIONS / DEPENDENCIES:
    - app/modules/notifications/providers/base.py (BaseNotificationProvider)
    - app/modules/notifications/providers/telegram.py (TelegramBotProvider)
    - app/modules/notifications/schemas.py (SosAlertPayload, SafetyCheckAlertPayload, AllClearPayload, NotificationResult)
    - app/modules/contacts/schemas.py (ContactResponse)
    - app/infrastructure/firestore/client.py (get_firestore_client)

INPUT / OUTPUT:
    - Input: Contacts list, Alert payloads.
    - Output: List[NotificationResult].
=============================================================================
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from starlette.concurrency import run_in_threadpool
from google.cloud.firestore import Client as FirestoreClient

from app.core.config import get_settings
from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client
from app.modules.contacts.schemas import ContactResponse
from app.modules.notifications.providers.base import BaseNotificationProvider
from app.modules.notifications.providers.telegram import TelegramBotProvider
from app.modules.notifications.schemas import (
    AllClearPayload,
    DuressAlertPayload,
    NotificationResult,
    SafetyCheckAlertPayload,
    SosAlertPayload,
)
from app.shared.enums.contact import NotificationChannel


class NotificationService:
    """Service điều phối phát tán cảnh báo khẩn cấp đa kênh."""

    def __init__(
        self,
        telegram_provider: Optional[BaseNotificationProvider] = None,
        db: Optional[FirestoreClient] = None,
    ) -> None:
        self.telegram_provider = telegram_provider or TelegramBotProvider()
        self.db = db or get_firestore_client()
        self.notifications_collection = self.db.collection("notifications")

    def _log_notification_audit(self, user_id: str, alert_type: str, result: NotificationResult) -> None:
        """Lưu vết kiểm toán thông báo vào Firestore."""
        try:
            doc_ref = self.notifications_collection.document()
            doc_ref.set({
                "id": doc_ref.id,
                "user_id": user_id,
                "alert_type": alert_type,
                "channel": result.channel.value,
                "recipient": result.recipient,
                "success": result.success,
                "message_id": result.message_id,
                "error_message": result.error_message,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.warning(f"Lỗi khi lưu audit notification vào Firestore: {str(e)}")

    async def broadcast_sos(
        self, user_id: str, contacts: List[ContactResponse], payload: SosAlertPayload
    ) -> List[NotificationResult]:
        """Gửi cảnh báo SOS khẩn cấp tới danh bạ người thân đang kích hoạt (Tối đa 10 liên hệ theo ADR-036)."""
        settings = get_settings()
        eligible = [c for c in contacts if c.is_active and c.telegram_id][: settings.MAX_EMERGENCY_CONTACTS_PER_USER]

        async def _send_single(contact: ContactResponse) -> NotificationResult:
            res = await self.telegram_provider.send_sos_alert(contact.telegram_id, payload)
            await run_in_threadpool(self._log_notification_audit, user_id, "SOS_ALERT", res)
            return res

        if not eligible:
            return []

        results = await asyncio.gather(*[_send_single(c) for c in eligible])
        return list(results)

    async def broadcast_safety_check_timeout(
        self, user_id: str, contacts: List[ContactResponse], payload: SafetyCheckAlertPayload
    ) -> List[NotificationResult]:
        """Gửi thông báo quá hạn hẹn giờ an toàn tới người thân (Tối đa 10 liên hệ theo ADR-036)."""
        settings = get_settings()
        eligible = [c for c in contacts if c.is_active and c.telegram_id][: settings.MAX_EMERGENCY_CONTACTS_PER_USER]

        async def _send_single(contact: ContactResponse) -> NotificationResult:
            res = await self.telegram_provider.send_safety_check_alert(contact.telegram_id, payload)
            await run_in_threadpool(self._log_notification_audit, user_id, "SAFETY_CHECK_TIMEOUT", res)
            return res

        if not eligible:
            return []

        results = await asyncio.gather(*[_send_single(c) for c in eligible])
        return list(results)

    async def broadcast_all_clear(
        self, user_id: str, contacts: List[ContactResponse], payload: AllClearPayload
    ) -> List[NotificationResult]:
        """Gửi thông báo đã an toàn tới người thân (Tối đa 10 liên hệ theo ADR-036)."""
        settings = get_settings()
        eligible = [c for c in contacts if c.is_active and c.telegram_id][: settings.MAX_EMERGENCY_CONTACTS_PER_USER]

        async def _send_single(contact: ContactResponse) -> NotificationResult:
            res = await self.telegram_provider.send_all_clear(contact.telegram_id, payload)
            await run_in_threadpool(self._log_notification_audit, user_id, "ALL_CLEAR", res)
            return res

        if not eligible:
            return []

        results = await asyncio.gather(*[_send_single(c) for c in eligible])
        return list(results)

    async def test_telegram_channel(self, telegram_id: str, custom_text: Optional[str] = None) -> NotificationResult:
        """Kiểm tra hoạt động của bot Telegram tới một chat ID cụ thể."""
        text = custom_text or (
            "🔔 <b>THÔNG BÁO THỬ NGHIỆM TỪ GUARDIAN AI</b> 🔔\n\n"
            "Hệ thống cảnh báo an toàn cá nhân của bạn đã kết nối thành công với Telegram Bot này!\n"
            "Khi có tình huống khẩn cấp, vị trí GPS và cảnh báo sẽ được tự động gửi vào đây."
        )
        return await self.telegram_provider.send_text(telegram_id, text)

    async def broadcast_duress_alert(
        self, user_id: str, contacts: List[ContactResponse], payload: DuressAlertPayload
    ) -> List[NotificationResult]:
        """Gửi cảnh báo DURESS_COERCION tới tất cả người thân.

        Phân biệt với broadcast_all_clear: Thay vì "Đã an toàn", gửi cảnh báo
        TỐI KHẨN "BỊ ÉP BUỘC! CẦN ỨNG CỨU!" kèm khuyến nghị gọi 113.

        Ngữ cảnh kích hoạt (PLAN_PIN_VERIFICATION_OVERHAUL.md):
        - User nhập Duress PIN thay vì Safe PIN khi bị kẻ xấu ép buộc.
        - Hệ thống tắt UI cảnh báo để không kích động kẻ xấu,
          nhưng GỌI NGAY tới người thân + công an.
        """
        settings = get_settings()
        eligible = [c for c in contacts if c.is_active and c.telegram_id][: settings.MAX_EMERGENCY_CONTACTS_PER_USER]

        async def _send_single(contact: ContactResponse) -> NotificationResult:
            res = await self.telegram_provider.send_duress_alert(contact.telegram_id, payload)
            await run_in_threadpool(self._log_notification_audit, user_id, "DURESS_COERCION", res)
            return res

        if not eligible:
            logger.warning(f"Không có liên hệ nào để gửi DURESS alert cho user {user_id}")
            return []

        results = await asyncio.gather(*[_send_single(c) for c in eligible])
        logger.warning(
            f"🚨 Đã gửi cảnh báo DURESS_COERCION tới {len(eligible)} người thân cho user {user_id}"
        )
        return list(results)

    async def broadcast_audio_evidence(
        self,
        user_id: str,
        contacts: List[ContactResponse],
        audio_bytes: bytes,
        filename: str = "evidence.ogg",
        caption: str = "Bằng chứng âm thanh khẩn cấp",
    ) -> List[NotificationResult]:
        """
        Gửi audio evidence CHỈ tới 3 người ưu tiên cao nhất (priority 1, 2, 3).
        Được gọi sau khi file audio đã upload lên R2 thành công.
        """
        # Sắp xếp theo priority và lấy top 3
        eligible = [c for c in contacts if c.is_active and c.telegram_id]
        sorted_contacts = sorted(eligible, key=lambda c: c.priority)
        top_3 = sorted_contacts[:3]

        async def _send_audio(contact: ContactResponse) -> NotificationResult:
            res = await self.telegram_provider.send_audio_evidence(
                contact.telegram_id,
                audio_bytes,
                filename,
                caption,
            )
            await run_in_threadpool(self._log_notification_audit, user_id, "AUDIO_EVIDENCE", res)
            return res

        if not top_3:
            logger.warning(f"Không có người liên hệ nào để gửi audio evidence cho user {user_id}")
            return []

        results = await asyncio.gather(*[_send_audio(c) for c in top_3])
        logger.info(f"Đã gửi audio evidence tới {len(top_3)} người liên hệ ưu tiên cho user {user_id}")
        return list(results)
