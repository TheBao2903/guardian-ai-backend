"""
=============================================================================
FILE: app/modules/emergency/repository.py
MODULE: Emergency - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `emergency_sessions`.
    - Quản lý các tài liệu phiên khẩn cấp, tìm kiếm phiên đang ACTIVE của người dùng
      nhằm phục vụ cơ chế chống trùng lặp Idempotent (ADR-014).
    - Cập nhật trạng thái chuyển đổi (State Transitions) của phiên.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/emergency/service.py`.

INPUT / OUTPUT:
    - Input: session_id, user_id, session data dictionary.
    - Output: Emergency session dictionaries, lists.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient, FieldFilter

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client
from app.shared.enums.emergency import EmergencyStatus


class EmergencyRepository:
    """Repository truy cập Firestore collection `emergency_sessions`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("emergency_sessions")

    def create(self, session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo một phiên khẩn cấp mới trong Firestore."""
        from app.modules.detection.alerts.store import FirestoreStore
        from app.modules.detection.alerts.repository import ensure_active_session
        now = datetime.now(timezone.utc)
        data = dict(data, session_id=session_id, created_at=now, updated_at=now)
        return FirestoreStore(self.db).atomic(lambda tx: ensure_active_session(tx, data['user_id'], data))

    def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin phiên khẩn cấp theo ID."""
        doc = self.collection.document(session_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["session_id"] = session_id
            return data
        return None

    def get_active_session_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Tìm phiên khẩn cấp đang ACTIVE của người dùng (Cơ chế Idempotent).
        Nếu người dùng đã có phiên đang ACTIVE, không tạo thêm phiên mới.
        """
        docs = self.collection.where(filter=FieldFilter("user_id", "==", user_id)).stream()
        for doc in docs:
            data = doc.to_dict() or {}
            if data.get("status") == EmergencyStatus.ACTIVE.value:
                data["session_id"] = doc.id
                return data
        return None

    def update(self, session_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cập nhật dữ liệu hoặc chuyển đổi trạng thái của phiên khẩn cấp."""
        doc_ref = self.collection.document(session_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None

        update_data["updated_at"] = datetime.now(timezone.utc)
        doc_ref.set(update_data, merge=True)
        logger.info(f"Đã cập nhật emergency session: emergency_sessions/{session_id}")

        updated = doc_ref.get().to_dict() or {}
        updated["session_id"] = session_id
        return updated

    def list_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các phiên khẩn cấp lịch sử của người dùng (High Performance)."""
        try:
            # Truy vấn Native tối ưu với Composite Index (user_id ASC + created_at DESC)
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
                data["session_id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.warning(f"Firestore Index chưa sẵn sàng ({str(e)}), fallback in-memory sort.")
            docs = self.collection.where(filter=FieldFilter("user_id", "==", user_id)).stream()
            results = []
            for doc in docs:
                data = doc.to_dict() or {}
                data["session_id"] = doc.id
                results.append(data)
            results.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
            return results[:limit]
