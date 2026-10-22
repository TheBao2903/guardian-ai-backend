"""
=============================================================================
FILE: app/modules/notifications/router.py
MODULE: Notifications - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint phục vụ kiểm tra và quản lý thông báo cảnh báo:
      + POST /api/v1/notifications/test-telegram: Thử nghiệm gửi tin nhắn Telegram tới Chat ID người dùng / người thân.
    - Đảm bảo tuân thủ xác thực qua Firebase Bearer token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/notifications/service.py (NotificationService)
    - app/modules/notifications/schemas.py (TestNotificationRequest, NotificationResult)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: TestNotificationRequest.
    - Output: ApiResponse[NotificationResult].
=============================================================================
"""

from fastapi import APIRouter, Depends

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.notifications.schemas import NotificationResult, TestNotificationRequest
from app.modules.notifications.service import NotificationService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
notification_service = NotificationService()


@router.post(
    "/test-telegram",
    response_model=ApiResponse[NotificationResult],
    summary="Kiểm tra kết nối và gửi thử thông báo tới Telegram Chat ID",
)
async def test_telegram_notification(
    data: TestNotificationRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[NotificationResult]:
    """Gửi một tin nhắn mẫu kiểm tra tính sẵn sàng của bot cảnh báo tới Chat ID."""
    result = await notification_service.test_telegram_channel(
        telegram_id=data.telegram_id,
        custom_text=data.message,
    )
    return ApiResponse.ok(
        data=result,
        message="Đã thực hiện gửi tin nhắn kiểm tra tới Telegram"
        if result.success
        else f"Gửi tin nhắn Telegram không thành công: {result.error_message}",
    )
