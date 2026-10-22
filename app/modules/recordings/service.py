"""
=============================================================================
FILE: app/modules/recordings/service.py
MODULE: Recordings - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối việc lưu trữ và trích xuất bằng chứng ghi âm khẩn cấp:
      + Nhận stream audio bytes từ client (Flutter app).
      + Chuẩn hóa tên file, cấu trúc storage key phân tầng theo người dùng và sự kiện.
      + Đẩy binary audio lên Cloudflare R2 (ADR-006).
      + Lưu trữ metadata vào Firestore `recordings`.
      + Sinh đường dẫn presigned URL có chữ ký bảo mật cho phép nghe lại có kiểm soát.
      + Kiểm tra quyền sở hữu (Ownership check) đảm bảo tính riêng tư dữ liệu.
      + Xóa đồng bộ cả trên Cloudflare R2 lẫn Firestore.
      + Hỗ trợ clip upload với idempotency, retry và validation.
      + Tự động gửi audio evidence tới 3 người ưu tiên cao nhất qua Telegram sau khi upload thành công.
      + Tuân thủ Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân nhạy cảm.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/storage/r2/client.py (R2StorageClient, get_r2_client)
    - app/modules/recordings/repository.py (RecordingRepository)
    - app/modules/recordings/schemas.py (RecordingMetadataResponse, PresignedAudioUrlResponse)
    - app/modules/notifications/service.py (NotificationService) - for audio evidence dispatch
    - app/modules/contacts/service.py (ContactService) - for getting priority contacts
    - app/core/exceptions.py (EntityNotFoundException, UnauthorizedException, ValidationException)
    - app/core/config.py (get_settings)

INPUT / OUTPUT:
    - Input: user_id, audio bytes, filenames, recording_id, clip metadata.
    - Output: RecordingMetadataResponse, PresignedAudioUrlResponse, List[RecordingMetadataResponse].
=============================================================================
"""

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.core.config import get_settings
from app.core.logging import logger
from app.core.exceptions import ConflictException, EntityNotFoundException, UnauthorizedException, ValidationException
from app.infrastructure.storage.r2.client import R2StorageClient, get_r2_client
from app.modules.notifications.service import NotificationService
from app.modules.recordings.repository import RecordingRepository
from app.modules.recordings.schemas import PresignedAudioUrlResponse, RecordingMetadataResponse


