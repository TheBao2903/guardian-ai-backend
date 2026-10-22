"""
=============================================================================
FILE: app/modules/auth/service.py
MODULE: Auth - Authentication Service
ROLE / RESPONSIBILITY:
    - Quản lý logic nghiệp vụ đăng ký tài khoản (tạo Firebase user + Firestore doc + Consent record).
    - Quản lý logic đăng nhập, xác thực ID token và ghi nhật ký kiểm toán đăng nhập (Login Audit Log).
    - Cung cấp nội dung bản Cam kết bảo mật dữ liệu (Privacy Policy & 5 Trụ cột cam kết vàng).
    - Xử lý quên mật khẩu và đổi mật khẩu qua Firebase Admin SDK.
    - Đảm bảo tuân thủ ADR-004, tiêu chuẩn Nghị định 13/2023/NĐ-CP.

CONNECTIONS / DEPENDENCIES:
    - Thư viện ngoài: `firebase_admin.auth`.
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - app/core/exceptions.py (ConflictException, EntityNotFoundException, ValidationException, ProviderException)
    - app/modules/auth/schemas.py (RegisterRequest, LoginRequest, AuthResponse, AuthenticatedUser,
      PrivacyPolicyResponse, PrivacyCommitmentItem, LoginLogItem)

INPUT / OUTPUT:
    - Input: DTOs từ Router, IP client, User-Agent.
    - Output: AuthResponse, Password Reset link, PrivacyPolicyResponse, List[LoginLogItem].
=============================================================================
"""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import BackgroundTasks
from firebase_admin import auth as firebase_auth
from firebase_admin.exceptions import FirebaseError

import httpx
import jwt
from app.core.config import get_settings
from app.core.exceptions import ConflictException, EntityNotFoundException, ProviderException, ValidationException
from app.core.logging import logger
from app.core.rate_limiter import check_account_lockout, background_post_login_tasks
from app.infrastructure.firestore.client import get_firestore_client
from app.modules.auth.schemas import (
    AuthenticatedUser,
    AuthResponse,
    LoginLogItem,
    LoginRequest,
    PrivacyCommitmentItem,
    PrivacyPolicyResponse,
    RegisterRequest,
)


