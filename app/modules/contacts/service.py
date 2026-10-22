"""
=============================================================================
FILE: app/modules/contacts/service.py
MODULE: Contacts - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối nghiệp vụ danh bạ người thân:
      + Lấy danh sách sắp xếp theo độ ưu tiên.
      + Thêm mới người thân (tự động tính độ ưu tiên kế tiếp nếu không chỉ định).
      + Cập nhật thông tin và số điện thoại / Telegram ID.
      + Xóa liên hệ.
      + Sắp xếp lại danh sách thứ tự ưu tiên (Reorder Priority).
    - Đảm bảo tuân thủ nguyên tắc cách ly dữ liệu: Người dùng chỉ được xem/sửa liên hệ của chính mình.

CONNECTIONS / DEPENDENCIES:
    - app/modules/contacts/repository.py (ContactRepository)
    - app/modules/contacts/schemas.py (ContactResponse, ContactCreateRequest, ContactUpdateRequest, ContactReorderRequest)
    - app/core/exceptions.py (EntityNotFoundException)

INPUT / OUTPUT:
    - Input: user_id, contact_id, DTO requests.
    - Output: ContactResponse, List[ContactResponse].
=============================================================================
"""

from typing import List, Optional

from app.core.config import get_settings
from app.core.exceptions import EntityNotFoundException, ValidationException
from app.core.logging import logger
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.schemas import (
    ContactCreateRequest,
    ContactReorderRequest,
    ContactResponse,
    ContactUpdateRequest,
)
from app.shared.enums.contact import ContactRelationship


class ContactService:
    """Service điều phối nghiệp vụ danh bạ người thân khẩn cấp."""

    def __init__(self, repository: Optional[ContactRepository] = None) -> None:
        self.repository = repository or ContactRepository()

    def _to_response(self, raw: dict) -> ContactResponse:
        """Chuyển đổi dữ liệu thô sang DTO chuẩn."""
        return ContactResponse(
            id=raw["id"],
            user_id=raw["user_id"],
            name=raw.get("name", ""),
            relationship=ContactRelationship(raw.get("relationship", ContactRelationship.OTHER.value)),
            phone=raw.get("phone", ""),
            telegram_id=raw.get("telegram_id"),
            priority=raw.get("priority", 1),
            is_active=raw.get("is_active", True),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    async def list_contacts(self, user_id: str) -> List[ContactResponse]:
        """Lấy danh sách người liên hệ khẩn cấp sắp xếp theo priority tăng dần."""
        raw_list = self.repository.list_by_user(user_id)
        return [self._to_response(item) for item in raw_list]

    async def get_contact(self, user_id: str, contact_id: str) -> ContactResponse:
        """Lấy chi tiết một người liên hệ."""
        raw = self.repository.get_by_id(user_id, contact_id)
        if not raw:
            raise EntityNotFoundException(f"Không tìm thấy người liên hệ với ID: {contact_id}")
        return self._to_response(raw)

    async def create_contact(self, user_id: str, request: ContactCreateRequest) -> ContactResponse:
        """Thêm người liên hệ khẩn cấp mới (Giới hạn tối đa 10 người theo ADR-036)."""
        settings = get_settings()
        current_count = self.repository.count_by_user(user_id)
        if current_count >= settings.MAX_EMERGENCY_CONTACTS_PER_USER:
            raise ValidationException(
                f"Đã đạt giới hạn tối đa {settings.MAX_EMERGENCY_CONTACTS_PER_USER} người liên hệ khẩn cấp nhằm tối ưu băng thông và chi phí.",
                details={"max_contacts": settings.MAX_EMERGENCY_CONTACTS_PER_USER, "current_count": current_count},
            )

        data = request.model_dump()

        # Nếu không cung cấp priority, tự gán số kế tiếp
        if data.get("priority") is None:
            data["priority"] = current_count + 1

        if isinstance(data.get("relationship"), ContactRelationship):
            data["relationship"] = data["relationship"].value

        saved = self.repository.create(user_id, data)
        if data.get("priority") == 1 and current_count > 0:
            return await self.set_primary_contact(user_id, saved["id"])
        return self._to_response(saved)

    async def update_contact(
        self, user_id: str, contact_id: str, request: ContactUpdateRequest
    ) -> ContactResponse:
        """Cập nhật thông tin người liên hệ."""
        update_data = request.model_dump(exclude_unset=True, exclude_none=True)

        if "relationship" in update_data and isinstance(update_data["relationship"], ContactRelationship):
            update_data["relationship"] = update_data["relationship"].value

        updated = self.repository.update(user_id, contact_id, update_data)
        if not updated:
            raise EntityNotFoundException(f"Không tìm thấy người liên hệ với ID: {contact_id}")

        return self._to_response(updated)

    async def delete_contact(self, user_id: str, contact_id: str) -> None:
        """Xóa người liên hệ khỏi danh bạ."""
        deleted = self.repository.delete(user_id, contact_id)
        if not deleted:
            raise EntityNotFoundException(f"Không tìm thấy người liên hệ với ID: {contact_id}")

    async def reorder_contacts(
        self, user_id: str, request: ContactReorderRequest
    ) -> List[ContactResponse]:
        """Cập nhật thứ tự ưu tiên của danh bạ."""
        for item in request.orders:
            self.repository.update(user_id, item.id, {"priority": item.priority})

        return await self.list_contacts(user_id)

    async def set_primary_contact(self, user_id: str, contact_id: str) -> ContactResponse:
        """
        Đặt một liên hệ làm ưu tiên gọi #1.
        Tự động sắp xếp lại toàn bộ danh bạ: contact_id lên #1, các liên hệ còn lại là 2, 3, 4...
        """
        current_contacts = self.repository.list_by_user(user_id)
        target = next((c for c in current_contacts if c.get("id") == contact_id), None)
        if not target:
            raise EntityNotFoundException(f"Không tìm thấy người liên hệ với ID: {contact_id}")

        others = [c for c in current_contacts if c.get("id") != contact_id]
        others.sort(key=lambda c: c.get("priority", 99))

        # 1. Đặt priority = 1 cho contact mục tiêu
        self.repository.update(user_id, contact_id, {"priority": 1})

        # 2. Re-index các contacts còn lại tuần tự 2, 3, 4...
        for idx, other in enumerate(others, start=2):
            if other.get("priority") != idx:
                self.repository.update(user_id, other["id"], {"priority": idx})

        logger.info(f"Đã đặt '{target.get('name')}' làm liên hệ ưu tiên gọi #1 và tái lập thứ tự ưu tiên danh bạ.")
        updated = self.repository.get_by_id(user_id, contact_id)
        return self._to_response(updated)

    async def set_primary_on_create(
        self, user_id: str, contact_id: str
    ) -> ContactResponse:
        """Đặt một liên hệ mới làm ưu tiên gọi #1 khi tạo mới."""
        return await self.set_primary_contact(user_id, contact_id)

