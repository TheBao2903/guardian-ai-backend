"""
=============================================================================
FILE: app/modules/users/service.py
MODULE: Users - Application Service
ROLE / RESPONSIBILITY:
    - Điều phối logic nghiệp vụ xem và cập nhật hồ sơ cá nhân người dùng.
    - Truy vấn lịch sử đăng nhập phục vụ màn hình bảo mật tài khoản.
    - Thực thi yêu cầu xóa dữ liệu cá nhân theo Quyền được lãng quên (Right to be Forgotten).

CONNECTIONS / DEPENDENCIES:
    - app/modules/users/repository.py (UserRepository)
    - app/modules/users/schemas.py (UserProfileResponse, UpdateProfileRequest)
    - app/modules/auth/schemas.py (LoginLogItem)
    - app/core/exceptions.py (EntityNotFoundException)

INPUT / OUTPUT:
    - Input: uid, UpdateProfileRequest, limit.
    - Output: UserProfileResponse, List[LoginLogItem].
=============================================================================
"""

from datetime import datetime, timezone
from typing import List, Optional
from starlette.concurrency import run_in_threadpool
from app.core.exceptions import EntityNotFoundException
from app.core.logging import logger
from app.core.security import PinHasher
from app.modules.auth.schemas import LoginLogItem
from app.modules.users.medical_repository import MedicalProfileRepository
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    UpdateDeviceLocationRequest,
    UpdateProfileRequest,
    UserPinsResponse,
    UserPinsUpdateRequest,
    UserProfileResponse,
)


