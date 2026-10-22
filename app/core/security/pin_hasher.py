"""
=============================================================================
FILE: app/core/security/pin_hasher.py
MODULE: Security - PIN Hashing Utility
ROLE / RESPONSIBILITY:
    - Hash & verify mã PIN 4 số bằng bcrypt.
    - Lý do dùng bcrypt thay vì SHA256: PIN chỉ 4 chữ số (10^4 = 10000 combinations)
      nên cần slow hashing để chống brute force. Bcrypt rounds=10 mất ~100ms/lần.
    - Cung cấp class `PinHasher` với 2 static methods: hash_pin(), verify_pin().

CONNECTIONS / DEPENDENCIES:
    - bcrypt library (pip install bcrypt==4.1.2)
    - Được gọi bởi:
      + app/modules/users/service.py: hash khi user đổi PIN.
      + app/modules/emergency/service.py: verify khi user hủy SOS.

INPUT / OUTPUT:
    - hash_pin(pin: str) -> str (bcrypt hash 60 chars).
    - verify_pin(pin: str, hashed: str) -> bool (True nếu match).
=============================================================================
"""

import logging
import re

import bcrypt

logger = logging.getLogger(__name__)


# Pattern chuẩn: đúng 4 chữ số
_PIN_PATTERN = re.compile(r"^\d{4}$")


class PinHasher:
    """Helper class để hash và verify mã PIN 4 số bằng bcrypt."""

    # Số rounds cho bcrypt. Tăng giảm tùy theo yêu cầu performance/security.
    # 10 rounds ≈ 100ms/hash trên CPU phổ thông. Đủ chậm để chống brute force
    # 10^4 combinations (4 số) ~ 17 phút với 1 thread.
    BCRYPT_ROUNDS = 10

    @staticmethod
    def verify_user_pin(pin: str, user: dict, *, duress: bool = False) -> bool:
        """An existing hash is authoritative even on legacy rows missing flags."""
        prefix = 'duress' if duress else 'sos'
        hashed = user.get(f'{prefix}_pin_hash')
        if hashed is not None:
            return PinHasher.verify_pin(pin, hashed)
        if user.get(f'has_changed_{prefix}_pin', False):
            return False
        return pin == ('9999' if duress else '1234')

    @staticmethod
    def hash_pin(pin: str) -> str:
        """
        Hash mã PIN 4 số thành bcrypt hash (60 chars).

        Args:
            pin: Chuỗi 4 chữ số, ví dụ "1234".

        Returns:
            Bcrypt hash string (60 chars), ví dụ "$2b$10$...".

        Raises:
            ValueError: Nếu PIN không phải 4 chữ số.
        """
        if not isinstance(pin, str) or not _PIN_PATTERN.match(pin):
            raise ValueError("PIN phải là chuỗi đúng 4 chữ số (0-9)")

        # bcrypt giới hạn input 72 bytes, PIN 4 chars (UTF-8 = 4 bytes) OK.
        salt = bcrypt.gensalt(rounds=PinHasher.BCRYPT_ROUNDS)
        hashed_bytes = bcrypt.hashpw(pin.encode("utf-8"), salt)
        return hashed_bytes.decode("utf-8")

    @staticmethod
    def verify_pin(pin: str, hashed: str) -> bool:
        """
        Verify mã PIN với hash đã lưu trong DB.

        Args:
            pin: PIN người dùng nhập (plain text).
            hashed: Bcrypt hash đã lưu trong Firestore.

        Returns:
            True nếu PIN match hash, False nếu sai hoặc input invalid.
        """
        if not isinstance(pin, str) or not isinstance(hashed, str):
            return False
        if not pin or not hashed:
            return False

        try:
            return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
        except (ValueError, TypeError) as e:
            # Có thể hash không hợp lệ (legacy plain text) → log và reject
            logger.warning(f"verify_pin: bcrypt check failed - {e}")
            return False
