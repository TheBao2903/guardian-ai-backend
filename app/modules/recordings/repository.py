"""
=============================================================================
FILE: app/modules/recordings/repository.py
MODULE: Recordings - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `recordings`.
    - Lưu trữ, truy vấn và xóa metadata của các đoạn ghi âm bằng chứng khẩn cấp.
    - Đảm bảo tuân thủ ADR-006: Firestore chỉ lưu metadata và Cloudflare R2 lưu binary.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/recordings/service.py`.

INPUT / OUTPUT:
    - Input: recording_id, user_id, metadata dictionary.
    - Output: Recording metadata dictionaries, lists.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient, FieldFilter, Query

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class RecordingRepository:
    """Repository truy cập Firestore collection `recordings`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("recordings")

    def create(self, recording_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu metadata bản ghi âm vào Firestore."""
        doc_ref = self.collection.document(recording_id)
        data["recording_id"] = recording_id
        data["created_at"] = datetime.now(timezone.utc)

        doc_ref.set(data)
        logger.info(f"Đã lưu metadata ghi âm vào Firestore: recordings/{recording_id}")

        return data

    def update(self, recording_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cập nhật metadata bản ghi âm (partial update)."""
        doc_ref = self.collection.document(recording_id)
        doc = doc_ref.get()
        if not doc.exists:
            logger.warning(f"Không tìm thấy recording để update: recordings/{recording_id}")
            return None

        update_data["updated_at"] = datetime.now(timezone.utc)
        doc_ref.set(update_data, merge=True)
        logger.info(f"Đã cập nhật metadata ghi âm: recordings/{recording_id}")

        updated = doc_ref.get().to_dict() or {}
        updated["recording_id"] = recording_id
        return updated

    def get_by_id(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """Lấy metadata bản ghi âm theo ID."""
        doc = self.collection.document(recording_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["recording_id"] = recording_id
            return data
        return None

    def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các bản ghi âm của người dùng, sắp xếp mới nhất lên đầu (High Performance)."""
        try:
            # 1. Thử query native với Composite Index (user_id ASC + created_at DESC)
            docs = (
                self.collection
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["recording_id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.warning(f"Native index chưa sẵn sàng ({str(e)}), fallback in-memory sort.")
            docs = self.collection.where(filter=FieldFilter("user_id", "==", user_id)).stream()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["recording_id"] = doc.id
                results.append(data)

            # Sắp xếp in-memory theo created_at giảm dần
            results.sort(
                key=lambda r: str(r.get("created_at", "")),
                reverse=True,
            )
            return results[:limit]

    def delete(self, recording_id: str) -> bool:
        """Xóa metadata bản ghi âm."""
        doc_ref = self.collection.document(recording_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False

        doc_ref.delete()
        logger.info(f"Đã xóa metadata ghi âm khỏi Firestore: recordings/{recording_id}")
        return True
