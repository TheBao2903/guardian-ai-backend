"""
=============================================================================
FILE: app/modules/emergency/safety_check/service.py
MODULE: Safety Check - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối toàn bộ nghiệp vụ Hẹn giờ kiểm tra an toàn (Safety Check Timer):
      + Quản lý các mẫu Template (5 mẫu hệ thống + mẫu người dùng tự tạo).
      + Bắt đầu phiên đếm ngược mới: tính toán `expires_at`, `grace_period_until`, ngăn chặn trùng lặp.
      + Bấm 'Tôi an toàn' (`confirm_safe`) chuyển sang `COMPLETED`.
      + Gia hạn thêm thời gian (`extend_timer` tối đa 3 lần).
      + Hủy phiên (`cancel_instance`).
      + Cập nhật vị trí GPS định kỳ trong quá trình đếm ngược.
      + Leo thang cảnh báo (`escalate_overdue_instance`): Khi quá hạn Grace Period,
        tự động gửi cảnh báo khẩn cấp tới Telegram người thân kèm vị trí gần nhất.
      + Xử lý trường hợp đặc biệt: Người dùng bấm an toàn sau khi đã bị Escalate
        -> tự động gửi thông báo đính chính All-Clear cho người thân an tâm.
    - Tuân thủ ADR-031 (Safety Check Timer & Escalation).

CONNECTIONS / DEPENDENCIES:
    - app/modules/emergency/safety_check/repository.py (SafetyCheckRepository)
    - app/modules/emergency/safety_check/schemas.py
    - app/modules/contacts/service.py (ContactService)
    - app/modules/notifications/service.py (NotificationService)
    - app/modules/location/service.py (LocationService)
    - app/modules/users/repository.py (UserRepository)
    - app/realtime/manager.py (ws_manager)
    - app/core/exceptions.py (EntityNotFoundException, UnauthorizedException, ValidationException)

INPUT / OUTPUT:
    - Input: user_id, DTO requests.
    - Output: SafetyCheckInstanceResponse, SafetyCheckTemplateResponse, lists.
=============================================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
import uuid

from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundException, UnauthorizedException, ValidationException
from app.core.logging import logger
from app.modules.contacts.service import ContactService
from app.modules.emergency.safety_check.repository import SafetyCheckRepository
from app.modules.emergency.safety_check.schemas import (
    CancelSafetyCheckRequest,
    ConfirmSafeRequest,
    CreateCustomTemplateRequest,
    ExtendSafetyCheckRequest,
    SafetyCheckInstanceResponse,
    SafetyCheckTemplateResponse,
    StartSafetyCheckRequest,
)
from app.modules.location.schemas import LocationCheckpointCreateRequest
from app.modules.location.service import LocationService
from app.modules.notifications.schemas import AllClearPayload, SafetyCheckAlertPayload
from app.modules.notifications.service import NotificationService
from app.modules.users.medical_repository import MedicalProfileRepository
from app.modules.users.repository import UserRepository
from app.realtime.manager import ws_manager
from app.shared.enums.safety_check import SafetyCheckStatus
from app.shared.enums.user import MedicalPrivacyLevel
from app.shared.schemas.location import GeoPointSchema


class SafetyCheckService:
    """Service điều phối nghiệp vụ hẹn giờ kiểm tra an toàn và leo thang cảnh báo."""

    def __init__(
        self,
        repository: Optional[SafetyCheckRepository] = None,
        contact_service: Optional[ContactService] = None,
        notification_service: Optional[NotificationService] = None,
        location_service: Optional[LocationService] = None,
        user_repo: Optional[UserRepository] = None,
        medical_repo: Optional[MedicalProfileRepository] = None,
    ) -> None:
        self.repository = repository or SafetyCheckRepository()
        self.contact_service = contact_service or ContactService()
        self.notification_service = notification_service or NotificationService()
        self.location_service = location_service or LocationService()
        self.user_repo = user_repo or UserRepository()
        self.medical_repo = medical_repo or MedicalProfileRepository()
        self.settings = get_settings()

    def _to_instance_response(self, raw: dict) -> SafetyCheckInstanceResponse:
        """Chuyển đổi dữ liệu sang DTO chuẩn."""
        loc = None
        if raw.get("latest_location"):
            loc = GeoPointSchema(**raw["latest_location"])

        maps_url = loc.to_google_maps_url() if loc else None

        return SafetyCheckInstanceResponse(
            instance_id=raw["instance_id"],
            user_id=raw["user_id"],
            template_id=raw.get("template_id"),
            name=raw.get("name", "Hẹn giờ an toàn"),
            status=SafetyCheckStatus(raw.get("status", SafetyCheckStatus.ACTIVE.value)),
            duration_minutes=raw.get("duration_minutes", 30),
            grace_period_seconds=raw.get("grace_period_seconds", 60),
            started_at=raw.get("started_at"),
            expires_at=raw.get("expires_at"),
            grace_period_until=raw.get("grace_period_until"),
            extension_count=raw.get("extension_count", 0),
            max_extensions=raw.get("max_extensions", 3),
            latest_location=loc,
            maps_url=maps_url,
            notes=raw.get("notes"),
            completed_at=raw.get("completed_at"),
            escalated_at=raw.get("escalated_at"),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    async def list_templates(self, user_id: str) -> List[SafetyCheckTemplateResponse]:
        """Lấy danh sách các mẫu template sẵn có."""
        raw_list = self.repository.list_templates(user_id)
        return [
            SafetyCheckTemplateResponse(
                template_id=tpl["template_id"],
                name=tpl["name"],
                description=tpl.get("description"),
                default_duration_minutes=tpl.get("default_duration_minutes", 30),
                default_grace_period_seconds=tpl.get("default_grace_period_seconds", 60),
                icon=tpl.get("icon", "shield"),
                is_system=tpl.get("is_system", True),
                created_by=tpl.get("created_by"),
                preset_durations=tpl.get("preset_durations"),
            )
            for tpl in raw_list
        ]

    async def create_custom_template(
        self, user_id: str, request: CreateCustomTemplateRequest
    ) -> SafetyCheckTemplateResponse:
        """Tạo template tùy chỉnh mới cho người dùng."""
        tpl_id = f"custom_{uuid.uuid4().hex[:8]}"
        data = request.model_dump()
        data["created_by"] = user_id

        saved = self.repository.create_custom_template(tpl_id, data)
        return SafetyCheckTemplateResponse(
            template_id=saved["template_id"],
            name=saved["name"],
            description=saved.get("description"),
            default_duration_minutes=saved.get("default_duration_minutes", 30),
            default_grace_period_seconds=saved.get("default_grace_period_seconds", 60),
            icon=saved.get("icon", "shield"),
            is_system=False,
            created_by=user_id,
            preset_durations=saved.get("preset_durations"),
        )

    async def update_template(self, user_id: str, template_id: str,
                              request: CreateCustomTemplateRequest) -> SafetyCheckTemplateResponse:
        current = self.repository.get_visible_template(user_id, template_id)
        if not current:
            raise EntityNotFoundException("Không tìm thấy kịch bản này.")
        data = {**request.model_dump(), "is_system": False,
                "created_by": user_id, "deleted": False}
        self.repository.save_template_override(user_id, template_id, data)
        return SafetyCheckTemplateResponse(**{**current, **data, "template_id": template_id})

    async def delete_template(self, user_id: str, template_id: str) -> None:
        if not self.repository.get_visible_template(user_id, template_id):
            raise EntityNotFoundException("Không tìm thấy kịch bản này.")
        self.repository.save_template_override(user_id, template_id, {"deleted": True})

    async def start_safety_check(
        self, user_id: str, request: StartSafetyCheckRequest
    ) -> SafetyCheckInstanceResponse:
        """Bắt đầu một phiên hẹn giờ an toàn mới."""
        # 1. Chặn nếu người dùng đang có phiên ACTIVE hoặc CHECK_REQUIRED
        existing = self.repository.get_active_instance_by_user(user_id)
        if existing:
            raise ValidationException("Bạn đang có một phiên hẹn giờ an toàn đang hoạt động. Vui lòng xác nhận hoặc hủy phiên trước.")

        now = datetime.now(timezone.utc)
        duration_minutes = request.duration_minutes
        grace_period_seconds = request.grace_period_seconds or self.settings.DEFAULT_SAFETY_CHECK_GRACE_PERIOD_SECONDS

        name = request.custom_name or "Hẹn giờ an toàn"
        if request.template_id:
            tpl = self.repository.get_visible_template(user_id, request.template_id)
            if not tpl:
                raise EntityNotFoundException("Không tìm thấy kịch bản này.")
            name = tpl["name"]
            if request.grace_period_seconds is None:
                grace_period_seconds = tpl.get("default_grace_period_seconds", grace_period_seconds)

        expires_at = now + timedelta(minutes=duration_minutes)
        grace_period_until = expires_at + timedelta(seconds=grace_period_seconds)

        instance_id = str(uuid.uuid4())
        geo_point = None
        if request.latitude is not None and request.longitude is not None:
            geo_point = GeoPointSchema(
                latitude=request.latitude,
                longitude=request.longitude,
            )

        data = {
            "instance_id": instance_id,
            "user_id": user_id,
            "template_id": request.template_id,
            "name": name,
            "status": SafetyCheckStatus.ACTIVE.value,
            "duration_minutes": duration_minutes,
            "grace_period_seconds": grace_period_seconds,
            "started_at": now,
            "expires_at": expires_at,
            "grace_period_until": grace_period_until,
            "extension_count": 0,
            "max_extensions": self.settings.MAX_SAFETY_CHECK_EXTENSIONS,
            "latest_location": geo_point.model_dump() if geo_point else None,
            "notes": request.notes,
        }

        saved = self.repository.create_instance(instance_id, data)

        # Ghi mốc tọa độ ban đầu nếu có
        if geo_point:
            try:
                await self.location_service.record_checkpoint(
                    user_id=user_id,
                    request=LocationCheckpointCreateRequest(
                        latitude=request.latitude,
                        longitude=request.longitude,
                        trigger_reason="SAFETY_CHECK_STARTED",
                        session_id=instance_id,
                        address_text=request.notes,
                    ),
                )
            except Exception as e:
                logger.warning(f"Lỗi ghi checkpoint khi start safety check: {str(e)}")

        return self._to_instance_response(saved)

    async def get_current_instance(self, user_id: str) -> Optional[SafetyCheckInstanceResponse]:
        """Lấy phiên Safety Check đang chạy của người dùng."""
        active = self.repository.get_active_instance_by_user(user_id)
        return self._to_instance_response(active) if active else None

    async def confirm_safe(
        self, user_id: str, instance_id: str, request: ConfirmSafeRequest
    ) -> SafetyCheckInstanceResponse:
        """Người dùng bấm 'Tôi an toàn' xác nhận hoàn thành phiên."""
        instance = self.repository.get_instance(instance_id)
        if not instance:
            raise EntityNotFoundException(f"Không tìm thấy phiên Safety Check với ID: {instance_id}")

        if instance.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền thao tác phiên này.")

        was_escalated = instance.get("status") == SafetyCheckStatus.ESCALATED.value
        now = datetime.now(timezone.utc)

        updated = self.repository.update_instance(
            instance_id,
            {
                "status": SafetyCheckStatus.COMPLETED.value,
                "completed_at": now,
            },
        )

        # Xử lý trường hợp đặc biệt (ADR-031): User bấm Tôi an toàn sau khi đã bị Escalate
        # -> Tự động gửi thông báo đính chính All-Clear cho người thân an tâm!
        if was_escalated:
            try:
                contacts = await self.contact_service.list_contacts(user_id)
                user_doc = self.user_repo.get_by_id(user_id) or {}
                user_name = user_doc.get("name") or "Người dùng"
                all_clear_payload = AllClearPayload(
                    user_name=user_name,
                    reason=request.note or "Người dùng đã nhập mã xác nhận an toàn sau khi hết giờ hẹn.",
                )
                await self.notification_service.broadcast_all_clear(user_id, contacts, all_clear_payload)
            except Exception as e:
                logger.warning(f"Lỗi gửi All-Clear sau khi escalate: {str(e)}")

        return self._to_instance_response(updated or instance)

    async def extend_timer(
        self, user_id: str, instance_id: str, request: ExtendSafetyCheckRequest
    ) -> SafetyCheckInstanceResponse:
        """Gia hạn thêm thời gian cho phiên đang chạy."""
        instance = self.repository.get_instance(instance_id)
        if not instance:
            raise EntityNotFoundException(f"Không tìm thấy phiên Safety Check với ID: {instance_id}")

        if instance.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền thao tác phiên này.")

        current_status = instance.get("status")
        if current_status not in [SafetyCheckStatus.ACTIVE.value, SafetyCheckStatus.CHECK_REQUIRED.value]:
            raise ValidationException(f"Không thể gia hạn phiên có trạng thái là '{current_status}'.")

        ext_count = instance.get("extension_count", 0)
        max_ext = instance.get("max_extensions", self.settings.MAX_SAFETY_CHECK_EXTENSIONS)
        if ext_count >= max_ext:
            raise ValidationException(f"Đã đạt giới hạn tối đa số lần gia hạn ({max_ext} lần).")

        # Tính toán thời gian mới
        curr_expires_at = instance.get("expires_at")
        if isinstance(curr_expires_at, str):
            curr_expires_at = datetime.fromisoformat(curr_expires_at)
        elif not curr_expires_at:
            curr_expires_at = datetime.now(timezone.utc)

        new_expires_at = curr_expires_at + timedelta(minutes=request.extend_minutes)
        grace_period_seconds = instance.get("grace_period_seconds", 60)
        new_grace_until = new_expires_at + timedelta(seconds=grace_period_seconds)

        updated = self.repository.update_instance(
            instance_id,
            {
                "status": SafetyCheckStatus.ACTIVE.value,
                "expires_at": new_expires_at,
                "grace_period_until": new_grace_until,
                "extension_count": ext_count + 1,
            },
        )
        return self._to_instance_response(updated or instance)

    async def cancel_instance(
        self, user_id: str, instance_id: str, request: CancelSafetyCheckRequest
    ) -> SafetyCheckInstanceResponse:
        """Người dùng chủ động hủy phiên hẹn giờ an toàn."""
        instance = self.repository.get_instance(instance_id)
        if not instance:
            raise EntityNotFoundException(f"Không tìm thấy phiên Safety Check với ID: {instance_id}")

        if instance.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền thao tác phiên này.")

        updated = self.repository.update_instance(
            instance_id,
            {
                "status": SafetyCheckStatus.CANCELLED.value,
            },
        )
        return self._to_instance_response(updated or instance)

    async def update_location(
        self, user_id: str, instance_id: str, latitude: float, longitude: float, accuracy: Optional[float] = None
    ) -> SafetyCheckInstanceResponse:
        """Cập nhật tọa độ GPS gần nhất trong quá trình hẹn giờ."""
        instance = self.repository.get_instance(instance_id)
        if not instance:
            raise EntityNotFoundException(f"Không tìm thấy phiên Safety Check với ID: {instance_id}")

        if instance.get("user_id") != user_id:
            raise UnauthorizedException("Bạn không có quyền thao tác phiên này.")

        loc = GeoPointSchema(latitude=latitude, longitude=longitude, accuracy_meters=accuracy)
        updated = self.repository.update_instance(
            instance_id,
            {
                "latest_location": loc.model_dump(),
            },
        )
        return self._to_instance_response(updated or instance)

    async def escalate_instance(self, instance: dict) -> SafetyCheckInstanceResponse:
        """
        Kích hoạt leo thang cảnh báo khi quá hạn Grace Period (Escalation).
        Chuyển trạng thái sang ESCALATED và gửi thông báo cảnh báo qua Telegram cho người thân.
        """
        instance_id = instance["instance_id"]
        user_id = instance["user_id"]
        now = datetime.now(timezone.utc)

        updated = self.repository.claim_overdue(instance_id, now)
        if updated is None:
            fresh = self.repository.get_instance(instance_id) or instance
            return self._to_instance_response(fresh)
        instance = updated

        # Phát tán thông báo cảnh báo Telegram cho người thân
        try:
            contacts = await self.contact_service.list_contacts(user_id)
            user_doc = self.user_repo.get_by_id(user_id) or {}
            user_name = user_doc.get("name") or "Người dùng Guardian AI"

            loc_dict = instance.get("latest_location")
            loc_schema = GeoPointSchema(**loc_dict) if loc_dict else None

            # Lấy thông tin y tế sơ cứu nếu không đặt PRIVATE
            med_data = self.medical_repo.get_by_uid(user_id) or {}
            privacy_level = med_data.get("privacy_level", MedicalPrivacyLevel.EMERGENCY_SHARABLE.value)

            blood_type = None
            allergies = []
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

                raw_conditions = med_data.get("chronic_conditions") or user_doc.get("chronic_conditions")
                if isinstance(raw_conditions, list):
                    chronic_conditions = [str(c).strip() for c in raw_conditions if c and str(c).strip() != "Không có"]
                elif isinstance(raw_conditions, str) and raw_conditions.strip() and raw_conditions.strip() != "Không có":
                    chronic_conditions = [c.strip() for c in raw_conditions.split(",") if c.strip()]

                medical_notes = med_data.get("medical_notes") or user_doc.get("medical_notes")
                if medical_notes == "Không có":
                    medical_notes = None

                backend_url = getattr(self.settings, "BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
                medical_profile_url = f"{backend_url}/api/v1/users/{user_id}/public-emergency"

            alert_payload = SafetyCheckAlertPayload(
                user_name=user_name,
                template_name=instance.get("name", "Hẹn giờ an toàn"),
                duration_minutes=instance.get("duration_minutes", 30),
                location=loc_schema,
                blood_type=blood_type,
                allergies=allergies,
                chronic_conditions=chronic_conditions,
                medical_notes=medical_notes,
                medical_profile_url=medical_profile_url,
            )
            await self.notification_service.broadcast_safety_check_timeout(user_id, contacts, alert_payload)
            logger.info(f"Đã escalate Safety Check instance '{instance_id}' và thông báo người thân.")
        except Exception as e:
            logger.error(f"Lỗi khi escalate safety check: {str(e)}")

        return self._to_instance_response(updated or instance)
