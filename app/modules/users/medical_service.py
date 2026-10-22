"""
=============================================================================
FILE: app/modules/users/medical_service.py
MODULE: Users - Emergency Medical Profile Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối nghiệp vụ quản lý hồ sơ y tế khẩn cấp:
      + Lấy hồ sơ y tế riêng tư đầy đủ (Tier 1 Private cho chính chủ).
      + Cập nhật thông tin y tế và tùy chọn hiển thị màn hình khóa (Tier 2).
      + Trích xuất hồ sơ khẩn cấp công khai (Tier 3 Lock-Screen Public) cho nhân viên y tế / người sơ cứu.
    - Áp dụng nguyên tắc Data Minimization: Không bao giờ để lộ dữ liệu nhạy cảm nếu người dùng không cho phép hoặc chọn chế độ riêng tư (ADR-017).

CONNECTIONS / DEPENDENCIES:
    - app/modules/users/medical_repository.py (MedicalProfileRepository)
    - app/modules/users/repository.py (UserRepository)
    - app/modules/users/medical_schemas.py (MedicalProfileResponse, UpdateMedicalProfileRequest, PublicEmergencyProfileResponse, EmergencyContactQuickDial)
    - app/shared/enums/user.py (BloodType, MedicalPrivacyLevel)
    - app/core/exceptions.py (EntityNotFoundException)

INPUT / OUTPUT:
    - Input: uid, UpdateMedicalProfileRequest.
    - Output: MedicalProfileResponse, PublicEmergencyProfileResponse.
=============================================================================
"""

from typing import List, Optional
from google.cloud.firestore import Client as FirestoreClient, FieldFilter

from app.core.exceptions import EntityNotFoundException
from app.infrastructure.firestore.client import get_firestore_client
from app.modules.users.medical_repository import MedicalProfileRepository
from app.modules.users.medical_schemas import (
    EmergencyContactQuickDial,
    MedicalProfileResponse,
    PublicEmergencyProfileResponse,
    UpdateMedicalProfileRequest,
)
from app.modules.users.repository import UserRepository
from app.shared.enums.user import BloodType, MedicalPrivacyLevel


