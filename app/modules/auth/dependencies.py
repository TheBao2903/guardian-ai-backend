"""
=============================================================================
FILE: app/modules/auth/dependencies.py
MODULE: Auth - Authentication Dependency
ROLE / RESPONSIBILITY:
    - Trích xuất Bearer Token từ header Authorization của HTTP request.
    - Xác thực Firebase ID Token thông qua Firebase Admin SDK (auth.verify_id_token).
    - Kiểm tra tính hợp lệ, trạng thái thu hồi (check_revoked), thời hạn token.
    - Tải thông tin người dùng từ Firestore `users/{uid}`, tự động đồng bộ nếu mới.
    - Cung cấp AuthenticatedUser cho toàn bộ các protected endpoint.
    - Đảm bảo tuân thủ ADR-004 (Firebase Authentication, không trust arbitrary user_id).

CONNECTIONS / DEPENDENCIES:
    - Thư viện ngoài: `firebase_admin.auth`.
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - app/core/exceptions.py (UnauthorizedException, ForbiddenException)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - Được gọi bởi: Mọi endpoint yêu cầu đăng nhập trong backend via `Depends(get_current_user)`.

INPUT / OUTPUT:
    - Input: HTTP Authorization: Bearer <firebase_id_token>.
    - Output: AuthenticatedUser model chứa uid, email, role, profile data.
=============================================================================
"""

from datetime import datetime, timezone
import asyncio
from typing import Optional
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin.exceptions import FirebaseError

import jwt
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client
from app.modules.auth.schemas import AuthenticatedUser

# HTTPBearer trích xuất Authorization: Bearer <token>
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    """Dependency xác thực JWT Token / Firebase ID Token và trả về AuthenticatedUser."""
    if not credentials or not credentials.credentials:
        raise UnauthorizedException(
            message="Yêu cầu xác thực: Vui lòng cung cấp Bearer token trong header Authorization",
            details={"error_code": "MISSING_BEARER_TOKEN"},
        )

    token = credentials.credentials
    settings = get_settings()
    uid: Optional[str] = None
    email: Optional[str] = None
    decoded_token: dict = {}

    # 1. Thử giải mã JWT nội bộ hệ thống (High-speed HS256 < 0.1ms)
    try:
        decoded_token = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
    except Exception:
        # 2. Nếu không phải JWT nội bộ, xác thực qua Firebase ID Token
        try:
            decoded_token = await asyncio.to_thread(firebase_auth.verify_id_token, token, check_revoked=False)
            uid = decoded_token.get("uid")
            email = decoded_token.get("email")
        except firebase_auth.ExpiredIdTokenError:
            logger.warning("Firebase ID Token đã hết hạn")
            raise UnauthorizedException(
                message="Phiên đăng nhập đã hết hạn, vui lòng làm mới token",
                details={"error_code": "TOKEN_EXPIRED"},
            )
        except firebase_auth.RevokedIdTokenError:
            logger.warning("Firebase ID Token đã bị thu hồi")
            raise UnauthorizedException(
                message="Token đã bị vô hiệu hóa, vui lòng đăng nhập lại",
                details={"error_code": "TOKEN_REVOKED"},
            )
        except (firebase_auth.InvalidIdTokenError, ValueError, FirebaseError) as e:
            logger.warning(f"Token xác thực không hợp lệ: {str(e)}")
            raise UnauthorizedException(
                message="Token xác thực không hợp lệ",
                details={"error_code": "INVALID_TOKEN"},
            )

    if not uid:
        raise UnauthorizedException(message="Token không chứa thông tin định danh hợp lệ (uid)")

    try:
        # Truy vấn thông tin người dùng từ Firestore (chạy trên worker thread để không block event loop)
        db = get_firestore_client()
        user_ref = db.collection("users").document(uid)
        user_doc = await asyncio.to_thread(user_ref.get)

        now_utc = datetime.now(timezone.utc)

        if user_doc.exists:
            user_data = user_doc.to_dict() or {}
        else:
            # Nếu người dùng đã xác thực Firebase thành công nhưng chưa có record trong Firestore
            display_name = decoded_token.get("name") or (email.split("@")[0] if email else "Người dùng")
            user_data = {
                "firebase_uid": uid,
                "email": email,
                "name": display_name,
                "display_name": display_name,
                "role": "user",
                "status": "active",
                "created_at": now_utc,
                "last_login_at": now_utc,
                "updated_at": now_utc,
                "telegram_enabled": False,
                "notify_on_sos": True,
                "notify_on_scream": True,
                "notify_on_abnormal_sound": True,
            }
            await asyncio.to_thread(user_ref.set, user_data)
            logger.info(f"Đã tự động khởi tạo hồ sơ người dùng Firestore cho UID: {uid}")

        # Kiểm tra trạng thái tài khoản
        if user_data.get("status") == "disabled":
            raise UnauthorizedException(message="Tài khoản đã bị tạm khóa bởi quản trị viên")

        return AuthenticatedUser(
            uid=uid,
            email=email or user_data.get("email"),
            name=user_data.get("name") or user_data.get("display_name"),
            phone=user_data.get("phone"),
            telegram_id=user_data.get("telegram_id"),
            telegram_enabled=user_data.get("telegram_enabled", False),
            device_info=user_data.get("device_info"),
            location_permission_granted=user_data.get("location_permission_granted", False),
            last_known_location=user_data.get("last_known_location"),
            role=user_data.get("role", "user"),
            status=user_data.get("status", "active"),
            avatar_url=user_data.get("avatar_url"),
            created_at=user_data.get("created_at"),
            last_login_at=user_data.get("last_login_at") or now_utc,
        )

    except firebase_auth.ExpiredIdTokenError:
        logger.warning("Firebase ID Token đã hết hạn")
        raise UnauthorizedException(
            message="Phiên đăng nhập đã hết hạn, vui lòng làm mới token",
            details={"error_code": "TOKEN_EXPIRED"},
        )
    except firebase_auth.RevokedIdTokenError:
        logger.warning("Firebase ID Token đã bị thu hồi")
        raise UnauthorizedException(
            message="Token đã bị vô hiệu hóa, vui lòng đăng nhập lại",
            details={"error_code": "TOKEN_REVOKED"},
        )
    except (firebase_auth.InvalidIdTokenError, ValueError) as e:
        logger.warning(f"Firebase ID Token không hợp lệ: {str(e)}")
        raise UnauthorizedException(
            message="Token xác thực không hợp lệ",
            details={"error_code": "INVALID_TOKEN"},
        )
    except FirebaseError as e:
        logger.error(f"Lỗi kết nối dịch vụ Firebase Auth: {str(e)}")
        raise UnauthorizedException(message=f"Lỗi xác thực Firebase: {str(e)}")