class RecordingService:
    """Service điều phối nghiệp vụ lưu trữ và nghe lại file ghi âm bằng chứng."""

    # Recording upload status for tracking
    STATUS_PENDING = "pending"
    STATUS_UPLOADING = "uploading"
    STATUS_UPLOADED = "uploaded"
    STATUS_FAILED = "failed"
    _last_evidence_broadcast_by_user: Dict[str, float] = {}

    def __init__(
        self,
        repository: Optional[RecordingRepository] = None,
        r2_client: Optional[R2StorageClient] = None,
        notification_service: Optional[NotificationService] = None,
    ) -> None:
        self.repository = repository or RecordingRepository()
        self.r2_client = r2_client or get_r2_client()
        self.notification_service = notification_service or NotificationService()
        self.settings = get_settings()

    def _sanitize_filename(self, filename: str) -> str:
        """Làm sạch tên file, chỉ giữ lại ký tự an toàn và phần mở rộng."""
        base_name, ext = os.path.splitext(filename)
        clean_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_name)[:50]
        clean_ext = ext.lower() if ext.lower() in [".webm", ".mp4", ".m4a", ".wav", ".ogg", ".aac", ".opus"] else ".webm"
        return f"{clean_base}{clean_ext}"

    def _to_response(self, raw: dict) -> RecordingMetadataResponse:
        """Chuyển đổi dữ liệu sang DTO chuẩn."""
        return RecordingMetadataResponse(
            recording_id=raw["recording_id"],
            user_id=raw["user_id"],
            event_id=raw.get("event_id"),
            session_id=raw.get("session_id"),
            file_name=raw.get("file_name", "audio.webm"),
            storage_key=raw.get("storage_key", ""),
            duration_seconds=raw.get("duration_seconds"),
            file_size_bytes=raw.get("file_size_bytes", 0),
            content_type=raw.get("content_type", "audio/webm"),
            created_at=raw.get("created_at"),
            # Clip-specific fields
            event_type=raw.get("event_type"),
            confidence=raw.get("confidence"),
            pre_event_seconds=raw.get("pre_event_seconds"),
            post_event_seconds=raw.get("post_event_seconds"),
            upload_status=raw.get("upload_status"),
        )

    def _validate_clip(
        self,
        audio_bytes: bytes,
        duration_seconds: Optional[float],
        pre_event_seconds: Optional[float],
        post_event_seconds: Optional[float],
    ) -> None:
        """Validate clip metadata against configured limits."""
        # Validate audio size
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValidationException("File ghi âm không có nội dung (0 bytes).")

        max_bytes = self.settings.CLIP_MAX_TOTAL_DURATION_SECONDS * 16 * 1024 * 2  # Rough estimate
        if len(audio_bytes) > max_bytes:
            raise ValidationException(
                f"File ghi âm vượt quá giới hạn ({self.settings.CLIP_MAX_TOTAL_DURATION_SECONDS}s tối đa)."
            )

        # Validate duration if provided
        if duration_seconds is not None:
            if duration_seconds > self.settings.CLIP_MAX_TOTAL_DURATION_SECONDS:
                raise ValidationException(
                    f"Thời lượng clip vượt quá giới hạn cho phép "
                    f"({self.settings.CLIP_MAX_TOTAL_DURATION_SECONDS}s)."
                )
            if duration_seconds <= 0:
                raise ValidationException("Thời lượng clip phải lớn hơn 0.")

        # Validate pre/post roll
        if pre_event_seconds is not None and pre_event_seconds > self.settings.CLIP_MAX_PRE_ROLL_SECONDS:
            raise ValidationException(
                f"Pre-roll vượt quá giới hạn ({self.settings.CLIP_MAX_PRE_ROLL_SECONDS}s)."
            )

        if post_event_seconds is not None and post_event_seconds > self.settings.CLIP_MAX_POST_ROLL_SECONDS:
            raise ValidationException(
                f"Post-roll vượt quá giới hạn ({self.settings.CLIP_MAX_POST_ROLL_SECONDS}s)."
            )

    def _check_idempotency(self, event_id: str, user_id: str) -> Optional[dict]:
        """
        Kiểm tra idempotency: nếu đã có recording với cùng event_id trong khoảng thời gian,
        trả về recording đó thay vì tạo mới.
        """
        # Get all recordings for this event
        all_recordings = self.repository.list_by_user(user_id, limit=100)
        for rec in all_recordings:
            if rec.get("event_id") == event_id and rec.get("upload_status") != self.STATUS_FAILED:
                # Check if within idempotency window
                created_at = rec.get("created_at")
                if created_at:
                    if isinstance(created_at, datetime):
                        age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
                    else:
                        age_seconds = 0

                    if age_seconds < self.settings.CLIP_IDEMPOTENCY_WINDOW_SECONDS:
                        return rec
        return None

    async def upload_audio_recording(
        self,
        user_id: str,
        audio_bytes: bytes,
        original_filename: str,
        content_type: str = "audio/webm",
        event_id: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        confidence: Optional[float] = None,
        pre_event_seconds: Optional[float] = None,
        post_event_seconds: Optional[float] = None,
    ) -> RecordingMetadataResponse:
        """
        Upload file ghi âm bằng chứng lên Cloudflare R2 và lưu metadata vào Firestore.

        Supports idempotency: if event_id is provided and a recording already exists
        for this event within the idempotency window, returns the existing recording.
        """
        # 1. Validate clip metadata
        self._validate_clip(audio_bytes, duration_seconds, pre_event_seconds, post_event_seconds)

        # 2. Check idempotency if event_id provided
        if event_id:
            existing = self._check_idempotency(event_id, user_id)
            if existing:
                return self._to_response(existing)

        recording_id = str(uuid.uuid4())
        sanitized_filename = self._sanitize_filename(original_filename)
        event_partition = event_id if event_id else (session_id if session_id else "adhoc")

        # Tự động bọc 44-byte RIFF header nếu client gửi raw PCM để bất kỳ trình phát nào cũng nghe được
        if (content_type == "audio/wav" or sanitized_filename.endswith(".wav")) and not audio_bytes.startswith(b"RIFF"):
            import struct
            sample_rate = 16000
            num_channels = 1
            pcm_len = len(audio_bytes)
            byte_rate = sample_rate * num_channels * 2
            block_align = num_channels * 2
            wav_header = struct.pack(
                "<4sI4s4sIHHIIHH4sI",
                b"RIFF",
                36 + pcm_len,
                b"WAVE",
                b"fmt ",
                16,
                1,  # PCM format
                num_channels,
                sample_rate,
                byte_rate,
                block_align,
                16,  # 16-bit
                b"data",
                pcm_len,
            )
            audio_bytes = wav_header + audio_bytes

        # Cấu trúc lưu trữ theo ADR-006: users/{user_id}/emergency/{event_id}/audio/{recording_id}_{filename}
        storage_key = f"users/{user_id}/emergency/{event_partition}/audio/{recording_id}_{sanitized_filename}"

        # 3. Prepare metadata with pending status
        metadata = {
            "recording_id": recording_id,
            "user_id": user_id,
            "event_id": event_id,
            "session_id": session_id,
            "file_name": sanitized_filename,
            "storage_key": storage_key,
            "duration_seconds": duration_seconds,
            "file_size_bytes": len(audio_bytes),
            "content_type": content_type,
            "upload_status": self.STATUS_PENDING,
            # Clip-specific fields
            "event_type": event_type,
            "confidence": confidence,
            "pre_event_seconds": pre_event_seconds,
            "post_event_seconds": post_event_seconds,
        }

        # 4. Save metadata to Firestore FIRST (with pending status)
        saved = self.repository.create(recording_id, metadata)

        # 5. Upload to R2 with idempotency check (using recording_id as idempotency key)
        try:
            self.repository.update(recording_id, {"upload_status": self.STATUS_UPLOADING})
            self.r2_client.upload_bytes(
                data=audio_bytes,
                key=storage_key,
                content_type=content_type,
                idempotency_key=recording_id,  # Use recording_id as idempotency key
            )
            # 6. Update status to uploaded
            self.repository.update(recording_id, {"upload_status": self.STATUS_UPLOADED})
            saved["upload_status"] = self.STATUS_UPLOADED

            # 6.1. Cập nhật liên kết tương đối vào Firestore emergency_sessions
            if session_id:
                try:
                    from app.infrastructure.firestore.client import get_firestore_client
                    db = get_firestore_client()
                    db.collection("emergency_sessions").document(session_id).set({
                        "recording_id": recording_id,
                        "storage_key": storage_key,
                    }, merge=True)
                    logger.info(f"Đã cập nhật link tương đối storage_key '{storage_key}' và recording_id vào emergency_sessions/{session_id}")
                except Exception as link_err:
                    logger.warning(f"Không thể cập nhật link vào emergency_session '{session_id}': {str(link_err)}")

            # 7. Gửi audio evidence cho 3 người ưu tiên cao nhất (chạy background)
            # ⚠️ TEST MODE: Tạm tắt gửi file âm thanh qua Telegram theo yêu cầu test riêng detection
            # critical_events = {'SCREAM', 'DISTRESS_CRY', 'GUNSHOT', 'VIOLENT_STRUGGLE', 'EXPLOSION', 'MANUAL_SOS'}
            # if event_type in critical_events:
            #     asyncio.create_task(self._send_audio_evidence_background(
            #         user_id=user_id,
            #         audio_bytes=audio_bytes,
            #         filename=sanitized_filename,
            #         session_id=session_id,
            #     ))
            logger.info(f"[TEST MODE] Bỏ qua gửi audio evidence qua Telegram cho recording '{recording_id}'.")

        except Exception as e:
            # If R2 upload fails, update status to failed
            self.repository.update(recording_id, {"upload_status": self.STATUS_FAILED})
            raise ValidationException(f"Upload thất bại: {str(e)}")

        return self._to_response(saved)

    async def get_recording(self, user_id: str, recording_id: str) -> RecordingMetadataResponse:
        """Lấy thông tin metadata của bản ghi âm (kiểm tra quyền sở hữu)."""
        rec = self.repository.get_by_id(recording_id)
        if not rec:
            raise EntityNotFoundException(f"Không tìm thấy bản ghi âm với ID: {recording_id}")

        if rec.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền truy cập bản ghi âm này.")

        return self._to_response(rec)

    async def get_playback_url(
        self, user_id: str, recording_id: str, expires_in: int = 3600
    ) -> PresignedAudioUrlResponse:
        """Sinh URL có chữ ký bảo mật để nghe lại bản ghi âm."""
        rec = await self.get_recording(user_id, recording_id)
        presigned_url = self.r2_client.generate_presigned_url(
            key=rec.storage_key,
            expires_in=expires_in,
        )

        return PresignedAudioUrlResponse(
            recording_id=recording_id,
            playback_url=presigned_url,
            expires_in_seconds=expires_in,
        )

    async def list_recordings(self, user_id: str, limit: int = 50) -> List[RecordingMetadataResponse]:
        """Lấy danh sách các bản ghi âm của người dùng."""
        raw_list = self.repository.list_by_user(user_id, limit=limit)
        return [self._to_response(item) for item in raw_list]

    async def delete_recording(self, user_id: str, recording_id: str) -> None:
        """Xóa bản ghi âm khỏi cả Cloudflare R2 và Firestore."""
        rec = self.repository.get_by_id(recording_id)
        if not rec:
            raise EntityNotFoundException(f"Không tìm thấy bản ghi âm với ID: {recording_id}")

        if rec.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền xóa bản ghi âm này.")

        # Xóa trên Cloudflare R2
        storage_key = rec.get("storage_key")
        if storage_key:
            self.r2_client.delete_object(storage_key)

        # Xóa trên Firestore
        self.repository.delete(recording_id)

    async def _send_audio_evidence_background(
        self,
        user_id: str,
        audio_bytes: bytes,
        filename: str,
        session_id: Optional[str],
    ) -> None:
        """
        Background task để gửi audio evidence tới 3 người ưu tiên cao nhất.
        Chạy async để không blocking upload response.
        Bảo đảm tính Idempotent và chống spam Telegram:
        - Chỉ gửi nếu phiên khẩn cấp đang ACTIVE hoặc CREATED (không gửi nếu CANCELLED / RESOLVED).
        - Mỗi session chỉ gửi bằng chứng âm thanh đúng 1 lần (audio_evidence_sent flag).
        - Rate limit người dùng tối thiểu 60s giữa các lần broadcast audio.
        """
        try:
            import time
            from app.modules.contacts.service import ContactService
            from app.modules.users.repository import UserRepository
            from app.infrastructure.firestore.client import get_firestore_client
            from datetime import datetime, timezone, timedelta

            # 1. Kiểm tra trạng thái phiên khẩn cấp nếu có session_id
            if session_id:
                try:
                    db = get_firestore_client()
                    session_ref = db.collection("emergency_sessions").document(session_id)
                    session_snap = session_ref.get()
                    if session_snap.exists:
                        session_data = session_snap.to_dict() or {}
                        status = session_data.get("status")
                        if status not in ("ACTIVE", "CREATED"):
                            logger.info(
                                f"Bỏ qua gửi audio evidence: Phiên {session_id} có trạng thái '{status}' (không còn ACTIVE)."
                            )
                            return
                        if session_data.get("audio_evidence_sent") is True:
                            logger.info(
                                f"Bỏ qua gửi audio evidence: Phiên {session_id} đã được gửi bằng chứng âm thanh trước đó."
                            )
                            return
                        # Đánh dấu đã gửi audio evidence cho session này
                        session_ref.set({"audio_evidence_sent": True}, merge=True)
                except Exception as check_err:
                    logger.warning(f"Lỗi kiểm tra trạng thái emergency session: {check_err}")

            # 2. Rate-limiting cấp User (Tối thiểu 60 giây giữa các lần gửi audio evidence)
            now_ts = time.time()
            last_ts = self._last_evidence_broadcast_by_user.get(user_id, 0.0)
            if now_ts - last_ts < 60.0:
                logger.info(
                    f"Bỏ qua gửi audio evidence cho user {user_id}: Vừa gửi cách đây {now_ts - last_ts:.1f}s (< 60s throttle)."
                )
                return
            self._last_evidence_broadcast_by_user[user_id] = now_ts

            contact_service = ContactService()
            user_repo = UserRepository()

            contacts = await contact_service.list_contacts(user_id)
            user_doc = user_repo.get_by_id(user_id) or {}
            user_name = user_doc.get("name", "Người dùng")

            # Định dạng thời gian Việt Nam
            vn_tz = timezone(timedelta(hours=7))
            timestamp = datetime.now(vn_tz).strftime("%H:%M:%S, ngày %d/%m/%Y")

            caption = (
                f"🚨 BẰNG CHỨNG ÂM THANH KHẨN CẤP\n"
                f"👤 Người gặp nạn: {user_name}\n"
                f"⏰ Thời điểm: {timestamp}"
            )

            await self.notification_service.broadcast_audio_evidence(
                user_id=user_id,
                contacts=contacts,
                audio_bytes=audio_bytes,
                filename=filename,
                caption=caption,
            )

            logger.info(
                f"Đã gửi audio evidence cho user {user_id}, session {session_id}"
            )

        except Exception as e:
            logger.error(f"Lỗi gửi audio evidence: {str(e)}")
