"""
=============================================================================
FILE: app/modules/users/repository.py
MODULE: Users - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore collection `users` và subcollection `login_logs`.
    - Cung cấp các hàm tìm kiếm theo UID, cập nhật thông tin và kiểm tra sự tồn tại.
    - Cung cấp hàm truy vấn lịch sử đăng nhập (Login Logs Audit Trail).
    - Cung cấp hàm xóa dữ liệu cá nhân theo Quyền được lãng quên (Right to be Forgotten).

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - Được gọi bởi: `app/modules/users/service.py`.

INPUT / OUTPUT:
    - Input: uid, update dictionary, limit.
    - Output: User document, List of login logs.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient, Query

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class UserRepository:
    """Repository truy cập Firestore collection `users`."""

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.collection = self.db.collection("users")

    def get_by_id(self, uid: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin người dùng theo Firebase UID."""
        doc = self.collection.document(uid).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["uid"] = uid
            return data
        return None

    def update(self, uid: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Cập nhật dữ liệu người dùng trong Firestore."""
        doc_ref = self.collection.document(uid)
        update_data["updated_at"] = datetime.now(timezone.utc)
        doc_ref.set(update_data, merge=True)
        logger.info(f"Đã cập nhật Firestore user doc: users/{uid}")

        # Trả về dữ liệu mới nhất
        updated_doc = doc_ref.get()
        data = updated_doc.to_dict() or {}
        data["uid"] = uid
        return data

    def get_login_logs(self, uid: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Truy vấn danh sách lịch sử đăng nhập gần nhất của người dùng."""
        logs_ref = (
            self.collection.document(uid)
            .collection("login_logs")
            .order_by("timestamp", direction=Query.DESCENDING)
            .limit(limit)
        )
        logs = []
        for doc in logs_ref.stream():
            log_data = doc.to_dict() or {}
            # Chuẩn hóa timestamp sang chuỗi ISO
            ts = log_data.get("timestamp")
            if hasattr(ts, "isoformat"):
                log_data["timestamp"] = ts.isoformat()
            else:
                log_data["timestamp"] = str(ts)
            logs.append(log_data)
        return logs

    def delete_all_user_data(self, uid: str) -> None:
        """Thực thi Quyền được lãng quên (Right to be Forgotten): Xóa toàn bộ dữ liệu người dùng."""
        user_ref = self.collection.document(uid)

        # Xóa các subcollections nếu có
        for sub_col in ["login_logs", "emergency_contacts"]:
            for doc in user_ref.collection(sub_col).stream():
                doc.reference.delete()

        # Đánh dấu trạng thái tài khoản là đã xóa hoặc xóa document
        user_ref.delete()
        logger.warning(f"Đã xóa hoàn toàn dữ liệu cá nhân của UID: {uid} theo Quyền được lãng quên.")
