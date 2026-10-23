"""
=============================================================================
FILE: app/modules/emergency/safety_check/scheduler.py
MODULE: Safety Check - Async Expiration Scheduler
ROLE / RESPONSIBILITY:
    - Background Worker chạy ngầm định kỳ bằng `asyncio` (ADR-031).
    - Quét các phiên hẹn giờ kiểm tra an toàn đã hết hạn Grace Period (`grace_period_until <= now`).
    - Kích hoạt quy trình leo thang (`escalate_instance`) gửi cảnh báo Telegram tới người thân kèm vị trí gần nhất.
    - Cung cấp phương thức `start()` và `stop()` gắn vào vòng đời `lifespan` của FastAPI.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/core/logging.py (logger)
    - app/modules/emergency/safety_check/service.py (SafetyCheckService)
    - app/modules/emergency/safety_check/repository.py (SafetyCheckRepository)

INPUT / OUTPUT:
    - Background task triggers periodic escalation events.
=============================================================================
"""

import asyncio
from typing import Optional

from app.core.config import get_settings
from app.core.logging import logger
from app.modules.emergency.safety_check.service import SafetyCheckService


class SafetyCheckScheduler:
    """Worker chạy ngầm định kỳ kiểm tra các phiên Safety Check quá hạn."""

    def __init__(self, service: Optional[SafetyCheckService] = None) -> None:
        self.service = service or SafetyCheckService()
        self.settings = get_settings()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    async def _worker_loop(self) -> None:
        """Vòng lặp kiểm tra định kỳ mỗi 15-30 giây (Non-blocking)."""
        logger.info(f"Khởi động SafetyCheckScheduler (Chu kỳ: {self.settings.SCHEDULER_INTERVAL_SECONDS}s)...")
        while self._running:
            try:
                # Nghỉ theo chu kỳ cấu hình trước khi quét
                await asyncio.sleep(self.settings.SCHEDULER_INTERVAL_SECONDS)
                if not self._running:
                    break

                # Quét các instance quá hạn Grace Period qua worker thread (không block event loop)
                overdue_instances = await asyncio.to_thread(self.service.repository.get_overdue_instances)
                if overdue_instances:
                    logger.info(f"Phát hiện {len(overdue_instances)} phiên Safety Check quá hạn, đang xử lý leo thang cảnh báo...")
                    for inst in overdue_instances:
                        try:
                            await self.service.escalate_instance(inst)
                        except Exception as e:
                            logger.error(f"Lỗi khi escalate instance '{inst.get('instance_id')}': {str(e)}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lỗi trong vòng lặp SafetyCheckScheduler: {str(e)}")

        logger.info("SafetyCheckScheduler đã dừng.")

    def start(self) -> None:
        """Bắt đầu chạy worker ngầm."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())

    def stop(self) -> None:
        """Dừng worker ngầm an toàn."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()

    async def wait_stopped(self) -> None:
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        close = getattr(self.service.repository, 'close', None)
        if close:
            await asyncio.to_thread(close)


# Singleton scheduler instance
safety_check_scheduler = SafetyCheckScheduler()
