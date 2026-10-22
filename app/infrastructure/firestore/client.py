"""
=============================================================================
FILE: app/infrastructure/firestore/client.py
MODULE: Infrastructure - Firestore Client
ROLE / RESPONSIBILITY:
    - Khởi tạo Firebase Admin SDK sử dụng file credentials Service Account.
    - Cung cấp Firestore Database Client cho toàn bộ Repositories trong backend.
    - Cung cấp hàm kiểm tra kết nối phục vụ Health Check API.
    - Đảm bảo tuân thủ ADR-004 (Firebase Auth) và ADR-005 (Firestore Primary DB).

CONNECTIONS / DEPENDENCIES:
    - Đọc cấu hình từ: `app/core/config.py` (get_settings).
    - Thư viện ngoài: `firebase_admin`, `google.cloud.firestore`.
    - Được gọi bởi: Repositories (Users, Emergency, Contacts, SafetyCheck, Location).

INPUT / OUTPUT:
    - Input: Path tới file Service Account JSON từ Settings.
    - Output: google.cloud.firestore.Client instance kết nối Firestore.
=============================================================================
"""

import os
from typing import Optional
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client as FirestoreClient

from app.core.config import get_settings
from app.core.exceptions import ProviderException
from app.core.logging import logger

_firebase_app: Optional[firebase_admin.App] = None
_firestore_client: Optional[FirestoreClient] = None


def init_firebase() -> firebase_admin.App:
    """Khởi tạo Firebase Admin SDK an toàn (chống duplicate initialization)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    settings = get_settings()
    cred_path = settings.FIREBASE_CREDENTIALS_PATH

    if not cred_path or not os.path.exists(cred_path):
        error_msg = f"Không tìm thấy file Firebase Service Account tại đường dẫn: {cred_path}"
        logger.error(error_msg)
        raise ProviderException(message=error_msg, provider="Firebase")

    try:
        # Nếu đã có default app của firebase thì tái sử dụng
        _firebase_app = firebase_admin.get_app()
        logger.info(f"Tái sử dụng Firebase App hiện có: {_firebase_app.name}")
    except ValueError:
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info(f"Khởi tạo Firebase Admin SDK thành công! Project ID: {_firebase_app.project_id}")

    return _firebase_app


def get_firestore_client() -> FirestoreClient:
    """Trả về Firestore Client singleton."""
    global _firestore_client
    if _firestore_client is None:
        init_firebase()
        _firestore_client = firestore.client()
        logger.info("Khởi tạo Firestore Database Client thành công.")
    return _firestore_client


def check_firestore_connection() -> bool:
    """Kiểm tra tính sẵn sàng của kết nối Firestore (dùng cho Health Check)."""
    try:
        db = get_firestore_client()
        # Thử lấy danh sách collections để xác nhận kết nối
        collections = list(db.collections())
        logger.debug(f"Firestore health check OK, số collections: {len(collections)}")
        return True
    except Exception as e:
        logger.error(f"Firestore health check thất bại: {str(e)}")
        return False
