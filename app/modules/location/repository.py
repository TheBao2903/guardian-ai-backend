"""
=============================================================================
FILE: app/modules/location/repository.py
MODULE: Location - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `location_checkpoints`.
    - Lưu trữ các tọa độ quan trọng (Checkpoints) khi kích hoạt SOS hoặc sự kiện AI.
    - Cung cấp hàm truy vấn lịch sử mốc tọa độ và lấy mốc vị trí mới nhất.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/location/service.py`.

INPUT / OUTPUT:
    - Input: checkpoint_id, user_id, checkpoint data dictionary.
    - Output: Location checkpoint dictionaries, lists.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient, FieldFilter, Query

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class LocationRepository:
    """Repository truy cập Firestore collection `location_checkpoints`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("location_checkpoints")

    def create(self, checkpoint_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu một điểm mốc vị trí mới vào Firestore."""
        doc_ref = self.collection.document(checkpoint_id)
        data["id"] = checkpoint_id
        data["created_at"] = datetime.now(timezone.utc)

        doc_ref.set(data)
        logger.info(f"Đã lưu location checkpoint: location_checkpoints/{checkpoint_id}")
        return data

    def get_by_id(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin một checkpoint theo ID."""
        doc = self.collection.document(checkpoint_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["id"] = checkpoint_id
            return data
        return None

    def list_by_user(
        self, user_id: str, session_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách các checkpoints của người dùng, sắp xếp mới nhất lên đầu (High Performance)."""
        try:
            # 1. Thử query native với Composite Index
            query = self.collection
            if session_id:
                query = query.where(filter=FieldFilter("session_id", "==", session_id))
            else:
                query = query.where(filter=FieldFilter("user_id", "==", user_id))

            docs = query.order_by("created_at", direction=Query.DESCENDING).limit(limit).stream()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.warning(f"Native index chưa sẵn sàng ({str(e)}), fallback in-memory sort.")
            docs = self.collection.where(filter=FieldFilter("user_id", "==", user_id)).stream()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                if session_id and data.get("session_id") != session_id:
                    continue
                results.append(data)

            # Sắp xếp in-memory theo created_at giảm dần
            results.sort(
                key=lambda item: str(item.get("created_at", "")),
                reverse=True,
            )
            return results[:limit]

    def get_latest_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy điểm mốc vị trí mới nhất của người dùng."""
        checkpoints = self.list_by_user(user_id=user_id, limit=1)
        return checkpoints[0] if checkpoints else None
