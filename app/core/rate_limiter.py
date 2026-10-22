"""
=============================================================================
FILE: app/core/rate_limiter.py
MODULE: Core - Escalating Backoff Rate Limiter (High-Performance Zero-Waste)
ROLE:
    - Giới hạn tần suất gọi API đăng nhập (POST /api/v1/auth/login) chống Brute-force.
    - Lưu trữ Đa tầng tối ưu hiệu năng (High Performance Multi-tier):
        + Tầng 1: IP Rate Limiting trên RAM (In-Memory) để chống DDoS, kiểm tra < 0.1ms.
        + Tầng 2: Account Lockout trên Firestore DB (`users/{uid}`) để bảo vệ tài khoản
          xuyên suốt MỌI THIẾT BỊ (điện thoại khác, máy tính khác, mạng 4G khác).
        + Tối ưu Zero-Waste: Tận dụng trực tiếp Document User đã đọc để kiểm tra khóa,
          không query lặp lại nhiều lần.
        + Tác vụ ghi Log và Reset cờ vi phạm được đẩy sang Background Task chạy ngầm.
=============================================================================
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status

from app.core.logging import logger
from app.infrastructure.firestore.client import get_firestore_client


class EscalatingRateLimiter:
    """Rate limiter kết hợp In-Memory (cho IP) và Firestore (cho Tài khoản)."""

    LOCKOUT_TIERS: List[int] = [60, 300, 600, 1800, 3600, 86400]

    def __init__(self, max_requests: int = 5, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # In-Memory tracking theo IP: { ip: [t1, t2, ...] }
        self._attempts: Dict[str, List[float]] = defaultdict(list)
        self._lockout_until: Dict[str, float] = {}
        self._current_tier: Dict[str, int] = defaultdict(int)

    def is_ip_allowed(self, client_ip: str) -> bool:
        """Kiểm tra IP trên RAM để chống flooding request từ 1 nguồn (< 0.1ms)."""
        key = f"ip:{client_ip}"
        now = time.time()

        if now < self._lockout_until.get(key, 0):
            return False

        window_start = now - self.window_seconds
        self._attempts[key] = [t for t in self._attempts[key] if t > window_start]
        self._attempts[key].append(now)

        if len(self._attempts[key]) > self.max_requests:
            tier = self._current_tier[key]
            duration = self.LOCKOUT_TIERS[min(tier, len(self.LOCKOUT_TIERS) - 1)]
            self._lockout_until[key] = now + duration
            self._current_tier[key] = min(tier + 1, len(self.LOCKOUT_TIERS) - 1)
            self._attempts[key] = []
            return False

        return True

    def get_ip_remaining_seconds(self, client_ip: str) -> int:
        """Lấy số giây còn lại cần chờ của IP trên RAM."""
        key = f"ip:{client_ip}"
        now = time.time()
        lock_until = self._lockout_until.get(key, 0)
        if lock_until > now:
            return max(int(lock_until - now), 1)
        return 0

    def reset_ip(self, client_ip: str) -> None:
        """Reset theo dõi IP trên RAM."""
        key = f"ip:{client_ip}"
        self._attempts.pop(key, None)
        self._lockout_until.pop(key, None)
        self._current_tier.pop(key, None)

    @staticmethod
    def format_duration_text(seconds: int) -> str:
        """Định dạng thời gian chờ thành văn bản tiếng Việt dễ hiểu."""
        if seconds >= 86400:
            hours = round(seconds / 3600)
            return f"{hours} giờ"
        if seconds >= 3600:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours} giờ {mins} phút" if mins > 0 else f"{hours} giờ"
        if seconds >= 60:
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins} phút {secs} giây" if secs > 0 else f"{mins} phút"
        return f"{seconds} giây"


# Singleton instance
login_rate_limiter = EscalatingRateLimiter(max_requests=5, window_seconds=60)


def check_ip_rate_limit(request: Request) -> None:
    """Kiểm tra IP cực nhanh trên RAM (< 0.1ms) chống tấn công DDoS."""
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    if not login_rate_limiter.is_ip_allowed(client_ip):
        wait_seconds = login_rate_limiter.get_ip_remaining_seconds(client_ip)
        time_text = login_rate_limiter.format_duration_text(wait_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Thiết bị/IP của bạn đang tạm khóa do thao tác quá nhanh. Vui lòng thử lại sau {time_text}.",
            headers={"Retry-After": str(wait_seconds)},
        )


def check_account_lockout(user_data: dict, email: str) -> None:
    """
    Kiểm tra trạng thái khóa tài khoản từ user_data (Zero-waste: Không query lặp lại).
    Áp dụng bảo vệ tài khoản xuyên suốt mọi thiết bị.
    """
    locked_until = user_data.get("locked_until")
    if not locked_until:
        return

    now_utc = datetime.now(timezone.utc)
    # Chuyển đổi Firestore Timestamp / datetime
    if hasattr(locked_until, "to_datetime"):
        locked_until_dt = locked_until.to_datetime()
    elif isinstance(locked_until, datetime):
        locked_until_dt = locked_until
    else:
        try:
            locked_until_dt = datetime.fromisoformat(str(locked_until))
        except Exception:
            return

    if locked_until_dt.tzinfo is None:
        locked_until_dt = locked_until_dt.replace(tzinfo=timezone.utc)

    if now_utc < locked_until_dt:
        wait_seconds = max(int((locked_until_dt - now_utc).total_seconds()), 1)
        time_text = login_rate_limiter.format_duration_text(wait_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Tài khoản '{email}' đang bị tạm khóa bảo vệ trên toàn hệ thống (áp dụng cho mọi thiết bị). Vui lòng thử lại sau {time_text}.",
            headers={"Retry-After": str(wait_seconds)},
        )


def record_failed_login_attempt(email: str) -> None:
    """
    Ghi nhận lần đăng nhập thất bại vào Firestore DB:
    - Chỉ chạy khi người dùng nhập sai mật khẩu.
    - Nếu chạm 5 lần -> Kích hoạt khóa tài khoản theo bậc leo thang (`locked_until`).
    """
    if not email:
        return

    clean_email = email.lower().strip()
    try:
        db = get_firestore_client()
        users_query = db.collection("users").where("email", "==", clean_email).limit(1).get()
        if not users_query:
            return

        user_ref = users_query[0].reference
        user_data = users_query[0].to_dict() or {}

        failed_attempts = int(user_data.get("failed_attempts", 0)) + 1
        tier = int(user_data.get("lockout_tier", 0))
        now_utc = datetime.now(timezone.utc)

        if failed_attempts >= 5:
            duration = EscalatingRateLimiter.LOCKOUT_TIERS[min(tier, len(EscalatingRateLimiter.LOCKOUT_TIERS) - 1)]
            locked_until = now_utc + timedelta(seconds=duration)
            new_tier = min(tier + 1, len(EscalatingRateLimiter.LOCKOUT_TIERS) - 1)

            user_ref.update({
                "failed_attempts": 0,
                "locked_until": locked_until,
                "lockout_tier": new_tier,
                "last_failed_login_at": now_utc,
            })
            time_text = EscalatingRateLimiter.format_duration_text(duration)
            logger.warning(f"Tài khoản {email} đã bị khóa trên Firestore trong {time_text} (Bậc {tier + 1}).")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tài khoản '{email}' đã bị tạm khóa bảo vệ trên toàn hệ thống (áp dụng mọi thiết bị). Vui lòng thử lại sau {time_text}.",
                headers={"Retry-After": str(duration)},
            )
        else:
            user_ref.update({
                "failed_attempts": failed_attempts,
                "last_failed_login_at": now_utc,
            })
            logger.info(f"Tài khoản {email} thử sai {failed_attempts}/5 lần.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi ghi nhận failed login vào Firestore: {str(e)}")


def background_post_login_tasks(
    uid: str,
    client_ip: str,
    user_agent: str,
    login_method: str,
    log_id: str,
    now_utc: datetime,
) -> None:
    """
    Tác vụ chạy ngầm (Non-blocking Background Task):
    - Cập nhật last_login_at và reset cờ vi phạm lockout trong Firestore.
    - Ghi nhận Login Audit Log vào subcollection.
    - Reset rate limiter trên RAM cho IP client.
    Không làm nghẽn luồng phản hồi cho người dùng!
    """
    try:
        db = get_firestore_client()
        user_ref = db.collection("users").document(uid)

        # 1. Cập nhật last_login_at và reset lockout
        user_ref.update({
            "last_login_at": now_utc,
            "failed_attempts": 0,
            "lockout_tier": 0,
            "locked_until": None,
        })

        # 2. Ghi nhận nhật ký đăng nhập (Audit Log)
        log_entry = {
            "log_id": log_id,
            "timestamp": now_utc,
            "ip_address": client_ip,
            "user_agent": user_agent,
            "login_method": login_method,
            "status": "SUCCESS",
        }
        user_ref.collection("login_logs").document(log_id).set(log_entry)

        # 3. Reset IP limiter
        login_rate_limiter.reset_ip(client_ip)
        logger.info(f"Background: Hoàn tất ghi audit log và reset lockout cho UID {uid}")
    except Exception as e:
        logger.warning(f"Lỗi background_post_login_tasks cho UID {uid}: {str(e)}")
