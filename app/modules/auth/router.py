"""
=============================================================================
FILE: app/modules/auth/router.py
MODULE: Auth - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoints cho phân hệ xác thực:
      + GET  /api/v1/auth/privacy-policy: Lấy bản Cam kết bảo mật & 5 Trụ cột vàng (phục vụ Modal).
      + POST /api/v1/auth/register: Đăng ký tài khoản mới kèm ràng buộc bắt buộc đồng ý 5 cam kết.
      + POST /api/v1/auth/login: Đăng nhập và ghi log kiểm toán IP/User-Agent.
      + POST /api/v1/auth/forgot-password: Quên mật khẩu, sinh link reset.
      + POST /api/v1/auth/change-password: Đổi mật khẩu (Protected).
      + GET  /api/v1/auth/me: Lấy thông tin user hiện tại (Protected).
    - Đảm bảo tuân thủ ADR-004, Nghị định 13/2023/NĐ-CP.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/service.py (AuthService)
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (RegisterRequest, LoginRequest, ForgotPasswordRequest,
      ChangePasswordRequest, PrivacyPolicyResponse, AuthResponse, AuthenticatedUser)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: JSON requests, HTTP Request headers (IP, User-Agent).
    - Output: ApiResponse[AuthResponse | AuthenticatedUser | PrivacyPolicyResponse | Dict].
=============================================================================
"""

from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status

from app.core.rate_limiter import (
    check_ip_rate_limit,
    record_failed_login_attempt,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    AuthenticatedUser,
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    PrivacyPolicyResponse,
    RegisterRequest,
)
from app.modules.auth.service import AuthService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
auth_service = AuthService()


@router.get(
    "/privacy-policy",
    response_model=ApiResponse[PrivacyPolicyResponse],
    summary="Lấy chi tiết bản Cam kết bảo mật thông tin & Quyền riêng tư (Phục vụ Modal Đăng ký)",
)
async def get_privacy_policy() -> ApiResponse[PrivacyPolicyResponse]:
    """Trả về 5 trụ cột cam kết vàng của hệ thống Guardian AI theo Nghị định 13/2023/NĐ-CP."""
    policy = auth_service.get_privacy_policy()
    return ApiResponse.ok(data=policy, message="Lấy cam kết bảo mật thành công")


@router.post(
    "/register",
    response_model=ApiResponse[AuthResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản người dùng mới (Yêu cầu đồng ý toàn bộ cam kết bảo mật)",
)
async def register(
    data: RegisterRequest,
    request: Request,
) -> ApiResponse[AuthResponse]:
    """Tạo người dùng mới trên Firebase Authentication và lưu vết hồ sơ cam kết bảo mật (Consent Audit)."""
    # Kiểm tra Rate Limit trên RAM cho IP (< 0.1ms) chống Spam tạo tài khoản rác
    check_ip_rate_limit(request)

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    result = await auth_service.register(data, client_ip=client_ip)
    return ApiResponse.ok(data=result, message="Đăng ký tài khoản thành công")


@router.post(
    "/login",
    response_model=ApiResponse[AuthResponse],
    summary="Đăng nhập hoặc xác thực Firebase ID Token (Tự động ghi Login Audit Log)",
)
async def login(
    data: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ApiResponse[AuthResponse]:
    """Xác thực Firebase ID Token hoặc tài khoản, tự động ghi nhận vết IP và thiết bị đăng nhập."""
    # Kiểm tra Rate Limit trên RAM cho IP (< 0.1ms) chống flooding/DDoS
    check_ip_rate_limit(request)

    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        result = await auth_service.login(
            data,
            ip_address=client_ip,
            user_agent=user_agent,
            background_tasks=background_tasks,
        )
        return ApiResponse.ok(data=result, message="Xác thực thành công")
    except Exception as exc:
        # Nếu đăng nhập thất bại -> Ghi nhận vào Firestore DB để khóa tài khoản đa thiết bị
        if data.email:
            record_failed_login_attempt(data.email)
        raise exc


@router.post(
    "/forgot-password",
    response_model=ApiResponse[Dict[str, str]],
    summary="Yêu cầu đặt lại mật khẩu",
)
async def forgot_password(data: ForgotPasswordRequest) -> ApiResponse[Dict[str, str]]:
    """Gửi yêu cầu đặt lại mật khẩu và trả về liên kết khôi phục an toàn."""
    reset_link = await auth_service.forgot_password(data.email)
    return ApiResponse.ok(
        data={"reset_link": reset_link, "email": data.email},
        message="Đã tạo liên kết đặt lại mật khẩu thành công",
    )


@router.post(
    "/change-password",
    response_model=ApiResponse[Dict[str, str]],
    summary="Đổi mật khẩu người dùng hiện tại",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Dict[str, str]]:
    """Cập nhật mật khẩu mới cho người dùng đang đăng nhập."""
    await auth_service.change_password(
        uid=current_user.uid,
        new_password=data.new_password,
        current_password=data.current_password,
        email=current_user.email,
    )
    return ApiResponse.ok(
        data={"uid": current_user.uid},
        message="Đổi mật khẩu thành công",
    )


@router.get(
    "/me",
    response_model=ApiResponse[AuthenticatedUser],
    summary="Lấy thông tin tài khoản đang đăng nhập",
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[AuthenticatedUser]:
    """Trả về thông tin hồ sơ của người dùng hiện tại dựa trên token Bearer."""
    return ApiResponse.ok(data=current_user, message="Lấy thông tin tài khoản thành công")
