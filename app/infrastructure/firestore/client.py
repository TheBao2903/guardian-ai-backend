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

import glob
import json
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

    # 1. Thử tải từ biến môi trường chuỗi JSON (tiện lợi cho Cloud / Render / Railway)
    cred = None
    if settings.FIREBASE_CREDENTIALS_JSON and settings.FIREBASE_CREDENTIALS_JSON.strip():
        try:
            cert_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cert_dict)
            logger.info("Đã nạp Firebase Service Account từ biến môi trường FIREBASE_CREDENTIALS_JSON.")
        except Exception as e:
            logger.error(f"Lỗi phân tích JSON từ FIREBASE_CREDENTIALS_JSON: {str(e)}")

    # 2. Thử tải từ file đường dẫn (Secret Files hoặc local file)
    if cred is None:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH

        # Nếu đường dẫn chỉ định không tồn tại, tự tìm trong /etc/secrets/ (Render Secret Files)
        if not cred_path or not os.path.exists(cred_path):
            render_secrets = glob.glob("/etc/secrets/*.json")
            if render_secrets:
                cred_path = render_secrets[0]
                logger.info(f"Tự động phát hiện Firebase Secret File trên Render: {cred_path}")

        if not cred_path or not os.path.exists(cred_path):
            error_msg = f"Không tìm thấy file Firebase Service Account tại đường dẫn: {cred_path}"
            logger.error(error_msg)
            raise ProviderException(message=error_msg, provider="Firebase")

        cred = credentials.Certificate(cred_path)

    try:
        # Nếu đã có default app của firebase thì tái sử dụng
        _firebase_app = firebase_admin.get_app()
        logger.info(f"Tái sử dụng Firebase App hiện có: {_firebase_app.name}")
    except ValueError:
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
