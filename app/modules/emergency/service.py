"""
=============================================================================
FILE: app/modules/emergency/service.py
MODULE: Emergency - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối toàn bộ phản ứng khẩn cấp (Emergency Orchestration Core):
      + Cơ chế Idempotent: Nếu đã có phiên ACTIVE thì không tạo phiên trùng lặp, chỉ cập nhật vị trí mới.
      + Kích hoạt phiên khẩn cấp (Manual SOS, nút nguồn vật lý, AI nhận diện tiếng thét, Safety Check).
      + Pipeline 5 bước: Lưu session -> Ghi mốc tọa độ GPS -> Lấy danh bạ người thân -> Gửi cảnh báo Telegram -> Broadcast WebSocket.
      + Hủy báo động (Cancel) hoặc Giải quyết sự cố (Resolve) kèm thông báo an toàn All-Clear cho người thân.
    - Đảm bảo tuân thủ ADR-014 (SOS Workflow Convergence) và ADR-015, ADR-016, ADR-007.

CONNECTIONS / DEPENDENCIES:
    - app/modules/emergency/repository.py (EmergencyRepository)
    - app/modules/emergency/schemas.py (EmergencyTriggerRequest, EmergencySessionResponse, EmergencyCancelRequest, EmergencyResolveRequest)
    - app/modules/contacts/service.py (ContactService)
    - app/modules/notifications/service.py (NotificationService)
    - app/modules/notifications/schemas.py (SosAlertPayload, AllClearPayload)
    - app/modules/location/service.py (LocationService)
    - app/modules/location/schemas.py (LocationCheckpointCreateRequest)
    - app/modules/users/repository.py (UserRepository)
    - app/realtime/manager.py (ws_manager)
    - app/core/exceptions.py (EntityNotFoundException, UnauthorizedException)

INPUT / OUTPUT:
    - Input: user_id, EmergencyTriggerRequest, EmergencyCancelRequest, EmergencyResolveRequest.
    - Output: EmergencySessionResponse, Optional[EmergencySessionResponse], List[EmergencySessionResponse].
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
import uuid

from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundException, UnauthorizedException
from app.core.logging import logger
from app.core.security import PinHasher
from app.modules.contacts.service import ContactService
from app.modules.emergency.repository import EmergencyRepository
from app.modules.emergency.schemas import (
    EmergencyCancelRequest,
    EmergencyResolveRequest,
    EmergencySessionResponse,
    EmergencyTriggerRequest,
)
from app.modules.location.schemas import LocationCheckpointCreateRequest
from app.modules.location.service import LocationService
from app.modules.notifications.schemas import AllClearPayload, DuressAlertPayload, SosAlertPayload
from app.modules.notifications.service import NotificationService
from app.modules.users.medical_repository import MedicalProfileRepository
from app.modules.users.repository import UserRepository
from app.realtime.manager import ws_manager
from app.shared.enums.emergency import EmergencySeverity, EmergencyStatus, EmergencyTriggerType
from app.shared.enums.user import MedicalPrivacyLevel
from app.shared.schemas.location import GeoPointSchema


class EmergencyService:
    """Service trái tim điều phối phản ứng khẩn cấp (Emergency Orchestrator)."""

    def __init__(
        self,
        repository: Optional[EmergencyRepository] = None,
        contact_service: Optional[ContactService] = None,
        notification_service: Optional[NotificationService] = None,
        location_service: Optional[LocationService] = None,
        user_repo: Optional[UserRepository] = None,
        medical_repo: Optional[MedicalProfileRepository] = None,
    ) -> None:
        self.repository = repository or EmergencyRepository()
        self.contact_service = contact_service or ContactService()
        self.notification_service = notification_service or NotificationService()
        self.location_service = location_service or LocationService()
        self.user_repo = user_repo or UserRepository()
        self.medical_repo = medical_repo or MedicalProfileRepository()

    def _to_response(self, raw: dict) -> EmergencySessionResponse:
        """Chuyển đổi dữ liệu thô sang DTO chuẩn."""
        init_loc = None
        if raw.get("initial_location"):
            init_loc = GeoPointSchema(**raw["initial_location"])

        latest_loc = None
        if raw.get("latest_location"):
            latest_loc = GeoPointSchema(**raw["latest_location"])

        maps_url = latest_loc.to_google_maps_url() if latest_loc else (init_loc.to_google_maps_url() if init_loc else None)

        return EmergencySessionResponse(
            session_id=raw["session_id"],
            user_id=raw["user_id"],
            status=EmergencyStatus(raw.get("status", EmergencyStatus.CREATED.value)),
            trigger_type=EmergencyTriggerType(raw.get("trigger_type", EmergencyTriggerType.MANUAL_SOS.value)),
            severity=EmergencySeverity(raw.get("severity", EmergencySeverity.CRITICAL.value)),
            event_details=raw.get("event_details"),
            initial_location=init_loc,
            latest_location=latest_loc,
            maps_url=maps_url,
            battery_level=raw.get("battery_level"),
            notes=raw.get("notes"),
            recording_id=raw.get("recording_id"),
            storage_key=raw.get("storage_key"),
            cancelled_reason=raw.get("cancelled_reason"),
            cancelled_via=raw.get("cancelled_via"),
            resolved_note=raw.get("resolved_note"),
            activated_at=raw.get("activated_at"),
            resolved_at=raw.get("resolved_at"),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    async def trigger_sos(
        self, user_id: str, request: EmergencyTriggerRequest
    ) -> EmergencySessionResponse:
        """
        Kích hoạt tình huống khẩn cấp (SOS Workflow Orchestration).
        Bảo đảm tính Idempotent: Nếu đã có phiên ACTIVE, trả về phiên hiện tại và cập nhật vị trí mới.
        """
        now = datetime.now(timezone.utc)

        # 1. Kiểm tra tính Idempotent
        existing_session = self.repository.get_active_session_by_user(user_id)
        if existing_session:
            logger.info(f"Người dùng '{user_id}' đã có phiên SOS đang ACTIVE ({existing_session['session_id']}), áp dụng Idempotency.")
            # Cập nhật vị trí mới nhất nếu có
            if request.latitude is not None and request.longitude is not None:
                new_loc = GeoPointSchema(
                    latitude=request.latitude,
                    longitude=request.longitude,
                    accuracy_meters=request.accuracy_meters,
                )
                self.repository.update(existing_session["session_id"], {"latest_location": new_loc.model_dump()})
                await self.location_service.record_checkpoint(
                    user_id=user_id,
                    request=LocationCheckpointCreateRequest(
                        latitude=request.latitude,
                        longitude=request.longitude,
                        accuracy_meters=request.accuracy_meters,
                        trigger_reason=request.trigger_type.value,
                        session_id=existing_session["session_id"],
                        address_text=request.notes,
                    ),
                )
                await ws_manager.broadcast_location(user_id, new_loc.model_dump())

            fresh = self.repository.get_by_id(existing_session["session_id"])
            return self._to_response(fresh or existing_session)

        # 2. Khởi tạo phiên khẩn cấp mới
        session_id = str(uuid.uuid4())
        geo_point = None
        if request.latitude is not None and request.longitude is not None:
            geo_point = GeoPointSchema(
                latitude=request.latitude,
                longitude=request.longitude,
                accuracy_meters=request.accuracy_meters,
            )

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "status": EmergencyStatus.ACTIVE.value,
            "trigger_type": request.trigger_type.value,
            "severity": request.severity.value,
            "event_details": request.event_details,
            "initial_location": geo_point.model_dump() if geo_point else None,
            "latest_location": geo_point.model_dump() if geo_point else None,
            "battery_level": request.battery_level,
            "notes": request.notes,
            "recording_id": request.recording_id,
            "activated_at": now,
        }
        saved_session = self.repository.create(session_id, session_data)
        if saved_session['session_id'] != session_id:
            return self._to_response(saved_session)

        # 3. Pipeline Bước 2: Ghi nhận mốc tọa độ vị trí (Location Checkpoint)
        if geo_point:
            try:
                await self.location_service.record_checkpoint(
                    user_id=user_id,
                    request=LocationCheckpointCreateRequest(
                        latitude=request.latitude,
                        longitude=request.longitude,
                        accuracy_meters=request.accuracy_meters,
                        trigger_reason=request.trigger_type.value,
                        session_id=session_id,
                        address_text=request.notes,
                    ),
                )
            except Exception as e:
                logger.warning(f"Lỗi khi lưu checkpoint lúc kích hoạt SOS: {str(e)}")

        # 4. Pipeline Bước 3 & 4: Lấy danh bạ và Gửi cảnh báo người thân qua Telegram
        try:
            contacts = await self.contact_service.list_contacts(user_id)
            user_doc = self.user_repo.get_by_id(user_id) or {}
            user_name = user_doc.get("name") or user_doc.get("display_name") or "Người dùng Guardian AI"
            user_phone = user_doc.get("phone")
            device_info = user_doc.get("device_info") or {}
            device_name = device_info.get("device_name")

            # Trích xuất thông tin y tế sơ cứu tuân thủ Medical Privacy (ADR-017)
            med_data = self.medical_repo.get_by_uid(user_id) or {}
            privacy_level = med_data.get("privacy_level", MedicalPrivacyLevel.EMERGENCY_SHARABLE.value)

            blood_type = None
            allergies = []
            medications = []
            chronic_conditions = []
            medical_notes = None
            medical_profile_url = None

            if privacy_level != MedicalPrivacyLevel.PRIVATE.value:
                blood_type = med_data.get("blood_type") or user_doc.get("blood_type")
                if blood_type == "UNKNOWN":
                    blood_type = None

                raw_allergies = med_data.get("allergies") or user_doc.get("allergies")
                if isinstance(raw_allergies, list):
                    allergies = [str(a).strip() for a in raw_allergies if a and str(a).strip() != "Không có"]
                elif isinstance(raw_allergies, str) and raw_allergies.strip() and raw_allergies.strip() != "Không có":
                    allergies = [a.strip() for a in raw_allergies.split(",") if a.strip()]

                raw_meds = med_data.get("medications") or user_doc.get("medications")
                if isinstance(raw_meds, list):
                    medications = [str(m).strip() for m in raw_meds if m and str(m).strip() != "Không có"]
                elif isinstance(raw_meds, str) and raw_meds.strip() and raw_meds.strip() != "Không có":
                    medications = [m.strip() for m in raw_meds.split(",") if m.strip()]

                raw_conditions = med_data.get("chronic_conditions") or user_doc.get("chronic_conditions")
                if isinstance(raw_conditions, list):
                    chronic_conditions = [str(c).strip() for c in raw_conditions if c and str(c).strip() != "Không có"]
                elif isinstance(raw_conditions, str) and raw_conditions.strip() and raw_conditions.strip() != "Không có":
                    chronic_conditions = [c.strip() for c in raw_conditions.split(",") if c.strip()]

                medical_notes = med_data.get("medical_notes") or user_doc.get("medical_notes")
                if medical_notes == "Không có":
                    medical_notes = None

                settings = get_settings()
                backend_url = getattr(settings, "BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
                medical_profile_url = f"{backend_url}/api/v1/users/{user_id}/public-emergency"

            sos_payload = SosAlertPayload(
                user_name=user_name,
                user_phone=user_phone,
                trigger_type=request.trigger_type.value,
                event_type=request.event_details or "Cảnh báo khẩn cấp",
                location=geo_point,
                device_name=device_name,
                battery_level=request.battery_level,
                notes=request.notes,
                blood_type=blood_type,
                allergies=allergies,
                medications=medications,
                chronic_conditions=chronic_conditions,
                medical_notes=medical_notes,
                medical_profile_url=medical_profile_url,
            )
            await self.notification_service.broadcast_sos(user_id, contacts, sos_payload)
        except Exception as e:
            logger.error(f"Lỗi khi gửi cảnh báo Telegram: {str(e)}")

        # 5. Pipeline Bước 5: Broadcast WebSocket thời gian thực
        try:
            await ws_manager.broadcast_emergency_state(
                user_id=user_id,
                state_payload={
                    "session_id": session_id,
                    "status": EmergencyStatus.ACTIVE.value,
                    "trigger_type": request.trigger_type.value,
                    "severity": request.severity.value,
                },
            )
            if geo_point:
                await ws_manager.broadcast_location(user_id, geo_point.model_dump())
        except Exception as e:
            logger.warning(f"Lỗi khi phát tán WebSocket: {str(e)}")

        return self._to_response(saved_session)

    async def cancel_emergency(
        self, user_id: str, request: EmergencyCancelRequest
    ) -> EmergencySessionResponse:
        """Hủy phiên khẩn cấp SAU KHI verify mã PIN thành công.

        Quy trình:
        1. Tìm phiên ACTIVE - nếu không có → 404.
        2. Verify PIN bằng bcrypt hash + fallback logic:
           - Safe PIN: verify với sos_pin_hash, hoặc fallback '1234' nếu chưa đổi.
           - Duress PIN: verify với duress_pin_hash, hoặc fallback '9999' nếu chưa đổi.
           - PIN sai → 401 Unauthorized.
        3. Nếu PIN đúng → cancel session + gửi notification phù hợp:
           - Safe PIN → All-Clear ("Đã an toàn").
           - Duress PIN → DURESS_COERCION ("BỊ ÉP BUỘC! CẦN ỨNG CỨU!").
        4. Broadcast WebSocket state change.

        Raises:
            EntityNotFoundException: Không có phiên ACTIVE.
            UnauthorizedException: PIN sai.
        """
        active_session = self.repository.get_active_session_by_user(user_id)
        if not active_session:
            raise EntityNotFoundException("Không tìm thấy phiên khẩn cấp đang kích hoạt để hủy.")

        # 1. Verify PIN bắt buộc
        user_doc = self.user_repo.get_by_id(user_id) or {}
        entered_pin = request.pin_code
        is_safe = PinHasher.verify_user_pin(entered_pin, user_doc)
        is_duress = not is_safe and PinHasher.verify_user_pin(entered_pin, user_doc, duress=True)

        if not is_safe and not is_duress:
            logger.warning(
                f"User {user_id} nhập sai PIN khi cố hủy SOS session {active_session.get('session_id')}"
            )
            raise UnauthorizedException("Mã PIN không chính xác")

        session_id = active_session["session_id"]
        now = datetime.now(timezone.utc)

        # 2. Phân biệt lý do cancel theo loại PIN
        if is_duress:
            final_reason = (
                "DURESS_COERCION: Nạn nhân bị ép buộc nhập mã PIN cưỡng bức! "
                "Cần ứng cứu khẩn cấp ngay lập tức!"
            )
            cancelled_via = "DURESS_PIN"
        else:
            final_reason = request.cancelled_reason or "Người dùng đã hủy báo động an toàn."
            cancelled_via = "SAFE_PIN"

        updated_session = self.repository.update(
            session_id,
            {
                "status": EmergencyStatus.CANCELLED.value,
                "cancelled_reason": final_reason,
                "cancelled_via": cancelled_via,
                "resolved_at": now,
            },
        )

        # 3. Gửi notification phù hợp
        try:
            contacts = await self.contact_service.list_contacts(user_id)
            user_name = user_doc.get("name") or "Người dùng"
            if is_duress:
                # Gửi cảnh báo DURESS_COERCION đặc biệt - PHÂN BIỆT với AllClear
                duress_payload = DuressAlertPayload(
                    user_name=user_name,
                    note=(
                        "🚨 KHẨN CẤP - DURESS_COERCION: Người dùng vừa nhập mã PIN cưỡng bức! "
                        "Có thể đang bị kẻ xấu ép buộc. CẦN ỨNG CỨU NGAY!"
                    ),
                )
                await self.notification_service.broadcast_duress_alert(
                    user_id, contacts, duress_payload
                )
            else:
                # Gửi All-Clear an toàn
                all_clear_payload = AllClearPayload(
                    user_name=user_name,
                    reason=final_reason,
                )
                await self.notification_service.broadcast_all_clear(
                    user_id, contacts, all_clear_payload
                )
        except Exception as e:
            logger.warning(f"Lỗi gửi notification khi hủy phiên: {str(e)}")

        # 4. Phát tán sự kiện WebSocket
        await ws_manager.broadcast_emergency_state(
            user_id,
            {"session_id": session_id, "status": EmergencyStatus.CANCELLED.value},
        )

        logger.info(
            f"User {user_id} cancelled SOS session {session_id} via {cancelled_via}"
        )
        return self._to_response(updated_session or active_session)

    async def resolve_emergency(
        self, user_id: str, request: EmergencyResolveRequest
    ) -> EmergencySessionResponse:
        """Đánh dấu sự cố đã được giải quyết an toàn."""
        active_session = self.repository.get_active_session_by_user(user_id)
        if not active_session:
            raise EntityNotFoundException("Không tìm thấy phiên khẩn cấp đang kích hoạt để giải quyết.")

        session_id = active_session["session_id"]
        now = datetime.now(timezone.utc)

        updated_session = self.repository.update(
            session_id,
            {
                "status": EmergencyStatus.RESOLVED.value,
                "resolved_note": request.resolved_note,
                "resolved_at": now,
            },
        )

        # Gửi thông báo All-Clear tới người thân
        try:
            contacts = await self.contact_service.list_contacts(user_id)
            user_doc = self.user_repo.get_by_id(user_id) or {}
            user_name = user_doc.get("name") or "Người dùng"
            all_clear_payload = AllClearPayload(
                user_name=user_name,
                reason=request.resolved_note or "Sự cố đã được giải quyết an toàn.",
            )
            await self.notification_service.broadcast_all_clear(user_id, contacts, all_clear_payload)
        except Exception as e:
            logger.warning(f"Lỗi gửi All-Clear khi giải quyết phiên: {str(e)}")

        # Phát tán sự kiện WebSocket
        await ws_manager.broadcast_emergency_state(
            user_id,
            {"session_id": session_id, "status": EmergencyStatus.RESOLVED.value},
        )

        return self._to_response(updated_session or active_session)

    async def get_active_session(self, user_id: str) -> Optional[EmergencySessionResponse]:
        """Lấy phiên khẩn cấp đang ACTIVE của người dùng nếu có."""
        active = self.repository.get_active_session_by_user(user_id)
        return self._to_response(active) if active else None

    async def get_session_by_id(self, user_id: str, session_id: str) -> EmergencySessionResponse:
        """Lấy chi tiết một phiên khẩn cấp theo ID (kiểm tra quyền sở hữu)."""
        session = self.repository.get_by_id(session_id)
        if not session:
            raise EntityNotFoundException(f"Không tìm thấy phiên khẩn cấp với ID: {session_id}")

        if session.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền xem phiên khẩn cấp này.")

        return self._to_response(session)

    async def list_user_sessions(self, user_id: str, limit: int = 50) -> List[EmergencySessionResponse]:
        """Lấy danh sách các phiên khẩn cấp lịch sử của người dùng."""
        raw_list = self.repository.list_by_user(user_id, limit=limit)
        return [self._to_response(item) for item in raw_list]
