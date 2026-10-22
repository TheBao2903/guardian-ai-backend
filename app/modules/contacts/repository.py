"""
=============================================================================
FILE: app/modules/contacts/repository.py
MODULE: Contacts - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore subcollection `users/{user_id}/emergency_contacts`.
    - Cung cấp các thao tác CRUD và sắp xếp theo độ ưu tiên `priority`.
    - Đảm bảo tính toàn vẹn dữ liệu cho từng chủ tài khoản.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/contacts/service.py`.

INPUT / OUTPUT:
    - Input: user_id, contact_id, payload dictionary.
    - Output: Contact dictionaries, lists.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class ContactRepository:
    """Repository truy cập Firestore subcollection `users/{user_id}/emergency_contacts`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()

    def _get_collection(self, user_id: str):
        return self.db.collection("users").document(user_id).collection("emergency_contacts")

    def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh bạ người thân của user sắp xếp theo priority tăng dần."""
        collection_ref = self._get_collection(user_id)
        docs = collection_ref.stream()

        contacts = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            data["user_id"] = user_id
            contacts.append(data)

        # Sắp xếp theo priority tăng dần (1, 2, 3...)
        contacts.sort(key=lambda c: c.get("priority", 99))
        return contacts

    def get_by_id(self, user_id: str, contact_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một liên hệ theo ID."""
        doc = self._get_collection(user_id).document(contact_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            data["user_id"] = user_id
            return data
        return None

    def create(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo mới một người liên hệ khẩn cấp."""
        collection_ref = self._get_collection(user_id)
        doc_ref = collection_ref.document()

        now = datetime.now(timezone.utc)
        data["created_at"] = now
        data["updated_at"] = now
        data["user_id"] = user_id

        doc_ref.set(data)
        logger.info(f"Đã tạo liên hệ khẩn cấp mới: users/{user_id}/emergency_contacts/{doc_ref.id}")

        data["id"] = doc_ref.id
        return data

    def update(self, user_id: str, contact_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cập nhật thông tin một liên hệ."""
        doc_ref = self._get_collection(user_id).document(contact_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None

        data["updated_at"] = datetime.now(timezone.utc)
        doc_ref.set(data, merge=True)
        logger.info(f"Đã cập nhật liên hệ khẩn cấp: users/{user_id}/emergency_contacts/{contact_id}")

        updated_doc = doc_ref.get()
        result = updated_doc.to_dict() or {}
        result["id"] = contact_id
        result["user_id"] = user_id
        return result

    def delete(self, user_id: str, contact_id: str) -> bool:
        """Xóa một liên hệ khỏi danh bạ."""
        doc_ref = self._get_collection(user_id).document(contact_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.delete()
        logger.info(f"Đã xóa liên hệ khẩn cấp: users/{user_id}/emergency_contacts/{contact_id}")
        return True

    def count_by_user(self, user_id: str) -> int:
        """Đếm số lượng liên hệ của người dùng."""
        return len(list(self._get_collection(user_id).stream()))
