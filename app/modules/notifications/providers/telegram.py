"""
=============================================================================
FILE: app/modules/notifications/providers/telegram.py
MODULE: Notifications - Telegram Bot Provider
ROLE / RESPONSIBILITY:
    - Triển khai `BaseNotificationProvider` sử dụng Telegram Bot API (ADR-016).
    - Soạn thảo và gửi tin nhắn cảnh báo khẩn cấp bằng định dạng HTML an toàn, trực quan:
      + SOS Alert kèm đường link ghim vị trí Google Maps, mức pin, phân loại sự kiện âm thanh.
      + Safety Check Timeout Alert khi người dùng quá hạn kiểm tra an toàn.
      + All-Clear thông báo an toàn khi người dùng giải tỏa báo động.
      + Gửi file ghi âm bằng chứng khẩn cấp (`sendVoice` / `sendAudio`).
    - Cơ chế chịu lỗi (Fault-Tolerant): Bắt toàn bộ lỗi mạng / 400 Bad Request, ghi log, không làm sập luồng khẩn cấp chính.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/core/logging.py (logger)
    - app/modules/notifications/providers/base.py (BaseNotificationProvider)
    - app/modules/notifications/schemas.py (SosAlertPayload, SafetyCheckAlertPayload, AllClearPayload, NotificationResult)
    - app/shared/enums/contact.py (NotificationChannel)
    - httpx (AsyncClient)

INPUT / OUTPUT:
    - Input: recipient (chat_id), alert payload, audio bytes.
    - Output: NotificationResult(success, channel, recipient, message_id, error_message).
=============================================================================
"""

import html
from typing import Optional
from datetime import datetime, timezone, timedelta
import httpx

from app.core.config import get_settings
from app.core.logging import logger
from app.modules.notifications.providers.base import BaseNotificationProvider
from app.modules.notifications.schemas import (
    AllClearPayload,
    DuressAlertPayload,
    NotificationResult,
    SafetyCheckAlertPayload,
    SosAlertPayload,
)
from app.shared.enums.contact import NotificationChannel

VN_TZ = timezone(timedelta(hours=7))


def format_vietnam_time(timestamp_raw: Optional[str] = None) -> str:
    """Chuẩn hóa thời gian sang định dạng thân thiện người dùng: HH:MM:SS, ngày DD/MM/YYYY (GMT+7)."""
    try:
        if timestamp_raw:
            # Hỗ trợ parse ISO 8601 string
            clean_ts = timestamp_raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
            dt_vn = dt.astimezone(VN_TZ)
        else:
            dt_vn = datetime.now(VN_TZ)
        return dt_vn.strftime("%H:%M:%S, ngày %d/%m/%Y")
    except Exception:
        # Fallback an toàn nếu chuỗi thời gian đặc biệt
        now_vn = datetime.now(VN_TZ)
        return now_vn.strftime("%H:%M:%S, ngày %d/%m/%Y")