class AuthService:
    """Service xử lý logic xác thực và quản lý tài khoản người dùng."""

    def __init__(self) -> None:
        self.db = get_firestore_client()

    def get_privacy_policy(self) -> PrivacyPolicyResponse:
        """Trả về chi tiết 5 cam kết bảo mật & quyền dữ liệu của hệ thống Guardian AI."""
        commitments = [
            PrivacyCommitmentItem(
                key="terms_and_legal",
                title="1. Điều khoản dịch vụ & Pháp lý",
                summary="Tuân thủ nghiêm ngặt Nghị định 13/2023/NĐ-CP của Chính phủ về Bảo vệ dữ liệu cá nhân.",
                full_description=(
                    "Guardian AI cam kết thu thập và xử lý dữ liệu đúng mục đích cứu trợ an toàn cá nhân. "
                    "Người dùng có toàn quyền được biết, đồng ý, chỉnh sửa và yêu cầu xóa vĩnh viễn dữ liệu của mình bất cứ lúc nào."
                ),
                is_mandatory=True,
            ),
            PrivacyCommitmentItem(
                key="privacy_no_commercial",
                title="2. Quyền riêng tư & Tuyệt đối không thương mại hóa",
                summary="Dữ liệu cá nhân, danh bạ và vị trí của bạn không bao giờ bị bán cho bên thứ ba.",
                full_description=(
                    "Chúng tôi cam kết không chia sẻ dữ liệu người dùng cho các bên quảng cáo, tiếp thị "
                    "hoặc bất kỳ tổ chức thương mại nào. Dữ liệu chỉ được sử dụng duy nhất cho mục đích kích hoạt bảo vệ an toàn."
                ),
                is_mandatory=True,
            ),
            PrivacyCommitmentItem(
                key="audio_rolling_buffer",
                title="3. Cam kết xử lý âm thanh: Không nghe lén 24/7",
                summary="Micro chỉ chạy trên bộ đệm cục bộ (rolling buffer) của điện thoại, không stream âm thanh liên tục về máy chủ.",
                full_description=(
                    "Microphone của điện thoại chỉ xử lý phân tích tín hiệu trên bộ nhớ tạm thời của máy. "
                    "Hệ thống KHÔNG nghe lén, KHÔNG lưu trữ âm thanh sinh hoạt hàng ngày. "
                    "Chỉ khi sự kiện nguy cấp được xác nhận (hoặc người dùng bấm SOS), đoạn âm thanh bằng chứng ngắn mới được mã hóa "
                    "và lưu trữ an toàn trên Cloudflare R2 để gửi cho người thân."
                ),
                is_mandatory=True,
            ),
            PrivacyCommitmentItem(
                key="gps_emergency_only",
                title="4. Cam kết vị trí GPS: Chỉ trích xuất khi khẩn cấp",
                summary="Không theo dõi hành trình 24/7, chỉ gửi tọa độ khi kích hoạt SOS hoặc hết hạn Safety Check.",
                full_description=(
                    "Hệ thống không ghi lại lịch sử di chuyển thường nhật của bạn vào cơ sở dữ liệu. "
                    "Vị trí GPS thời gian thực chỉ được kết nối khi có phiên khẩn cấp đang kích hoạt, "
                    "hoặc khi phiên Hẹn giờ kiểm tra an toàn (Safety Check) bị quá hạn mà bạn không phản hồi."
                ),
                is_mandatory=True,
            ),
            PrivacyCommitmentItem(
                key="medical_privacy_tiers",
                title="5. Cam kết phân cấp bảo mật dữ liệu y tế",
                summary="Thông tin bệnh nền, nhóm máu, dị ứng được bảo vệ 3 tầng và người dùng toàn quyền quyết định hiển thị.",
                full_description=(
                    "Hồ sơ y tế được phân cấp bảo vệ nghiêm ngặt: Dữ liệu nhạy cảm chỉ hiển thị khi đã đăng nhập. "
                    "Chỉ các thông tin cần thiết phục vụ sơ cứu (nhóm máu, dị ứng thuốc cấp bách) mới được phép gửi cho người thân "
                    "hoặc hiển thị ngoài màn hình khóa theo sự cho phép của bạn."
                ),
                is_mandatory=True,
            ),
        ]

        return PrivacyPolicyResponse(
            version="1.0",
            effective_date="2026-10-08",
            app_name="Guardian AI",
            legal_basis="Nghị định 13/2023/NĐ-CP về Bảo vệ dữ liệu cá nhân & Chuẩn quyền riêng tư quốc tế",
            commitments=commitments,
        )

    async def register(self, data: RegisterRequest, client_ip: str = "unknown") -> AuthResponse:
        """
        Đăng ký tài khoản người dùng mới (High-Performance Zero-Waste Pipeline):
        - Tạo User trực tiếp trên Firebase Auth (loại bỏ get_user_by_email dư thừa).
        - Chạy song song: Lưu Document Firestore + Sinh Custom Token (tiết kiệm ~50% thời gian).
        """
        # 1. Tạo User trên Firebase Authentication (tự động phát hiện trùng email không cần query trước)
        try:
            user_record = await asyncio.to_thread(
                firebase_auth.create_user,
                email=data.email,
                password=data.password,
                display_name=data.name,
                email_verified=False,
            )
            uid = user_record.uid
            logger.info(f"Đã tạo Firebase User thành công: UID={uid}, Email={data.email}")
        except firebase_auth.EmailAlreadyExistsError:
            raise ConflictException(f"Email '{data.email}' đã được đăng ký trong hệ thống")
        except FirebaseError as e:
            err_str = str(e).lower()
            if "already exists" in err_str or "email_exists" in err_str:
                raise ConflictException(f"Email '{data.email}' đã được đăng ký trong hệ thống")
            logger.error(f"Lỗi tạo tài khoản trên Firebase Auth: {str(e)}")
            raise ProviderException(message=f"Lỗi tạo tài khoản: {str(e)}", provider="Firebase Auth")

        # 2. Chuẩn bị Document người dùng trong Firestore collection `users` kèm hồ sơ Consent
        now_utc = datetime.now(timezone.utc)
        user_doc_data = {
            "firebase_uid": uid,
            "email": data.email,
            "name": data.name,
            "display_name": data.name,
            "phone": data.phone,
            "role": "user",
            "status": "active",
            "created_at": now_utc,
            "updated_at": now_utc,
            "last_login_at": now_utc,
            "telegram_enabled": False,
            "notify_on_sos": True,
            "notify_on_scream": True,
            "notify_on_abnormal_sound": True,
            # Bằng chứng cam kết bảo mật & quyền dữ liệu (Audit Consent Record)
            "consent": {
                "accepted_terms": data.accepted_terms,
                "accepted_privacy_policy": data.accepted_privacy_policy,
                "accepted_audio_processing": data.accepted_audio_processing,
                "accepted_location_tracking": data.accepted_location_tracking,
                "accepted_medical_data_sharing": data.accepted_medical_data_sharing,
                "consented_at": now_utc,
                "consent_version": "1.0",
                "consent_ip": client_ip,
            },
        }

        # 3. Chạy song song: Lưu Firestore + Sinh Custom Token (Parallel Execution)
        def _write_user_doc():
            self.db.collection("users").document(uid).set(user_doc_data)
            logger.info(f"Đã lưu user document và hồ sơ Consent vào Firestore: users/{uid}")

        def _generate_custom_token():
            try:
                raw_token = firebase_auth.create_custom_token(uid)
                return raw_token.decode("utf-8") if isinstance(raw_token, bytes) else str(raw_token)
            except Exception as ex:
                logger.warning(f"Không thể tạo custom token cho UID {uid}: {str(ex)}")
                return None

        _, custom_token_str = await asyncio.gather(
            asyncio.to_thread(_write_user_doc),
            asyncio.to_thread(_generate_custom_token),
        )
        settings = get_settings()
        now_ts = int(now_utc.timestamp())
        jwt_payload = {
            "uid": uid,
            "email": data.email,
            "name": data.name,
            "role": "user",
            "iat": now_ts,
            "exp": now_ts + (30 * 24 * 3600),  # 30 ngày
        }
        access_token_str = jwt.encode(jwt_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        user_model = AuthenticatedUser(
            uid=uid,
            email=data.email,
            name=data.name,
            phone=data.phone,
            role="user",
            status="active",
            created_at=now_utc,
            last_login_at=now_utc,
        )

        return AuthResponse(
            user=user_model,
            access_token=access_token_str,
            custom_token=custom_token_str,
            token_type="Bearer",
            message="Đăng ký tài khoản và xác nhận cam kết bảo mật thành công",
        )

    async def verify_password_with_firebase(self, email: str, password: str) -> dict:
        """
        Xác thực email và mật khẩu trực tiếp qua Google Identity Toolkit REST API.
        Trả về dictionary gồm uid, email, idToken nếu hợp lệ; ném ValidationException nếu sai mật khẩu.
        """
        settings = get_settings()
        api_key = getattr(settings, "FIREBASE_WEB_API_KEY", "") or "AIzaSyCnsRihZcg25Ey1YmxSg9kVw-xn-SJvTsw"
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"

        # Cho phép bỏ qua gọi mạng khi chạy unit test giả lập offline
        if settings.APP_ENV == "test" and api_key == "mock":
            return {"uid": f"mock_{email}", "email": email, "idToken": "mock_id_token"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"email": email, "password": password, "returnSecureToken": True},
                )
                if resp.status_code == 200:
                    res_data = resp.json()
                    return {
                        "uid": res_data.get("localId"),
                        "email": res_data.get("email"),
                        "idToken": res_data.get("idToken"),
                    }
                else:
                    err_body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
                    err_msg = err_body.get("error", {}).get("message", "")
                    logger.warning(f"Xác thực mật khẩu Firebase thất bại cho email {email}: {err_msg}")
                    if "EMAIL_NOT_FOUND" in err_msg:
                        raise EntityNotFoundException(f"Không tìm thấy tài khoản với email '{email}'")
                    raise ValidationException("Email hoặc mật khẩu không chính xác")
        except (ValidationException, EntityNotFoundException):
            raise
        except Exception as exc:
            logger.error(f"Lỗi kết nối tới Identity Toolkit: {str(exc)}")
            raise ProviderException(message="Lỗi kết nối máy chủ xác thực", provider="Firebase Auth")

    async def login(
        self,
        data: LoginRequest,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> AuthResponse:
        """
        Xác thực đăng nhập siêu tốc (High-Performance Zero-Waste Pipeline):
        - Đọc Firestore Document đúng 1 lần duy nhất (Single-read).
        - Kiểm tra tài khoản có bị khóa hay không trực tiếp từ Document.
        - Toàn bộ tác vụ ghi Log và cập nhật Database được đẩy ra Background Task chạy ngầm.
        - Phản hồi trả về client tức thì trong ~300ms!
        """
        uid: Optional[str] = None
        email: Optional[str] = None
        login_method = "FIREBASE_ID_TOKEN" if data.id_token else "EMAIL_PASSWORD"

        if data.id_token:
            try:
                decoded = firebase_auth.verify_id_token(data.id_token)
                uid = decoded.get("uid")
                email = decoded.get("email")
            except Exception as e:
                logger.warning(f"ID Token không hợp lệ: {str(e)}")
                raise ValidationException(f"ID Token không hợp lệ hoặc đã hết hạn: {str(e)}")
        elif data.email:
            if data.password:
                # 1. Xác thực mật khẩu qua Firebase Identity Toolkit REST API
                verify_res = await self.verify_password_with_firebase(data.email, data.password)
                uid = verify_res["uid"]
                email = verify_res["email"]
            else:
                try:
                    user_record = firebase_auth.get_user_by_email(data.email)
                    uid = user_record.uid
                    email = user_record.email
                except firebase_auth.UserNotFoundError:
                    raise EntityNotFoundException(f"Không tìm thấy tài khoản với email '{data.email}'")
        else:
            raise ValidationException("Vui lòng cung cấp 'id_token' hoặc 'email' để xác thực")

        # 1. Đọc Firestore Document DUY NHẤT 1 LẦN (Single-read theo Document ID)
        now_utc = datetime.now(timezone.utc)
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict() or {}
            # 2. Kiểm tra khóa tài khoản đa thiết bị ngay từ Document vừa đọc (Zero redundant query)
            check_account_lockout(user_data, email or data.email or "")
        else:
            user_data = {
                "firebase_uid": uid,
                "email": email,
                "name": email.split("@")[0] if email else "Người dùng",
                "role": "user",
                "status": "active",
                "created_at": now_utc,
                "last_login_at": now_utc,
                "updated_at": now_utc,
                "telegram_enabled": False,
            }
            user_ref.set(user_data)

        # 3. Chuẩn bị thông tin Audit Log
        log_id = str(uuid.uuid4())

        # 4. Đẩy tác vụ ghi log và reset lockout ra Background Task chạy ngầm (Non-blocking)
        if background_tasks:
            background_tasks.add_task(
                background_post_login_tasks,
                uid,
                ip_address,
                user_agent,
                login_method,
                log_id,
                now_utc,
            )
        else:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.run_in_executor(
                    None,
                    background_post_login_tasks,
                    uid,
                    ip_address,
                    user_agent,
                    login_method,
                    log_id,
                    now_utc,
                )
            except Exception as e:
                logger.warning(f"Không thể khởi chạy background post login: {str(e)}")

        # 5. Sinh Custom Token (nhanh trên CPU, không gọi mạng)
        custom_token_str = None
        try:
            custom_token_bytes = firebase_auth.create_custom_token(uid)
            custom_token_str = custom_token_bytes.decode("utf-8") if isinstance(custom_token_bytes, bytes) else str(custom_token_bytes)
        except Exception as e:
            logger.warning(f"Không thể tạo custom token: {str(e)}")

        user_model = AuthenticatedUser(
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
            last_login_at=now_utc,
        )

        settings = get_settings()
        now_ts = int(now_utc.timestamp())
        jwt_payload = {
            "uid": uid,
            "email": email or user_data.get("email"),
            "name": user_data.get("name") or user_data.get("display_name"),
            "role": user_data.get("role", "user"),
            "iat": now_ts,
            "exp": now_ts + (30 * 24 * 3600),  # 30 ngày
        }
        access_token_str = jwt.encode(jwt_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        # Trả về kết quả cho client NGAY LẬP TỨC (không đợi ghi log)
        return AuthResponse(
            user=user_model,
            access_token=access_token_str,
            custom_token=custom_token_str,
            token_type="Bearer",
            message="Đăng nhập thành công",
        )

    async def forgot_password(self, email: str) -> str:
        """Sinh đường dẫn đặt lại mật khẩu và gửi email khôi phục an toàn qua Firebase."""
        try:
            firebase_auth.get_user_by_email(email)
            reset_link = firebase_auth.generate_password_reset_link(email)
            logger.info(f"Đã tạo Password Reset Link cho email: {email}")

            # Gửi email khôi phục mật khẩu trực tiếp tới hộp thư của user qua Identity Toolkit
            settings = get_settings()
            api_key = getattr(settings, "FIREBASE_WEB_API_KEY", "") or "AIzaSyCnsRihZcg25Ey1YmxSg9kVw-xn-SJvTsw"
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    await client.post(
                        url,
                        json={"requestType": "PASSWORD_RESET", "email": email},
                    )
                logger.info(f"Firebase đã điều phối email đặt lại mật khẩu tới hộp thư: {email}")
            except Exception as mail_err:
                logger.warning(f"Không thể gửi email tự động qua Identity Toolkit: {str(mail_err)}")

            return reset_link
        except firebase_auth.UserNotFoundError:
            raise EntityNotFoundException(f"Không tìm thấy tài khoản tương ứng với email: '{email}'")
        except FirebaseError as e:
            logger.error(f"Lỗi tạo password reset link: {str(e)}")
            raise ProviderException(message=f"Lỗi Firebase: {str(e)}", provider="Firebase Auth")

    async def change_password(
        self,
        uid: str,
        new_password: str,
        current_password: Optional[str] = None,
        email: Optional[str] = None,
    ) -> None:
        """Cập nhật mật khẩu mới cho người dùng đã xác thực kèm xác thực mật khẩu cũ."""
        # 1. Kiểm tra định dạng mật khẩu mới
        if len(new_password) < 6:
            raise ValidationException("Mật khẩu mới phải có ít nhất 6 ký tự")
        has_letter = bool(re.search(r'[a-zA-Z]', new_password))
        has_number = bool(re.search(r'[0-9]', new_password))
        if not (has_letter and has_number):
            raise ValidationException("Mật khẩu mới phải chứa cả chữ cái và chữ số")

        # 2. Xác thực mật khẩu hiện tại nếu được cung cấp
        if current_password:
            if current_password == new_password:
                raise ValidationException("Mật khẩu mới phải khác mật khẩu hiện tại")
            user_email = email
            if not user_email:
                try:
                    user_rec = firebase_auth.get_user(uid)
                    user_email = user_rec.email
                except Exception as ex:
                    logger.warning(f"Không lấy được email của user UID {uid}: {ex}")
            if user_email:
                try:
                    await self.verify_password_with_firebase(user_email, current_password)
                except ValidationException:
                    raise ValidationException("Mật khẩu hiện tại không chính xác")

        # 3. Cập nhật mật khẩu trên Firebase Auth
        try:
            firebase_auth.update_user(uid, password=new_password)
            logger.info(f"Đã cập nhật mật khẩu thành công cho UID: {uid}")
        except FirebaseError as e:
            logger.error(f"Lỗi đổi mật khẩu Firebase UID {uid}: {str(e)}")
            raise ProviderException(message=f"Lỗi cập nhật mật khẩu: {str(e)}", provider="Firebase Auth")
