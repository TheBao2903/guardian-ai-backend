"""
=============================================================================
FILE: app/modules/emergency/safety_check/repository.py
MODULE: Safety Check - Repository Layer
ROLE / RESPONSIBILITY:
    - Thao tác trực tiếp với Firestore:
      + Collection `safety_check_templates`: Quản lý 5 mẫu mặc định và mẫu tùy chỉnh của user.
      + Collection `safety_check_instances`: Quản lý các phiên đếm ngược an toàn của từng tài khoản.
    - Tự động gieo mầm (Seed) 5 template mặc định theo ADR-031 khi khởi tạo.
    - Cung cấp hàm tìm kiếm phiên đang chạy (`ACTIVE` / `CHECK_REQUIRED`) và quét phiên quá hạn cho Scheduler.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - app/shared/enums/safety_check.py (SafetyCheckStatus, DefaultTemplateId)
    - Được gọi bởi: `app/modules/emergency/safety_check/service.py`, `scheduler.py`.

INPUT / OUTPUT:
    - Input: template_id, instance_id, user_id, dictionary payloads.
    - Output: Template and instance dictionaries, lists.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from google.cloud.firestore import Client as FirestoreClient, FieldFilter

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client
from app.infrastructure.firestore.watched_query import WatchedQuery
from app.shared.enums.safety_check import DefaultTemplateId, SafetyCheckStatus

DEFAULT_SYSTEM_TEMPLATES = [
    {
        "template_id": DefaultTemplateId.WALKING_HOME.value,
        "name": "Đi bộ về nhà",
        "description": "Bảo vệ khi đi bộ trong đêm hoặc qua những đoạn đường vắng.",
        "default_duration_minutes": 20,
        "default_grace_period_seconds": 60,
        "icon": "walking",
        "is_system": True,
    },
    {
        "template_id": DefaultTemplateId.COMMUTE_TRANSIT.value,
        "name": "Di chuyển bằng xe",
        "description": "Theo dõi chuyến đi xe taxi, xe ôm công nghệ hoặc phương tiện công cộng.",
        "default_duration_minutes": 45,
        "default_grace_period_seconds": 120,
        "icon": "car",
        "is_system": True,
    },
    {
        "template_id": DefaultTemplateId.OUTDOOR_TREKKING.value,
        "name": "Khám phá ngoài trời",
        "description": "Dành cho các hoạt động leo núi, dã ngoại, chạy bộ đường dài.",
        "default_duration_minutes": 120,
        "default_grace_period_seconds": 300,
        "icon": "mountain",
        "is_system": True,
    },
    {
        "template_id": DefaultTemplateId.ALONE_HOME.value,
        "name": "Kiểm tra an toàn",
        "description": "Kiểm tra định kỳ khi ở nhà một mình hoặc làm việc đêm tại văn phòng.",
        "default_duration_minutes": 60,
        "default_grace_period_seconds": 120,
        "icon": "home",
        "is_system": True,
    },
    {
        "template_id": DefaultTemplateId.MEETING_STRANGER.value,
        "name": "Cuộc gặp an toàn",
        "description": "Bảo vệ khi gặp gỡ người mới quen, giao dịch mua bán hoặc phỏng vấn.",
        "default_duration_minutes": 30,
        "default_grace_period_seconds": 60,
        "icon": "user-friends",
        "is_system": True,
    },
]


class SafetyCheckRepository:
    """Repository truy cập Firestore collections `safety_check_templates` và `safety_check_instances`."""
    _templates_seeded: bool = False

    def __init__(self, db: Optional[FirestoreClient] = None) -> None:
        self.db = db or get_firestore_client()
        self.templates_col = self.db.collection("safety_check_templates")
        self.instances_col = self.db.collection("safety_check_instances")
        self._overdue_query = None
        if not SafetyCheckRepository._templates_seeded:
            self._seed_default_templates()
            SafetyCheckRepository._templates_seeded = True

    def _seed_default_templates(self) -> None:
        """Tự động kiểm tra và khởi tạo 5 template mặc định nếu chưa có."""
        try:
            for tpl in DEFAULT_SYSTEM_TEMPLATES:
                doc_ref = self.templates_col.document(tpl["template_id"])
                doc = doc_ref.get()
                if not doc.exists:
                    doc_ref.set(tpl)
                    logger.info(f"Đã seed safety check template: {tpl['template_id']}")
        except Exception as e:
            logger.warning(f"Lỗi khi seed templates: {str(e)}")

    def list_templates(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách template (bao gồm template hệ thống và template do user tự tạo)."""
        results: List[Dict[str, Any]] = []

        # 1. Templates hệ thống
        for doc in self.templates_col.where(filter=FieldFilter("is_system", "==", True)).stream():
            d = doc.to_dict() or {}
            d["template_id"] = doc.id
            results.append(d)

        # 2. Custom templates của user nếu có
        if user_id:
            for doc in self.templates_col.where(filter=FieldFilter("created_by", "==", user_id)).stream():
                d = doc.to_dict() or {}
                d["template_id"] = doc.id
                results.append(d)

        # Tránh trùng lặp ID
        unique_map = {item["template_id"]: item for item in results}
        if user_id:
            for doc in self._template_overrides(user_id).stream():
                if doc.id not in unique_map:
                    continue
                override = doc.to_dict() or {}
                if override.get("deleted"):
                    unique_map.pop(doc.id, None)
                else:
                    unique_map[doc.id] = {**unique_map[doc.id], **override,
                                          "template_id": doc.id}
        return list(unique_map.values())

    def _template_overrides(self, user_id: str):
        return self.db.collection("users").document(user_id).collection("safety_check_template_overrides")

    def get_visible_template(self, user_id: str, template_id: str) -> Optional[Dict[str, Any]]:
        template = self.get_template(template_id)
        if not template or (not template.get("is_system") and template.get("created_by") != user_id):
            return None
        doc = self._template_overrides(user_id).document(template_id).get()
        override = (doc.to_dict() or {}) if doc.exists else {}
        if override.get("deleted"):
            return None
        return {**template, **override, "template_id": template_id}

    def save_template_override(self, user_id: str, template_id: str, data: Dict[str, Any]) -> None:
        self._template_overrides(user_id).document(template_id).set({
            **data, "updated_at": datetime.now(timezone.utc),
        })

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin một template theo ID."""
        doc = self.templates_col.document(template_id).get()
        if doc.exists:
            d = doc.to_dict() or {}
            d["template_id"] = doc.id
            return d
        return None

    def create_custom_template(self, template_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo template tùy chỉnh mới của người dùng."""
        doc_ref = self.templates_col.document(template_id)
        data["template_id"] = template_id
        data["is_system"] = False
        data["created_at"] = datetime.now(timezone.utc)
        doc_ref.set(data)
        logger.info(f"Đã tạo custom template: safety_check_templates/{template_id}")
        return data

    def create_instance(self, instance_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu một phiên Safety Check mới vào Firestore."""
        doc_ref = self.instances_col.document(instance_id)
        now = datetime.now(timezone.utc)
        data["instance_id"] = instance_id
        data["created_at"] = now
        data["updated_at"] = now

        doc_ref.set(data)
        logger.info(f"Đã tạo safety check instance: safety_check_instances/{instance_id}")
        return data

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một phiên instance."""
        doc = self.instances_col.document(instance_id).get()
        if doc.exists:
            d = doc.to_dict() or {}
            d["instance_id"] = doc.id
            return d
        return None

    def get_active_instance_by_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Tìm phiên Safety Check đang chạy của user (status là ACTIVE hoặc CHECK_REQUIRED)."""
        docs = self.instances_col.where(filter=FieldFilter("user_id", "==", user_id)).stream()
        for doc in docs:
            d = doc.to_dict() or {}
            if d.get("status") in [SafetyCheckStatus.ACTIVE.value, SafetyCheckStatus.CHECK_REQUIRED.value]:
                d["instance_id"] = doc.id
                return d
        return None

    def update_instance(self, instance_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cập nhật dữ liệu hoặc trạng thái phiên Safety Check."""
        doc_ref = self.instances_col.document(instance_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None

        update_data["updated_at"] = datetime.now(timezone.utc)
        doc_ref.set(update_data, merge=True)

        updated = doc_ref.get().to_dict() or {}
        updated["instance_id"] = instance_id
        return updated

    def get_overdue_instances(self) -> List[Dict[str, Any]]:
        """
        Quét các phiên đã quá hạn Grace Period mà chưa xác nhận an toàn để Escalate:
        - status in [ACTIVE, CHECK_REQUIRED]
        - grace_period_until <= now()
        """
        now = datetime.now(timezone.utc)
        overdue_list = []

        # Chỉ quét các instance đang ACTIVE hoặc CHECK_REQUIRED (tiết kiệm 99% quota đọc)
        query = self.instances_col.where(
            filter=FieldFilter(
                "status",
                "in",
                [SafetyCheckStatus.ACTIVE.value, SafetyCheckStatus.CHECK_REQUIRED.value],
            )
        )
        if self._overdue_query is None:
            self._overdue_query = WatchedQuery(query)
        for row in self._overdue_query.read():
            d = {key: value for key, value in row.items() if key != '_document_id'}
            st = d.get("status")
            if st in [SafetyCheckStatus.ACTIVE.value, SafetyCheckStatus.CHECK_REQUIRED.value]:
                gp_until = d.get("grace_period_until")
                # Xử lý kiểu dữ liệu datetime hoặc chuỗi ISO
                if gp_until:
                    if isinstance(gp_until, str):
                        try:
                            gp_until_dt = datetime.fromisoformat(gp_until)
                        except Exception:
                            continue
                    else:
                        gp_until_dt = gp_until

                    if gp_until_dt <= now:
                        d["instance_id"] = row['_document_id']
                        overdue_list.append(d)

        return overdue_list

    def close(self):
        if self._overdue_query is not None:
            self._overdue_query.close()
            self._overdue_query = None

    def claim_overdue(self, instance_id, now):
        from app.modules.detection.alerts.store import FirestoreStore
        def operation(tx):
            path = f'safety_check_instances/{instance_id}'
            row = tx.get(path)
            if not row or row.get('status') not in ('ACTIVE', 'CHECK_REQUIRED'):
                return None
            deadline = row.get('grace_period_until')
            if isinstance(deadline, str):
                deadline = datetime.fromisoformat(deadline)
            if not deadline or deadline > now:
                return None
            row.update(status='ESCALATED', escalated_at=now, updated_at=now)
            tx.set(path, row)
            return row
        return FirestoreStore(self.db).atomic(operation)
