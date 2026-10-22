"""
=============================================================================
FILE: app/modules/detection/decision/temporal_aggregator.py
MODULE: Detection - Temporal Aggregation Engine
ROLE / RESPONSIBILITY:
    - Quản lý bộ đệm cửa sổ trượt (Sliding Time Window) cho các tín hiệu âm thanh của từng người dùng.
    - Chống báo động giả (False Positive Protection theo ADR-010):
      + Loại bỏ các xung âm thanh thoáng qua đơn độc (Transient noise spikes).
      + Yêu cầu tính nhất quán liên tục qua nhiều frame trong cửa sổ thời gian (Temporal Consistency).
    - Tính toán điểm tin cậy tổng hợp (Aggregated Confidence) và số frame liên tiếp (Consecutive frames).
    - Tự động cắt tỉa (Prune) các frame quá hạn ngoài cửa sổ.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/shared/schemas/detection_signal.py (DetectionSignal)
    - app/shared/enums/detection.py (AudioEventType)

INPUT / OUTPUT:
    - Input: user_id, List[DetectionSignal].
    - Output: Aggregation summary dictionary per event_type.
=============================================================================
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.shared.enums.detection import AudioEventType
from app.shared.schemas.detection_signal import DetectionSignal


class TemporalAggregator:
    """Bộ tổng hợp chuỗi thời gian nhằm lọc nhiễu và kiểm tra tính bền vững của tín hiệu."""

    def __init__(self, window_seconds: Optional[float] = None) -> None:
        self.settings = get_settings()
        self.window_seconds: float = (
            window_seconds if window_seconds is not None else self.settings.DETECTION_WINDOW_SECONDS
        )
        # Bộ đệm lưu trữ tín hiệu theo từng người dùng: user_id -> List[DetectionSignal]
        self._buffers: Dict[str, List[DetectionSignal]] = defaultdict(list)

    def add_signals(self, user_id: str, signals: List[DetectionSignal]) -> None:
        """
        Thêm các tín hiệu mới vào cửa sổ trượt của user và dọn dẹp các frame cũ.
        """
        now = datetime.now(timezone.utc)
        user_buffer = self._buffers[user_id]
        user_buffer.extend(signals)

        # Cắt tỉa các frame cũ vượt ngoài cửa sổ trượt (now - window_seconds)
        cutoff_time = now - timedelta(seconds=self.window_seconds)
        self._buffers[user_id] = [
            s for s in user_buffer if (s.detected_at if s.detected_at.tzinfo else s.detected_at.replace(tzinfo=timezone.utc)) >= cutoff_time
        ]

    def get_summary(
        self, user_id: str, confidence_threshold: Optional[float] = None
    ) -> Dict[AudioEventType, Dict[str, Any]]:
        """
        Tổng hợp thống kê các sự kiện trong cửa sổ trượt của user:
        - Số lượng frame phát hiện.
        - Số lượng frame liên tiếp đạt ngưỡng (consecutive count).
        - Điểm tin cậy tổng hợp (trung bình có trọng số ưu tiên frame mới nhất).
        - Điểm nhất quán thời gian (temporal consistency).
        """
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self.settings.DETECTION_CONFIDENCE_THRESHOLD
        )
        user_buffer = self._buffers.get(user_id, [])
        if not user_buffer:
            return {}

        # Phân nhóm signals theo loại sự kiện âm thanh
        by_event: Dict[AudioEventType, List[DetectionSignal]] = defaultdict(list)
        for sig in user_buffer:
            by_event[sig.event_type].append(sig)

        summary: Dict[AudioEventType, Dict[str, Any]] = {}

        for event_type, sigs in by_event.items():
            # Sắp xếp theo thứ tự thời gian phát hiện
            sorted_sigs = sorted(sigs, key=lambda s: s.detected_at)
            total_count = len(sorted_sigs)

            # Lọc các frame đạt ngưỡng tin cậy
            valid_sigs = [s for s in sorted_sigs if s.confidence >= threshold]
            valid_count = len(valid_sigs)

            # Tính số frame liên tiếp tối đa đạt ngưỡng
            max_consecutive = 0
            current_consecutive = 0
            for s in sorted_sigs:
                if s.confidence >= threshold:
                    current_consecutive += 1
                    if current_consecutive > max_consecutive:
                        max_consecutive = current_consecutive
                else:
                    current_consecutive = 0

            # Tính điểm tin cậy tổng hợp có trọng số
            if valid_sigs:
                weights = [1.0 + (i * 0.2) for i in range(len(valid_sigs))]
                weighted_sum = sum(s.confidence * w for s, w in zip(valid_sigs, weights))
                agg_confidence = min(1.0, weighted_sum / sum(weights))
            else:
                agg_confidence = sum(s.confidence for s in sorted_sigs) / max(total_count, 1)

            consistency_score = valid_count / max(total_count, 1)

            summary[event_type] = {
                "event_type": event_type,
                "total_frames": total_count,
                "valid_frames": valid_count,
                "consecutive_detections": max_consecutive,
                "aggregated_confidence": round(float(agg_confidence), 4),
                "temporal_consistency": round(float(consistency_score), 4),
                "latest_signal": sorted_sigs[-1],
            }

        return summary

    def clear(self, user_id: str) -> None:
        """Xóa sạch bộ đệm của một user (sau khi đã kích hoạt SOS hoặc reset)."""
        self._buffers.pop(user_id, None)
