"""
=============================================================================
FILE: app/modules/detection/decision/cooldown_manager.py
MODULE: Detection - Alert Cooldown Manager
ROLE / RESPONSIBILITY:
    - Quản lý thời gian giãn cách (Cooldown) giữa các lần kích hoạt cảnh báo nguy cấp.
    - Ngăn chặn bão thông báo (Alert Storm Protection theo ADR-010):
      + Không gửi liên tiếp 20 tin nhắn SOS khi người dùng la hét trong 20 giây liên tục.
      + Đặt khoảng thời gian ngưng lặp (ví dụ 30-60 giây) cho cùng loại biến cố của cùng một user.
    - Cung cấp hàm kiểm tra `is_in_cooldown` và lấy số giây còn lại `get_remaining_seconds`.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/shared/enums/detection.py (AudioEventType)

INPUT / OUTPUT:
    - Input: user_id, event_type.
    - Output: boolean is_in_cooldown, int remaining_seconds.
=============================================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from app.core.config import get_settings
from app.shared.enums.detection import AudioEventType


class CooldownManager:
    """Bộ quản lý thời gian giãn cách kích hoạt cảnh báo khẩn cấp."""

    def __init__(self, cooldown_seconds: Optional[int] = None) -> None:
        self.settings = get_settings()
        self.cooldown_seconds: int = (
            cooldown_seconds if cooldown_seconds is not None else self.settings.DETECTION_COOLDOWN_SECONDS
        )
        # Lưu thời điểm kích hoạt gần nhất: (user_id, event_type) -> datetime
        self._last_triggered: Dict[Tuple[str, str], datetime] = {}

    def _key(self, user_id: str, event_type: str) -> Tuple[str, str]:
        return (user_id, event_type)

    def is_in_cooldown(self, user_id: str, event_type: str) -> bool:
        """Kiểm tra xem biến cố của user hiện có đang nằm trong thời gian cooldown hay không."""
        key = self._key(user_id, event_type)
        last_time = self._last_triggered.get(key)
        if not last_time:
            return False

        now = datetime.now(timezone.utc)
        elapsed = (now - last_time).total_seconds()
        return elapsed < self.cooldown_seconds

    def get_remaining_seconds(self, user_id: str, event_type: str) -> int:
        """Lấy số giây cooldown còn lại trước khi có thể kích hoạt lại cảnh báo."""
        key = self._key(user_id, event_type)
        last_time = self._last_triggered.get(key)
        if not last_time:
            return 0

        now = datetime.now(timezone.utc)
        elapsed = (now - last_time).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0, int(remaining))

    def mark_triggered(self, user_id: str, event_type: str) -> None:
        """Ghi nhận mốc thời gian kích hoạt cảnh báo khẩn cấp."""
        key = self._key(user_id, event_type)
        self._last_triggered[key] = datetime.now(timezone.utc)

    def reset(self, user_id: str, event_type: Optional[str] = None) -> None:
        """Reset trạng thái cooldown của user (khi phiên kết thúc hoặc hủy)."""
        if event_type:
            self._last_triggered.pop(self._key(user_id, event_type), None)
        else:
            keys_to_remove = [k for k in self._last_triggered if k[0] == user_id]
            for k in keys_to_remove:
                self._last_triggered.pop(k, None)
