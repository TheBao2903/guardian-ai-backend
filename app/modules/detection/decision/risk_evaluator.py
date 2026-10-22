"""
=============================================================================
FILE: app/modules/detection/decision/risk_evaluator.py
MODULE: Detection - Risk Evaluation & Emergency Decision Engine
ROLE / RESPONSIBILITY:
    - Đánh giá cấp độ rủi ro tổng thể dựa trên kết quả tổng hợp chuỗi thời gian (Temporal Summary).
    - Phân loại 4 cấp độ: NEGLIGIBLE -> SUSPICIOUS -> WARNING -> EMERGENCY.
    - Ra quyết định chính xác: Biến cố âm thanh có đủ độ tin cậy và tính bền vững theo thời gian
      để kích hoạt quy trình cứu nạn khẩn cấp (Emergency SOS Workflow) hay không.
    - Tuân thủ ADR-009, ADR-010, ADR-011.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/modules/detection/schemas.py (RiskDecisionResult)
    - app/shared/enums/detection.py (AudioEventType, DetectionRiskLevel)

INPUT / OUTPUT:
    - Input: temporal_summary: Dict[AudioEventType, Dict[str, Any]].
    - Output: RiskDecisionResult.
=============================================================================
"""

from typing import Any, Dict, Optional, Set

from app.core.config import get_settings
from app.modules.detection.schemas import RiskDecisionResult
from app.shared.enums.detection import AudioEventType, DetectionRiskLevel

CRITICAL_EVENTS: Set[AudioEventType] = {
    AudioEventType.SCREAM,
    AudioEventType.GUNSHOT,
    AudioEventType.EXPLOSION,
    AudioEventType.CALL_FOR_HELP,
    AudioEventType.VIOLENT_STRUGGLE,
}

ELEVATED_EVENTS: Set[AudioEventType] = {
    AudioEventType.DISTRESS_CRY,
    AudioEventType.GLASS_SHATTER,
    AudioEventType.CAR_CRASH_SOUND,
    AudioEventType.AGGRESSIVE_BARK,
    AudioEventType.ENVIRONMENTAL_ALARM,
}


