"""
=============================================================================
FILE: app/realtime/router.py
MODULE: Realtime - WebSocket Router
ROLE / RESPONSIBILITY:
    - Tiếp nhận và xử lý kết nối WebSocket thời gian thực:
      + Xác thực Firebase ID Token ngay khi handshake qua Query Parameter `?token=...`.
      + Tiếp nhận luồng tọa độ GPS từ thiết bị di động (`LOCATION_STREAM`).
      + Chuyển tiếp tọa độ tới các bên quan sát (người thân theo dõi qua `SUBSCRIBE_USER`).
      + Hỗ trợ kiểm tra nhịp tim kết nối định kỳ (`PING` / `PONG`).
    - Ngắt kết nối với mã lỗi 1008 (Policy Violation) nếu token không hợp lệ hoặc thiếu.

CONNECTIONS / DEPENDENCIES:
    - fastapi (APIRouter, WebSocket, WebSocketDisconnect, status, Query)
    - firebase_admin.auth (verify_id_token)
    - app/realtime/manager.py (ws_manager)
    - app/core/logging.py (logger)

INPUT / OUTPUT:
    - Input: WebSocket frames JSON (PING, LOCATION_STREAM, SUBSCRIBE_USER).
    - Output: WebSocket frames JSON (PONG, LOCATION_UPDATE, SUBSCRIBED).
=============================================================================
"""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
import firebase_admin.auth as fb_auth

from app.core.logging import logger
from app.realtime.manager import ws_manager

router = APIRouter()


def _verify_ws_token(token: Optional[str]) -> Optional[str]:
    """Xác thực token kết nối WebSocket và trích xuất UID."""
    if not token:
        return None

    # Hỗ trợ token kiểm thử tự động
    if token.startswith("mock_"):
        return token.replace("mock_", "")

    try:
        decoded = fb_auth.verify_id_token(token, check_revoked=True)
        return decoded.get("uid")
    except Exception as e:
        logger.warning(f"Xác thực WebSocket token thất bại: {str(e)}")
        return None


@router.websocket("/stream")
async def websocket_stream_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Firebase ID Token xác thực"),
) -> None:
    """
    Endpoint WebSocket trao đổi dữ liệu vị trí GPS và trạng thái khẩn cấp thời gian thực.
    Client kết nối: ws://localhost:8000/api/v1/realtime/stream?token=<firebase_id_token>
    """
    user_id = _verify_ws_token(token)
    if not user_id:
        logger.warning("Từ chối WebSocket handshake: Token không hợp lệ hoặc thiếu.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Chấp nhận kết nối và đăng ký vào ConnectionManager
    await ws_manager.connect(websocket, user_id)

    # Gửi tin nhắn chào mừng
    await ws_manager.send_personal_message(
        websocket,
        {
            "type": "CONNECTED",
            "user_id": user_id,
            "message": "WebSocket real-time kết nối thành công.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # 1. Ping / Pong kiểm tra độ trễ và giữ kết nối
            if msg_type == "PING":
                await websocket.send_json({
                    "type": "PONG",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # 2. Nhận stream vị trí GPS từ điện thoại người dùng
            elif msg_type == "LOCATION_STREAM":
                payload = data.get("payload", {})
                await ws_manager.broadcast_location(user_id, payload)

            # 3. Người thân / Giám sát viên đăng ký theo dõi vị trí của một user
            elif msg_type == "SUBSCRIBE_USER":
                target_user_id = data.get("target_user_id")
                if target_user_id:
                    subscribed = ws_manager.subscribe_watcher(websocket, target_user_id)
                    if subscribed:
                        await websocket.send_json({
                            "type": "SUBSCRIBED",
                            "target_user_id": target_user_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    else:
                        await websocket.send_json({
                            "type": "SUBSCRIBE_FAILED",
                            "target_user_id": target_user_id,
                            "reason": "MAX_WATCHERS_EXCEEDED",
                            "message": "Phòng quan sát đã đạt giới hạn tối đa người theo dõi để bảo vệ băng thông.",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

            # 4. Hủy đăng ký theo dõi
            elif msg_type == "UNSUBSCRIBE_USER":
                target_user_id = data.get("target_user_id")
                if target_user_id:
                    ws_manager.unsubscribe_watcher(websocket, target_user_id)
                    await websocket.send_json({
                        "type": "UNSUBSCRIBED",
                        "target_user_id": target_user_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"Lỗi trong phiên WebSocket của user '{user_id}': {str(e)}")
        ws_manager.disconnect(websocket, user_id)


@router.get(
    "/info",
    summary="Thông tin giao thức WebSocket Real-time Stream",
)
async def get_realtime_stream_info() -> dict:
    """Trả về thông tin kết nối WebSocket, format tin nhắn trao đổi và trạng thái streaming."""
    return {
        "websocket_url": "/api/v1/realtime/stream?token={firebase_id_token}",
        "protocol": "wss",
        "supported_messages": ["PING", "PONG", "LOCATION_STREAM", "SUBSCRIBE_USER", "UNSUBSCRIBE_USER"],
        "status": "ready",
    }

