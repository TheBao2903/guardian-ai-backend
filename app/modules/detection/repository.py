"""
=============================================================================
FILE: app/modules/detection/repository.py
MODULE: Detection - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `detection_events`.
    - Lưu vết kiểm toán (Audit Trail) cho mọi sự kiện âm thanh được ghi nhận và phân tích.
    - Cung cấp hàm truy vấn lịch sử phát hiện âm thanh theo từng người dùng.
    - Tuân thủ ADR-005, ADR-009.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/detection/service.py`.

INPUT / OUTPUT:
    - Input: event_id, user_id, dictionary payloads.
    - Output: Dictionaries, list of events.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.api_core.exceptions import ResourceExhausted
from google.cloud.firestore import Client as FirestoreClient, FieldFilter, Query

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class DetectionRepository:
    """Repository truy cập Firestore collection `detection_events`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("detection_events")

    def save_event(self, event_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu trữ một sự kiện phát hiện âm thanh vào Firestore."""
        doc_ref = self.collection.document(event_id)
        now = datetime.now(timezone.utc)
        data["event_id"] = event_id
        if "created_at" not in data or not data["created_at"]:
            data["created_at"] = now

        doc_ref.set(data)
        logger.info(f"Đã lưu detection event: detection_events/{event_id}")
        return data

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một sự kiện phát hiện theo ID."""
        doc = self.collection.document(event_id).get()
        if doc.exists:
            d = doc.to_dict() or {}
            d["event_id"] = doc.id
            return d
        return None

    def list_events_by_user(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách các sự kiện phát hiện gần nhất của người dùng (High Performance)."""
        try:
            # 1. Thử query native với Composite Index (user_id ASC + created_at DESC)
            docs = (
                self.collection
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            results: List[Dict[str, Any]] = []
            for doc in docs:
                d = doc.to_dict() or {}
                d["event_id"] = doc.id
                results.append(d)
            return results
        except ResourceExhausted:
            # A broader fallback query cannot repair exhausted quota.
            raise
        except Exception as e:
            logger.warning(f"Native index chưa sẵn sàng ({str(e)}), fallback in-memory sort.")
            try:
                docs = self.collection.where(filter=FieldFilter("user_id", "==", user_id)).stream()
                results = []
                for doc in docs:
                    d = doc.to_dict() or {}
                    d["event_id"] = doc.id
                    results.append(d)

                # Sắp xếp giảm dần theo thời gian tạo trong bộ nhớ Python
                results.sort(
                    key=lambda x: str(x.get("created_at") or ""),
                    reverse=True,
                )
                return results[:limit]
            except Exception as ex:
                logger.warning(f"Lỗi khi truy vấn detection_events của user {user_id}: {str(ex)}")
                return []