class TelegramBotProvider(BaseNotificationProvider):
    """Provider gửi cảnh báo người thân qua Telegram Bot API."""

    def __init__(self, bot_token: Optional[str] = None, base_url: Optional[str] = None, transport=None) -> None:
        settings = get_settings()
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.base_url = (base_url or settings.TELEGRAM_API_BASE_URL).rstrip("/")
        self.channel = NotificationChannel.TELEGRAM
        self.transport = transport

    def _api_url(self, method: str) -> str:
        """Sinh URL gọi Telegram Bot API."""
        return f"{self.base_url}/bot{self.bot_token}/{method}"

    async def send_text(self, recipient: str, text: str) -> NotificationResult:
        """Gửi tin nhắn văn bản tùy chỉnh qua Telegram Bot."""
        if not self.bot_token:
            logger.warning("Telegram Bot Token chưa được cấu hình, bỏ qua gửi tin nhắn.")
            return NotificationResult(
                success=False,
                channel=self.channel,
                recipient=recipient,
                error_message="Telegram Bot Token chưa được thiết lập trong .env",
            )

        payload = {
            "chat_id": recipient,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.transport) as client:
                res = await client.post(self._api_url("sendMessage"), json=payload)
                try:
                    body = res.json()
                except ValueError:
                    body = {}
                body = body if isinstance(body, dict) else {}
                message_id = (body.get('result') or {}).get('message_id') if isinstance(body.get('result'), dict) else None
                if res.status_code == 200 and body.get('ok') is True and message_id is not None:
                    return NotificationResult(success=True, channel=self.channel,
                        recipient=recipient, message_id=str(message_id))
                code = body.get('error_code') or res.status_code
                retry_after = (body.get('parameters') or {}).get('retry_after') if isinstance(body.get('parameters'), dict) else None
                retry_after = retry_after if isinstance(retry_after, int) and retry_after >= 0 else None
                return NotificationResult(success=False, channel=self.channel, recipient=recipient,
                    error_message='Telegram chưa chấp nhận thông báo', error_code=f'TELEGRAM_{code}',
                    retryable=code == 429 or res.status_code >= 500,
                    retry_after_seconds=retry_after, delivery_uncertain=res.status_code >= 500)
        except Exception:
            # Never include the request URL in logs: it contains the bot token.
            return NotificationResult(success=False, channel=self.channel, recipient=recipient,
                error_message='Kết nối Telegram bị gián đoạn', error_code='TRANSPORT_ERROR',
                retryable=True, delivery_uncertain=True)

    async def send_sos_alert(self, recipient: str, payload: SosAlertPayload) -> NotificationResult:
        """Định dạng và gửi cảnh báo SOS khẩn cấp tới người thân qua Telegram."""
        user_name_esc = html.escape(payload.user_name)
        phone_esc = html.escape(payload.user_phone) if payload.user_phone else "Chưa cập nhật"
        trigger_esc = html.escape(payload.trigger_type)
        event_esc = html.escape(payload.event_type) if payload.event_type else "Cảnh báo khẩn"
        notes_esc = html.escape(payload.notes) if payload.notes else None

        maps_link = payload.maps_url
        if not maps_link and payload.location:
            maps_link = payload.location.to_google_maps_url()

        nav_link = payload.navigation_url
        if not nav_link and payload.location:
            nav_link = f"https://www.google.com/maps/dir/?api=1&destination={payload.location.latitude},{payload.location.longitude}"

        maps_html = f'<a href="{maps_link}">📍 Xem vị trí trên Google Maps</a>' if maps_link else "<i>(Không có tọa độ GPS)</i>"
        nav_html = f'\n🚗 <a href="{nav_link}">Dẫn đường khẩn cấp tới vị trí</a>' if nav_link else ""
        device_html = f"\n📱 <b>Thiết bị phát tín hiệu:</b> <code>{html.escape(payload.device_name)}</code>" if payload.device_name else ""
        audio_html = f'<br/>🎙️ <b>Ghi âm bằng chứng:</b> <a href="{payload.audio_url}">Nghe trực tiếp</a>' if payload.audio_url else ""
        battery_html = f"\n🔋 <b>Mức pin máy:</b> {payload.battery_level}%" if payload.battery_level is not None else ""
        notes_html = f"\n📝 <b>Ghi chú:</b> {notes_esc}" if notes_esc else ""
        time_display = format_vietnam_time(payload.timestamp)

        # Định dạng thông tin y tế sơ cứu nếu có
        medical_lines = []
        if payload.blood_type and payload.blood_type != "UNKNOWN":
            medical_lines.append(f"• 🩸 <b>Nhóm máu:</b> <code>{html.escape(payload.blood_type)}</code>")
        if payload.allergies:
            allergies_str = html.escape(", ".join(payload.allergies))
            medical_lines.append(f"• ⚠️ <b>Dị ứng:</b> <code>{allergies_str}</code>")
        if payload.chronic_conditions:
            conditions_str = html.escape(", ".join(payload.chronic_conditions))
            medical_lines.append(f"• 🫀 <b>Bệnh nền:</b> <code>{conditions_str}</code>")
        if payload.medications:
            meds_str = html.escape(", ".join(payload.medications))
            medical_lines.append(f"• 💊 <b>Thuốc đang dùng:</b> <code>{meds_str}</code>")
        if payload.medical_notes:
            medical_lines.append(f"• 📝 <b>Ghi chú sơ cứu:</b> <i>{html.escape(payload.medical_notes)}</i>")
        if payload.medical_profile_url:
            medical_lines.append(f'• 🏥 <a href="{payload.medical_profile_url}">Xem hồ sơ y tế khẩn cấp chi tiết</a>')

        medical_html = ""
        if medical_lines:
            medical_html = f"\n\n🩺 <b>THÔNG TIN Y TẾ SƠ CỨU:</b>\n" + "\n".join(medical_lines)

        message = (
            f"🚨 <b>CẢNH BÁO NGUY HIỂM KHẨN CẤP (SOS)</b> 🚨\n\n"
            f"👤 <b>Người gặp nạn:</b> <b>{user_name_esc}</b>\n"
            f"📞 <b>Số điện thoại:</b> {phone_esc}\n"
            f"⚠️ <b>Hình thức kích hoạt:</b> <code>{trigger_esc}</code>\n"
            f"🔊 <b>Sự kiện âm thanh:</b> <code>{event_esc}</code>"
            f"{device_html}\n"
            f"🗺️ <b>Vị trí hiện tại:</b> {maps_html}"
            f"{nav_html}"
            f"{battery_html}"
            f"{notes_html}"
            f"{medical_html}"
            f"{audio_html}\n\n"
            f"🕒 <i>Thời điểm: {time_display}</i>\n"
            f"⚡ <i>Vui lòng liên hệ người thân ngay lập tức hoặc gọi cứu hộ khẩn cấp!</i>"
        )

        return await self.send_text(recipient, message)

    async def send_safety_check_alert(
        self, recipient: str, payload: SafetyCheckAlertPayload
    ) -> NotificationResult:
        """Định dạng và gửi thông báo quá hạn kiểm tra an toàn (Escalated Safety Check)."""
        user_name_esc = html.escape(payload.user_name)
        template_esc = html.escape(payload.template_name)

        maps_link = payload.maps_url
        if not maps_link and payload.location:
            maps_link = payload.location.to_google_maps_url()

        maps_html = f'<a href="{maps_link}">📍 Vị trí ghi nhận gần nhất</a>' if maps_link else "<i>(Không có tọa độ GPS)</i>"
        time_display = format_vietnam_time(payload.timestamp)

        medical_lines = []
        if payload.blood_type and payload.blood_type != "UNKNOWN":
            medical_lines.append(f"• 🩸 <b>Nhóm máu:</b> <code>{html.escape(payload.blood_type)}</code>")
        if payload.allergies:
            allergies_str = html.escape(", ".join(payload.allergies))
            medical_lines.append(f"• ⚠️ <b>Dị ứng:</b> <code>{allergies_str}</code>")
        if payload.chronic_conditions:
            conditions_str = html.escape(", ".join(payload.chronic_conditions))
            medical_lines.append(f"• 🫀 <b>Bệnh nền:</b> <code>{conditions_str}</code>")
        if payload.medical_notes:
            medical_lines.append(f"• 📝 <b>Ghi chú sơ cứu:</b> <i>{html.escape(payload.medical_notes)}</i>")
        if payload.medical_profile_url:
            medical_lines.append(f'• 🏥 <a href="{payload.medical_profile_url}">Xem hồ sơ y tế khẩn cấp chi tiết</a>')

        medical_html = ""
        if medical_lines:
            medical_html = f"\n\n🩺 <b>THÔNG TIN Y TẾ SƠ CỨU:</b>\n" + "\n".join(medical_lines)

        message = (
            f"⚠️ <b>CẢNH BÁO QUÁ HẠN KIỂM TRA AN TOÀN</b> ⚠️\n\n"
            f"👤 <b>Người dùng:</b> <b>{user_name_esc}</b>\n"
            f"🛡️ <b>Mục tiêu an toàn:</b> {template_esc} (Hẹn giờ: {payload.duration_minutes} phút)\n"
            f"⏱️ <b>Trạng thái:</b> Đã hết hạn hẹn giờ và người dùng không xác nhận an toàn.\n"
            f"🗺️ <b>Vị trí gần nhất:</b> {maps_html}"
            f"{medical_html}\n\n"
            f"🕒 <i>Thời điểm: {time_display}</i>\n"
            f"📞 <i>Vui lòng gọi điện kiểm tra tình hình của người dùng.</i>"
        )

        return await self.send_text(recipient, message)

    async def send_all_clear(self, recipient: str, payload: AllClearPayload) -> NotificationResult:
        """Định dạng và gửi thông báo đã an toàn / hủy báo động (All-Clear hoặc Duress Alert)."""
        user_name_esc = html.escape(payload.user_name)
        reason_esc = html.escape(payload.reason) if payload.reason else "Đã xác nhận an toàn."

        is_duress = (
            "DURESS" in (payload.reason or "").upper()
            or "CƯỠNG BỨC" in (payload.reason or "").upper()
            or "ÉP BUỘC" in (payload.reason or "").upper()
        )

        time_display = format_vietnam_time(payload.timestamp)

        if is_duress:
            message = (
                f"🚨🚨 <b>BÁO ĐỘNG TỐI KHẨN: NẠN NHÂN BỊ ÉP BUỘC (DURESS ALERT)!</b> 🚨🚨\n\n"
                f"👤 <b>Người gặp nạn:</b> <b>{user_name_esc}</b>\n"
                f"⚠️ <b>Tình trạng:</b> Nạn nhân vừa nhập <b>MÃ PIN CƯỠNG BỨC</b> để tắt còi báo động!\n"
                f"‼️ <b>CẢNH BÁO NGUY HIỂM:</b> Nạn nhân đang bị khống chế/đe dọa và <b>KHÔNG HỀ AN TOÀN</b>!\n"
                f"📝 <b>Ghi chú hệ thống:</b> {reason_esc}\n\n"
                f"🕒 <i>Thời điểm: {time_display}</i>\n"
                f"🆘 <b>HÀNH ĐỘNG KHẨN CẤP:</b> Hãy liên hệ cơ quan công an (113) và triển khai giải cứu nạn nhân ngay lập tức!"
            )
        else:
            message = (
                f"✅ <b>THÔNG BÁO ĐÃ AN TOÀN (ALL CLEAR)</b> ✅\n\n"
                f"👤 <b>Người dùng:</b> <b>{user_name_esc}</b>\n"
                f"🛡️ <b>Tình trạng:</b> Đã giải tỏa trạng thái khẩn cấp.\n"
                f"📝 <b>Lý do:</b> {reason_esc}\n\n"
                f"🕒 <i>Thời điểm: {time_display}</i>\n"
                f"💚 <i>Người thân có thể an tâm!</i>"
            )

        return await self.send_text(recipient, message)

    async def send_duress_alert(
        self, recipient: str, payload: DuressAlertPayload
    ) -> NotificationResult:
        """Định dạng và gửi cảnh báo DURESS_COERCION tới người thân.

        Phân biệt rõ ràng với All-Clear:
        - All-Clear: ✅ "Đã an toàn, yên tâm"
        - DURESS: 🚨 "BỊ ÉP BUỘC! CẦN ỨNG CỨU KHẨN CẤP!"

        Ngữ cảnh: User vừa nhập mã PIN cưỡng bức để tắt còi báo động,
        có thể đang bị kẻ xấu ép buộc. Cảnh báo này gửi NGAY LẬP TỨC tới
        người thân + khuyến nghị gọi công an (113).
        """
        user_name_esc = html.escape(payload.user_name)
        note_esc = html.escape(payload.note) if payload.note else (
            "Người dùng vừa nhập mã PIN cưỡng bức - có thể bị ép buộc!"
        )

        time_display = format_vietnam_time(payload.timestamp)

        message = (
            f"🚨🚨🚨 <b>BÁO ĐỘNG TỐI KHẨN: NẠN NHÂN BỊ ÉP BUỘC (DURESS)!</b> 🚨🚨🚨\n\n"
            f"👤 <b>Người gặp nạn:</b> <b>{user_name_esc}</b>\n"
            f"⚠️ <b>Tình trạng:</b> Nạn nhân vừa nhập <b>MÃ PIN CƯỠNG BỨC</b> để tắt còi báo động!\n"
            f"‼️ <b>CẢNH BÁO NGUY HIỂM:</b> Nạn nhân đang bị khống chế/đe dọa và <b>KHÔNG HỀ AN TOÀN</b>!\n"
            f"📝 <b>Ghi chú hệ thống:</b> {note_esc}\n\n"
            f"🕒 <i>Thời điểm: {time_display}</i>\n"
            f"🆘 <b>HÀNH ĐỘNG KHẨN CẤP:</b> Hãy liên hệ cơ quan công an (113) và triển khai giải cứu nạn nhân ngay lập tức!"
        )

        return await self.send_text(recipient, message)

    async def send_audio_evidence(
        self, recipient: str, audio_bytes: bytes, filename: str = "evidence.ogg", caption: str = "Bằng chứng âm thanh khẩn cấp"
    ) -> NotificationResult:
        """Gửi trực tiếp đoạn ghi âm bằng chứng vào khung chat Telegram."""
        if not self.bot_token:
            return NotificationResult(
                success=False,
                channel=self.channel,
                recipient=recipient,
                error_message="Telegram Bot Token chưa được cấu hình",
            )

        try:
            # Ưu tiên gửi dạng sendVoice nếu là ogg, hoặc sendAudio
            method = "sendVoice" if filename.endswith((".ogg", ".oga", ".opus")) else "sendAudio"
            files = {"voice" if method == "sendVoice" else "audio": (filename, audio_bytes)}
            data = {"chat_id": recipient, "caption": caption}

            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(self._api_url(method), data=data, files=files)
                if res.status_code == 200:
                    msg_id = str(res.json().get("result", {}).get("message_id", ""))
                    logger.info(f"Đã gửi file ghi âm bằng chứng tới Telegram: {recipient}")
                    return NotificationResult(
                        success=True,
                        channel=self.channel,
                        recipient=recipient,
                        message_id=msg_id,
                    )
                else:
                    return NotificationResult(
                        success=False,
                        channel=self.channel,
                        recipient=recipient,
                        error_message=f"Lỗi gửi audio {res.status_code}: {res.text}",
                    )
        except Exception as e:
            logger.error(f"Lỗi gửi audio tới Telegram: {str(e)}")
            return NotificationResult(
                success=False,
                channel=self.channel,
                recipient=recipient,
                error_message=str(e),
            )
