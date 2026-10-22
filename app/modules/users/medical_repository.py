"""
=============================================================================
FILE: app/modules/users/medical_repository.py
MODULE: Users - Emergency Medical Profile Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `emergency_profiles`.
    - Cung cấp các hàm tìm kiếm theo UID, tạo mới / cập nhật (upsert) và xóa hồ sơ y tế.
    - Hỗ trợ lưu trữ tuân thủ các quy tắc bảo mật dữ liệu sức khỏe.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/users/medical_service.py`.

INPUT / OUTPUT:
    - Input: uid, update dictionary.
    - Output: Emergency profile dict.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from google.cloud.firestore import Client as FirestoreClient

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class MedicalProfileRepository:
    """Repository truy cập Firestore collection `emergency_profiles`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("emergency_profiles")

    def get_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """Lấy hồ sơ y tế khẩn cấp theo UID người dùng."""
        doc = self.collection.document(uid).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["uid"] = uid
            return data
        return None

    def upsert(self, uid: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo mới hoặc cập nhật thông tin hồ sơ y tế (upsert merge)."""
        doc_ref = self.collection.document(uid)
        profile_data["uid"] = uid
        profile_data["updated_at"] = datetime.now(timezone.utc)

        doc_ref.set(profile_data, merge=True)
        logger.info(f"Đã lưu hồ sơ y tế khẩn cấp: emergency_profiles/{uid}")

        updated_doc = doc_ref.get()
        data = updated_doc.to_dict() or {}
        data["uid"] = uid
        return data

    def delete(self, uid: str) -> None:
        """Xóa hồ sơ y tế khi người dùng thực thi Quyền được lãng quên."""
        self.collection.document(uid).delete()
        logger.warning(f"Đã xóa hồ sơ y tế khẩn cấp của UID: {uid}")