class UserService:
    """Service xử lý nghiệp vụ quản lý thông tin hồ sơ người dùng."""

    def __init__(
        self,
        repository: Optional[UserRepository] = None,
        medical_repo: Optional[MedicalProfileRepository] = None,
    ) -> None:
        self.repository = repository or UserRepository()
        self.medical_repo = medical_repo or MedicalProfileRepository()

    def _map_to_response(self, uid: str, data: dict) -> UserProfileResponse:
        """Helper chuẩn hóa Firestore data thành UserProfileResponse."""
        med_data = self.medical_repo.get_by_uid(uid) or {}
        blood_type = med_data.get("blood_type") or data.get("blood_type")
        allergies = med_data.get("allergies") or data.get("allergies")
        medical_notes = med_data.get("medical_notes") or data.get("medical_notes")

        return UserProfileResponse(
            uid=uid,
            email=data.get("email"),
            name=data.get("name") or data.get("display_name"),
            display_name=data.get("display_name") or data.get("name"),
            phone=data.get("phone"),
            age=data.get("age"),
            date_of_birth=data.get("date_of_birth"),
            avatar_url=data.get("avatar_url"),
            telegram_id=data.get("telegram_id"),
            telegram_enabled=data.get("telegram_enabled", False),
            device_info=data.get("device_info"),
            location_permission_granted=data.get("location_permission_granted", False),
            last_known_location=data.get("last_known_location"),
            role=data.get("role", "user"),
            status=data.get("status", "active"),
            blood_type=blood_type,
            allergies=allergies,
            medical_notes=medical_notes,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    async def get_profile(self, uid: str) -> UserProfileResponse:
        """Lấy thông tin hồ sơ cá nhân của người dùng."""
        user_data = self.repository.get_by_id(uid)
        if not user_data:
            raise EntityNotFoundException(f"Không tìm thấy hồ sơ người dùng với UID: {uid}")

        return self._map_to_response(uid, user_data)

    async def update_profile(self, uid: str, data: UpdateProfileRequest) -> UserProfileResponse:
        """Cập nhật thông tin hồ sơ cá nhân."""
        update_dict = data.model_dump(exclude_unset=True, exclude_none=True)

        if "name" in update_dict:
            update_dict["display_name"] = update_dict["name"]

        updated_data = self.repository.update(uid, update_dict)
        return self._map_to_response(uid, updated_data)

    async def update_device_location(self, uid: str, data: UpdateDeviceLocationRequest) -> UserProfileResponse:
        """Đăng ký thiết bị và ủy quyền vị trí khẩn cấp cho người dùng."""
        return await run_in_threadpool(self._update_device_location, uid, data)

    def _update_device_location(self, uid: str, data: UpdateDeviceLocationRequest) -> UserProfileResponse:
        device_dict = {
            "device_name": data.device_name,
            "platform": data.platform,
            "os_version": data.os_version,
            "updated_at": datetime.now(timezone.utc),
        }

        update_dict = {
            "device_info": device_dict,
            "location_permission_granted": data.location_permission_granted,
        }

        if data.latitude is not None and data.longitude is not None:
            update_dict["last_known_location"] = {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "accuracy": data.accuracy,
                "address": data.address,
                "updated_at": datetime.now(timezone.utc),
            }

        updated_data = self.repository.update(uid, update_dict)
        return self._map_to_response(uid, updated_data)

    async def get_login_history(self, uid: str, limit: int = 10) -> List[LoginLogItem]:
        """Lấy danh sách các lần đăng nhập gần nhất của người dùng."""
        raw_logs = self.repository.get_login_logs(uid, limit=limit)
        items = []
        for log in raw_logs:
            items.append(
                LoginLogItem(
                    log_id=log.get("log_id", ""),
                    timestamp=str(log.get("timestamp", "")),
                    ip_address=log.get("ip_address", "unknown"),
                    user_agent=log.get("user_agent", "unknown"),
                    login_method=log.get("login_method", "UNKNOWN"),
                    status=log.get("status", "SUCCESS"),
                )
            )
        return items

    async def delete_user_data(self, uid: str) -> None:
        """Thực thi Quyền được lãng quên: Xóa dữ liệu cá nhân theo yêu cầu."""
        self.repository.delete_all_user_data(uid)
        self.medical_repo.delete(uid)

    # ============================================================================
    # PIN MANAGEMENT (PLAN_PIN_VERIFICATION_OVERHAUL.md - Phase 2)
    # ============================================================================

    async def verify_user_pin(self, uid: str, pin_code: str, *, duress: bool = False) -> None:
        from app.core.exceptions import UnauthorizedException
        user = self.repository.get_by_id(uid) or {}
        if not PinHasher.verify_user_pin(pin_code, user, duress=duress):
            raise UnauthorizedException('Mã PIN không chính xác')

    async def update_user_pins(
        self, uid: str, request: UserPinsUpdateRequest
    ) -> UserPinsResponse:
        """Hash và lưu mã PIN an toàn / mã PIN cưỡng bức vào Firestore.

        - PIN được hash bằng bcrypt (rounds=10, ~100ms/lần).
        - Sau khi đổi, fallback '1234'/'9999' bị vô hiệu hóa vĩnh viễn.
        - Plain text PIN KHÔNG BAO GIỜ được lưu - chỉ hash.
        - Có thể cập nhật 1 hoặc cả 2 PIN trong cùng 1 request.

        Args:
            uid: Firebase UID của user.
            request: UserPinsUpdateRequest chứa sos_pin và/hoặc duress_pin.

        Returns:
            UserPinsResponse với metadata (sos_pin_set, duress_pin_set, ...).
            KHÔNG trả về PIN thật - chỉ mask '****'.

        Raises:
            ValidationException: Nếu PIN không hợp lệ (không phải 4 chữ số).
        """
        if request.sos_pin is None and request.duress_pin is None:
            raise ValueError("Cần cung cấp ít nhất sos_pin hoặc duress_pin")

        from app.core.exceptions import ValidationException
        user = self.repository.get_by_id(uid) or {}
        if request.sos_pin is not None and request.duress_pin is not None:
            collision = request.sos_pin == request.duress_pin
        elif request.sos_pin is not None:
            collision = PinHasher.verify_user_pin(request.sos_pin, user, duress=True)
        else:
            collision = PinHasher.verify_user_pin(request.duress_pin, user)
        if collision:
            raise ValidationException('Mã PIN này đã được sử dụng, vui lòng chọn mã khác')

        update_dict: dict = {"updated_at": datetime.now(timezone.utc)}

        if request.sos_pin is not None:
            # PinHasher.hash_pin sẽ raise ValueError nếu format sai
            try:
                sos_hash = PinHasher.hash_pin(request.sos_pin)
            except ValueError as e:
                from app.core.exceptions import ValidationException
                raise ValidationException(str(e))
            update_dict["sos_pin_hash"] = sos_hash
            update_dict["has_changed_sos_pin"] = True
            logger.info(f"User {uid} đã cập nhật SOS PIN")

        if request.duress_pin is not None:
            try:
                duress_hash = PinHasher.hash_pin(request.duress_pin)
            except ValueError as e:
                from app.core.exceptions import ValidationException
                raise ValidationException(str(e))
            update_dict["duress_pin_hash"] = duress_hash
            update_dict["has_changed_duress_pin"] = True
            logger.info(f"User {uid} đã cập nhật Duress PIN")

        self.repository.update(uid, update_dict)

        # Trả về metadata (KHÔNG trả về hash)
        user_doc = self.repository.get_by_id(uid) or {}
        return UserPinsResponse(
            sos_pin_set=bool(user_doc.get("sos_pin_hash")),
            duress_pin_set=bool(user_doc.get("duress_pin_hash")),
            sos_pin_masked="****",
            duress_pin_masked="****",
            has_changed_sos_pin=bool(user_doc.get("has_changed_sos_pin", False)),
            has_changed_duress_pin=bool(user_doc.get("has_changed_duress_pin", False)),
        )
