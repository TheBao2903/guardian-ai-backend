"""
=============================================================================
FILE: app/realtime/manager.py
MODULE: Realtime - WebSocket Connection Manager
ROLE / RESPONSIBILITY:
    - Quản lý tập trung các kết nối WebSocket đang hoạt động của từng người dùng:
      + Đăng ký và hủy kết nối an toàn (connect / disconnect).
      + Hỗ trợ một người dùng kết nối nhiều thiết bị đồng thời (multi-device per user).
      + Quản lý phòng quan sát (Watchers): Cho phép người thân theo dõi stream vị trí khi có SOS.
      + Phát tán tọa độ GPS (broadcast_location) và trạng thái khẩn cấp (broadcast_emergency_state).
      + Cache vị trí mới nhất trong bộ nhớ RAM để trả về tức thì.
    - Tuân thủ ADR-007 (FastAPI WebSocket + asyncio).

CONNECTIONS / DEPENDENCIES:
    - fastapi.WebSocket
    - app/core/logging.py (logger)
    - Được gọi bởi: `app/realtime/router.py`, Emergency Service.

INPUT / OUTPUT:
    - Input: WebSocket instance, user_id, message payloads.
    - Output: Real-time JSON broadcasts.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set
from fastapi import WebSocket

from app.core.config import get_settings
from app.core.logging import logger


class ConnectionManager:
    """Quản lý các kết nối WebSocket thời gian thực."""

    def __init__(self) -> None:
        # user_id -> Set các kết nối WebSocket của chính user đó
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # target_user_id -> Set các kết nối của người thân/quan sát viên đang theo dõi target_user
        self.user_watchers: Dict[str, Set[WebSocket]] = {}
        # user_id -> Tọa độ vị trí mới nhất được cache trong RAM
        self.cached_locations: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Chấp nhận và đăng ký một kết nối WebSocket mới."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"WebSocket client đã kết nối: user_id='{user_id}' (Tổng sockets: {len(self.active_connections[user_id])})")

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Hủy đăng ký kết nối WebSocket khi ngắt kết nối."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        # Xóa socket khỏi tất cả các danh sách watchers
        for target_id, watchers in list(self.user_watchers.items()):
            watchers.discard(websocket)
            if not watchers:
                del self.user_watchers[target_id]

        logger.info(f"WebSocket client đã ngắt kết nối: user_id='{user_id}'")

    def subscribe_watcher(self, watcher_socket: WebSocket, target_user_id: str) -> bool:
        """Đăng ký một người quan sát theo dõi luồng GPS của target_user_id (Giới hạn tối đa 10 watchers theo ADR-036)."""
        if target_user_id not in self.user_watchers:
            self.user_watchers[target_user_id] = set()

        settings = get_settings()
        if len(self.user_watchers[target_user_id]) >= settings.MAX_WATCHERS_PER_USER and watcher_socket not in self.user_watchers[target_user_id]:
            logger.warning(
                f"Phòng quan sát của user '{target_user_id}' đã đạt giới hạn tối đa {settings.MAX_WATCHERS_PER_USER} người theo dõi."
            )
            return False

        self.user_watchers[target_user_id].add(watcher_socket)
        logger.info(f"Đã đăng ký quan sát viên theo dõi user_id='{target_user_id}'")
        return True

    def unsubscribe_watcher(self, watcher_socket: WebSocket, target_user_id: str) -> None:
        """Hủy theo dõi luồng GPS của target_user_id."""
        if target_user_id in self.user_watchers:
            self.user_watchers[target_user_id].discard(watcher_socket)

    async def send_personal_message(self, websocket: WebSocket, message: dict) -> None:
        """Gửi trực tiếp một tin nhắn JSON tới một socket cụ thể."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Lỗi gửi tin nhắn trực tiếp qua WebSocket: {str(e)}")

    async def broadcast_to_user(self, user_id: str, message: dict) -> None:
        """Gửi tin nhắn tới toàn bộ các kết nối của một user_id."""
        sockets = list(self.active_connections.get(user_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Lỗi gửi tin nhắn tới user '{user_id}': {str(e)}")
                self.disconnect(ws, user_id)

    async def broadcast_location(self, user_id: str, location_payload: dict) -> None:
        """Phát tán vị trí GPS mới nhất tới người dùng và toàn bộ người thân đang theo dõi."""
        self.cached_locations[user_id] = location_payload

        event_message = {
            "type": "LOCATION_UPDATE",
            "user_id": user_id,
            "payload": location_payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 1. Gửi tới các thiết bị của chính user
        user_sockets = list(self.active_connections.get(user_id, set()))
        for ws in user_sockets:
            try:
                await ws.send_json(event_message)
            except Exception:
                self.disconnect(ws, user_id)

        # 2. Gửi tới các watchers (người thân / cứu hộ đang theo dõi)
        watcher_sockets = list(self.user_watchers.get(user_id, set()))
        for ws in watcher_sockets:
            try:
                await ws.send_json(event_message)
            except Exception:
                self.unsubscribe_watcher(ws, user_id)

    async def broadcast_emergency_state(self, user_id: str, state_payload: dict) -> None:
        """Phát tán sự kiện thay đổi trạng thái khẩn cấp (ACTIVE, RESOLVED...)."""
        event_message = {
            "type": "EMERGENCY_STATE_UPDATE",
            "user_id": user_id,
            "payload": state_payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Gửi tới cả user và watchers
        targets = set(self.active_connections.get(user_id, set())).union(
            self.user_watchers.get(user_id, set())
        )
        for ws in list(targets):
            try:
                await ws.send_json(event_message)
            except Exception:
                pass

    def get_cached_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy vị trí mới nhất được lưu trong bộ nhớ tạm."""
        return self.cached_locations.get(user_id)


# Singleton instance toàn hệ thống
ws_manager = ConnectionManager()