class MedicalProfileService:
    """Service xử lý logic nghiệp vụ hồ sơ y tế khẩn cấp và bảo vệ dữ liệu sức khỏe."""

    def __init__(
        self,
        medical_repo: Optional[MedicalProfileRepository] = None,
        user_repo: Optional[UserRepository] = None,
        db: Optional[FirestoreClient] = None,
    ) -> None:
        self.medical_repo = medical_repo or MedicalProfileRepository()
        self.user_repo = user_repo or UserRepository()
        self.db = db or get_firestore_client()

    async def get_medical_profile(self, uid: str) -> MedicalProfileResponse:
        """Lấy hồ sơ y tế đầy đủ của chính chủ (Tier 1 - Authenticated)."""
        data = self.medical_repo.get_by_uid(uid)
        if not data:
            # Nếu chưa tạo, trả về bản ghi mặc định an toàn
            return MedicalProfileResponse(
                uid=uid,
                blood_type=BloodType.UNKNOWN,
                allergies=[],
                medications=[],
                chronic_conditions=[],
                organ_donor=False,
                privacy_level=MedicalPrivacyLevel.EMERGENCY_SHARABLE,
            )

        return MedicalProfileResponse(
            uid=uid,
            blood_type=BloodType(data.get("blood_type", BloodType.UNKNOWN)),
            height_cm=data.get("height_cm"),
            weight_kg=data.get("weight_kg"),
            allergies=data.get("allergies", []),
            medications=data.get("medications", []),
            chronic_conditions=data.get("chronic_conditions", []),
            organ_donor=data.get("organ_donor", False),
            medical_notes=data.get("medical_notes"),
            privacy_level=MedicalPrivacyLevel(data.get("privacy_level", MedicalPrivacyLevel.EMERGENCY_SHARABLE)),
            share_blood_type_on_lock_screen=data.get("share_blood_type_on_lock_screen", True),
            share_allergies_on_lock_screen=data.get("share_allergies_on_lock_screen", True),
            share_medications_on_lock_screen=data.get("share_medications_on_lock_screen", False),
            share_chronic_conditions_on_lock_screen=data.get("share_chronic_conditions_on_lock_screen", False),
            share_organ_donor_on_lock_screen=data.get("share_organ_donor_on_lock_screen", True),
            share_notes_on_lock_screen=data.get("share_notes_on_lock_screen", False),
            updated_at=data.get("updated_at"),
        )

    async def update_medical_profile(
        self, uid: str, request: UpdateMedicalProfileRequest
    ) -> MedicalProfileResponse:
        """Cập nhật thông tin hồ sơ y tế (Tier 2 - Authenticated Update)."""
        update_data = request.model_dump(exclude_unset=True, exclude_none=True)

        # Chuyển đổi enum sang giá trị string nếu có
        if "blood_type" in update_data and isinstance(update_data["blood_type"], BloodType):
            update_data["blood_type"] = update_data["blood_type"].value
        if "privacy_level" in update_data and isinstance(update_data["privacy_level"], MedicalPrivacyLevel):
            update_data["privacy_level"] = update_data["privacy_level"].value

        saved_data = self.medical_repo.upsert(uid, update_data)

        return MedicalProfileResponse(
            uid=uid,
            blood_type=BloodType(saved_data.get("blood_type", BloodType.UNKNOWN)),
            height_cm=saved_data.get("height_cm"),
            weight_kg=saved_data.get("weight_kg"),
            allergies=saved_data.get("allergies", []),
            medications=saved_data.get("medications", []),
            chronic_conditions=saved_data.get("chronic_conditions", []),
            organ_donor=saved_data.get("organ_donor", False),
            medical_notes=saved_data.get("medical_notes"),
            privacy_level=MedicalPrivacyLevel(saved_data.get("privacy_level", MedicalPrivacyLevel.EMERGENCY_SHARABLE)),
            share_blood_type_on_lock_screen=saved_data.get("share_blood_type_on_lock_screen", True),
            share_allergies_on_lock_screen=saved_data.get("share_allergies_on_lock_screen", True),
            share_medications_on_lock_screen=saved_data.get("share_medications_on_lock_screen", False),
            share_chronic_conditions_on_lock_screen=saved_data.get("share_chronic_conditions_on_lock_screen", False),
            share_organ_donor_on_lock_screen=saved_data.get("share_organ_donor_on_lock_screen", True),
            share_notes_on_lock_screen=saved_data.get("share_notes_on_lock_screen", False),
            updated_at=saved_data.get("updated_at"),
        )

    async def get_public_emergency_profile(self, user_id: str) -> PublicEmergencyProfileResponse:
        """
        Trích xuất thông tin y tế khẩn cấp công khai ngoài màn hình khóa (Tier 3 - Lock Screen Public).
        Tuân thủ nghiêm ngặt quyền riêng tư theo Nghị định 13/2023/NĐ-CP:
        - Nếu privacy_level là PRIVATE: Giấu toàn bộ thông tin bệnh án.
        - Chỉ hiển thị những mục mà người dùng đã cho phép qua cờ `share_*_on_lock_screen`.
        """
        user_data = self.user_repo.get_by_id(user_id)
        if not user_data:
            raise EntityNotFoundException(f"Không tìm thấy người dùng với ID: {user_id}")

        display_name = user_data.get("display_name") or user_data.get("name")
        age = user_data.get("age")

        # Lấy danh bạ khẩn cấp phục vụ gọi điện nhanh
        quick_contacts: List[EmergencyContactQuickDial] = []
        try:
            contacts_docs = (
                self.db.collection("users")
                .document(user_id)
                .collection("emergency_contacts")
                .stream()
            )
            raw_active = []
            for c in contacts_docs:
                cd = c.to_dict() or {}
                if cd.get("is_active", True):
                    raw_active.append(cd)

            # Sắp xếp theo thứ tự ưu tiên (Priority 1, 2, 3...)
            raw_active.sort(key=lambda x: x.get("priority", 99))

            for cd in raw_active[:3]:
                quick_contacts.append(
                    EmergencyContactQuickDial(
                        name=cd.get("name", "Người thân"),
                        relationship=cd.get("relationship", "OTHER"),
                        phone=cd.get("phone", ""),
                        priority=cd.get("priority", 1),
                    )
                )
        except Exception:
            pass

        med_data = self.medical_repo.get_by_uid(user_id)
        if not med_data:
            return PublicEmergencyProfileResponse(
                user_id=user_id,
                display_name=display_name,
                age=age,
                emergency_contacts=quick_contacts,
                is_private=False,
            )

        privacy_level = med_data.get("privacy_level", MedicalPrivacyLevel.EMERGENCY_SHARABLE.value)

        # Nếu người dùng cài đặt hoàn toàn riêng tư:
        if privacy_level == MedicalPrivacyLevel.PRIVATE.value:
            return PublicEmergencyProfileResponse(
                user_id=user_id,
                display_name=display_name,
                age=age,
                emergency_contacts=quick_contacts,
                is_private=True,
                blood_type=None,
                allergies=[],
                medications=[],
                chronic_conditions=[],
                organ_donor=None,
                medical_notes=None,
            )

        # Lọc dữ liệu theo cấu hình chia sẻ màn hình khóa
        blood_type = med_data.get("blood_type") if med_data.get("share_blood_type_on_lock_screen", True) else None
        allergies = med_data.get("allergies", []) if med_data.get("share_allergies_on_lock_screen", True) else []
        medications = med_data.get("medications", []) if med_data.get("share_medications_on_lock_screen", False) else []
        chronic_conditions = med_data.get("chronic_conditions", []) if med_data.get("share_chronic_conditions_on_lock_screen", False) else []
        organ_donor = med_data.get("organ_donor") if med_data.get("share_organ_donor_on_lock_screen", True) else None
        medical_notes = med_data.get("medical_notes") if med_data.get("share_notes_on_lock_screen", False) else None

        return PublicEmergencyProfileResponse(
            user_id=user_id,
            display_name=display_name,
            age=age,
            blood_type=blood_type,
            allergies=allergies,
            medications=medications,
            chronic_conditions=chronic_conditions,
            organ_donor=organ_donor,
            medical_notes=medical_notes,
            emergency_contacts=quick_contacts,
            is_private=False,
        )