class RiskEvaluator:
    """Bộ thẩm định mức độ nguy hiểm và đưa ra quyết định kích hoạt khẩn cấp."""

    def __init__(
        self,
        emergency_threshold: Optional[float] = None,
        min_consecutive_frames: Optional[int] = None,
    ) -> None:
        self.settings = get_settings()
        self.emergency_threshold: float = (
            emergency_threshold
            if emergency_threshold is not None
            else self.settings.DETECTION_EMERGENCY_RISK_THRESHOLD
        )
        self.min_consecutive_frames: int = (
            min_consecutive_frames
            if min_consecutive_frames is not None
            else self.settings.DETECTION_MIN_CONSECUTIVE_FRAMES
        )

    def evaluate(
        self, temporal_summary: Dict[AudioEventType, Dict[str, Any]]
    ) -> RiskDecisionResult:
        """
        Thẩm định danh sách thống kê các sự kiện âm thanh trong cửa sổ trượt.
        Trả về kết quả quyết định rủi ro tổng hợp.
        """
        if not temporal_summary:
            return RiskDecisionResult(
                risk_level=DetectionRiskLevel.NEGLIGIBLE,
                is_emergency=False,
                aggregated_confidence=0.0,
                primary_event_type=None,
                consecutive_detections=0,
                temporal_consistency_score=0.0,
                reason="Không có tín hiệu âm thanh nào được ghi nhận trong cửa sổ quan sát.",
            )

        # 1. Kiểm tra nhóm biến cố khẩn cấp cao nhất (CRITICAL_EVENTS)
        best_critical_event = None
        best_critical_stats = None
        for ev, stats in temporal_summary.items():
            if ev in CRITICAL_EVENTS:
                if (
                    not best_critical_stats
                    or stats["aggregated_confidence"] > best_critical_stats["aggregated_confidence"]
                ):
                    best_critical_event = ev
                    best_critical_stats = stats

        if best_critical_stats:
            agg_conf = best_critical_stats["aggregated_confidence"]
            consec = best_critical_stats["consecutive_detections"]
            consistency = best_critical_stats["temporal_consistency"]

            # Điều kiện kích hoạt khẩn cấp: Đạt ngưỡng tự tin + đủ số frame liên tiếp chống false positive
            if agg_conf >= self.emergency_threshold and consec >= self.min_consecutive_frames:
                return RiskDecisionResult(
                    risk_level=DetectionRiskLevel.EMERGENCY,
                    is_emergency=True,
                    aggregated_confidence=agg_conf,
                    primary_event_type=best_critical_event,
                    consecutive_detections=consec,
                    temporal_consistency_score=consistency,
                    reason=(
                        f"Phát hiện sự kiện nghiêm trọng '{best_critical_event.value}' với độ tin cậy cao "
                        f"({agg_conf:.2f} >= {self.emergency_threshold:.2f}) qua {consec} frame liên tiếp. "
                        "Kích hoạt quy trình khẩn cấp."
                    ),
                )

            # Nếu phát hiện âm thanh nghiêm trọng nhưng chưa đủ frame liên tiếp hoặc chưa chạm ngưỡng cao nhất
            return RiskDecisionResult(
                risk_level=DetectionRiskLevel.WARNING,
                is_emergency=False,
                aggregated_confidence=agg_conf,
                primary_event_type=best_critical_event,
                consecutive_detections=consec,
                temporal_consistency_score=consistency,
                reason=(
                    f"Ghi nhận tín hiệu nguy cơ '{best_critical_event.value}' ({agg_conf:.2f}), "
                    f"nhưng chưa đủ tính bền vững theo thời gian ({consec}/{self.min_consecutive_frames} frame) "
                    "để tự động kích hoạt SOS."
                ),
            )

        # 2. Kiểm tra nhóm sự kiện cảnh báo (ELEVATED_EVENTS)
        best_elevated_event = None
        best_elevated_stats = None
        for ev, stats in temporal_summary.items():
            if ev in ELEVATED_EVENTS:
                if (
                    not best_elevated_stats
                    or stats["aggregated_confidence"] > best_elevated_stats["aggregated_confidence"]
                ):
                    best_elevated_event = ev
                    best_elevated_stats = stats

        if best_elevated_stats:
            agg_conf = best_elevated_stats["aggregated_confidence"]
            consec = best_elevated_stats["consecutive_detections"]
            consistency = best_elevated_stats["temporal_consistency"]

            if agg_conf >= 0.75 and consec >= 2:
                return RiskDecisionResult(
                    risk_level=DetectionRiskLevel.WARNING,
                    is_emergency=False,
                    aggregated_confidence=agg_conf,
                    primary_event_type=best_elevated_event,
                    consecutive_detections=consec,
                    temporal_consistency_score=consistency,
                    reason=(
                        f"Phát hiện âm thanh bất thường '{best_elevated_event.value}' có cường độ cao ({agg_conf:.2f}). "
                        "Đưa vào trạng thái Cảnh báo theo dõi."
                    ),
                )
            else:
                return RiskDecisionResult(
                    risk_level=DetectionRiskLevel.SUSPICIOUS,
                    is_emergency=False,
                    aggregated_confidence=agg_conf,
                    primary_event_type=best_elevated_event,
                    consecutive_detections=consec,
                    temporal_consistency_score=consistency,
                    reason=f"Phát hiện âm thanh đáng ngờ '{best_elevated_event.value}' ({agg_conf:.2f}).",
                )

        # 3. Các âm thanh còn lại
        top_event, top_stats = max(
            temporal_summary.items(), key=lambda item: item[1]["aggregated_confidence"]
        )
        conf = top_stats["aggregated_confidence"]
        return RiskDecisionResult(
            risk_level=DetectionRiskLevel.SUSPICIOUS if conf >= 0.50 else DetectionRiskLevel.NEGLIGIBLE,
            is_emergency=False,
            aggregated_confidence=conf,
            primary_event_type=top_event,
            consecutive_detections=top_stats["consecutive_detections"],
            temporal_consistency_score=top_stats["temporal_consistency"],
            reason=f"Âm thanh '{top_event.value}' ở mức độ an toàn (Confidence: {conf:.2f}).",
        )
