"""
=============================================================================
FILE: app/modules/detection/service.py
MODULE: Detection - Application Service Layer
ROLE / RESPONSIBILITY:
    - Điều phối toàn bộ quy trình phát hiện âm thanh và thẩm định rủi ro:
      + Tiếp nhận tín hiệu từ Client/Edge AI (On-device Detection Signals).
      + Phân tích âm thanh thô phía Server (Server-side Audio Classification qua YAMNet + VocalBurst).
      + Gom cụm chuỗi thời gian qua `TemporalAggregator` (Chống false positive theo ADR-010).
      + Thẩm định cấp độ rủi ro qua `RiskEvaluator`.
      + Quản lý giãn cách qua `CooldownManager` (Chống spam alert storm theo ADR-010).
      + Khi phát hiện nguy cấp thực sự $\rightarrow$ Tự động chuyển giao sang `EmergencyService`
        kích hoạt SOS Orchestration Pipeline (ADR-009, ADR-014).
      + Lưu vết lịch sử và Audit Trail vào Firestore `detection_events`.

CONNECTIONS / DEPENDENCIES:
    - app/modules/detection/detectors/ (YAMNetDetector, VocalBurstDetector)
    - app/modules/detection/decision/ (TemporalAggregator, CooldownManager, RiskEvaluator)
    - app/modules/detection/repository.py (DetectionRepository)
    - app/modules/detection/schemas.py
    - app/modules/emergency/service.py (EmergencyService)
    - app/modules/emergency/schemas.py (EmergencyTriggerRequest)
    - app/shared/enums/emergency.py (EmergencySeverity, EmergencyTriggerType)
    - app/shared/schemas/location.py (GeoPointSchema)

INPUT / OUTPUT:
    - Input: user_id, DetectionSignalIngestRequest, AudioAnalyzeRequest.
    - Output: DetectionIngestResponse, DetectionConfigResponse, List[DetectionEventRecordResponse].
=============================================================================
"""

import asyncio
import base64
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import logger
from app.modules.detection.decision.cooldown_manager import CooldownManager
from app.modules.detection.decision.risk_evaluator import RiskEvaluator
from app.modules.detection.decision.temporal_aggregator import TemporalAggregator
from app.modules.detection.detectors.vocal_burst_detector import VocalBurstDetector
from app.modules.detection.detectors.yamnet_detector import YAMNetDetector
from app.modules.detection.repository import DetectionRepository
from app.modules.detection.schemas import (
    AudioAnalyzeRequest,
    DetectionConfigResponse,
    DetectionEventRecordResponse,
    DetectionIngestResponse,
    DetectionSignalIngestRequest,
)
from app.modules.emergency.service import EmergencyService
from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType
from app.shared.schemas.detection_signal import DetectionSignal
from app.shared.schemas.location import GeoPointSchema


class DetectionService:
    """Service điều phối nghiệp vụ nhận diện âm thanh, lọc nhiễu và kích hoạt phản ứng khẩn cấp."""

    def __init__(
        self,
        repository: Optional[DetectionRepository] = None,
        yamnet_detector: Optional[YAMNetDetector] = None,
        vocal_burst_detector: Optional[VocalBurstDetector] = None,
        temporal_aggregator: Optional[TemporalAggregator] = None,
        cooldown_manager: Optional[CooldownManager] = None,
        risk_evaluator: Optional[RiskEvaluator] = None,
        emergency_service: Optional[EmergencyService] = None,
    ) -> None:
        self.settings = get_settings()
        self.repository = repository or DetectionRepository()
        self.yamnet = yamnet_detector or YAMNetDetector()
        self.vocal_burst = vocal_burst_detector or VocalBurstDetector()
        self.temporal_aggregator = temporal_aggregator or TemporalAggregator()
        self.cooldown_manager = cooldown_manager or CooldownManager()
        self.risk_evaluator = risk_evaluator or RiskEvaluator()
        self.emergency_service = emergency_service or EmergencyService()

    async def ingest_signals(
        self, user_id: str, request: DetectionSignalIngestRequest
    ) -> DetectionIngestResponse:
        """
        Tiếp nhận danh sách các tín hiệu đã phân loại từ Edge/Client AI,
        chạy qua bộ lọc chuỗi thời gian (Temporal Filter) và thẩm định rủi ro.
        """
        now = datetime.now(timezone.utc)
        normalized_signals: List[DetectionSignal] = []

        # 1. Chuyển đổi input sang Domain Contract `DetectionSignal`
        for sig_in in request.signals:
            sig = DetectionSignal(
                signal_id=str(uuid.uuid4()),
                event_type=sig_in.event_type,
                model_type=sig_in.model_type,
                confidence=sig_in.confidence,
                start_offset_seconds=sig_in.start_offset_seconds,
                end_offset_seconds=sig_in.end_offset_seconds,
                detected_at=now,
                raw_labels=sig_in.raw_labels,
                metadata={
                    "decibel_peak": sig_in.decibel_peak,
                    "battery_level": request.battery_level,
                },
            )
            normalized_signals.append(sig)

        # 2. Đưa vào cửa sổ trượt tổng hợp chuỗi thời gian (Temporal Aggregation)
        self.temporal_aggregator.add_signals(user_id, normalized_signals)
        summary = self.temporal_aggregator.get_summary(user_id)

        # 3. Thẩm định cấp độ rủi ro (Risk Evaluation)
        decision = self.risk_evaluator.evaluate(summary)

        # 4. Xử lý logic khẩn cấp & Giãn cách Cooldown
        emergency_triggered = False
        session_id = None
        cooldown_active = False
        cooldown_remaining = 0

        event_key = (
            decision.primary_event_type.value
            if decision.primary_event_type
            else AudioEventType.ABNORMAL_UNKNOWN.value
        )

        if decision.is_emergency:
            # Kiểm tra thời gian giãn cách để chống alert storm
            if self.cooldown_manager.is_in_cooldown(user_id, event_key):
                cooldown_active = True
                cooldown_remaining = self.cooldown_manager.get_remaining_seconds(user_id, event_key)
                logger.info(
                    f"Tín hiệu khẩn cấp '{event_key}' của user '{user_id}' đang trong Cooldown "
                    f"({cooldown_remaining}s còn lại), bỏ qua kích hoạt SOS lặp."
                )
            else:
                # QUAN TRỌNG (Refactor): Backend KHÔNG tự gọi trigger_sos() nữa.
                # Chỉ ghi nhận Cooldown và trả is_emergency=True để Client quyết định
                # (hiển thị popup xác nhận hoặc tự trigger tùy theo chính sách).
                # Tránh false positive do TV/music/hội thoại gây bắn SOS thật tới người thân.
                self.cooldown_manager.mark_triggered(user_id, event_key)
                logger.info(
                    f"AI Detection phát hiện nguy hiểm tiềm tàng: '{event_key}' "
                    f"(Confidence: {decision.aggregated_confidence:.2f}, "
                    f"consecutive: {decision.consecutive_detections}). "
                    f"Trả cờ is_emergency=True cho Client hiển thị xác nhận người dùng. "
                    f"emergency_triggered giữ nguyên = False."
                )
                # emergency_triggered giữ nguyên = False
                # session_id giữ nguyên = None
                # Client sẽ tự quyết định dựa trên event_type và confidence.

        # Raw inference windows are ephemeral. Persist only pending alert/SOS
        # transitions, never per-window audio features or detection evidence.

        return DetectionIngestResponse(
            signals_processed=len(normalized_signals),
            risk_level=decision.risk_level,
            is_emergency=decision.is_emergency,
            emergency_triggered=emergency_triggered,
            session_id=session_id,
            cooldown_active=cooldown_active,
            cooldown_remaining_seconds=cooldown_remaining,
            message=decision.reason,
            signals=normalized_signals,
        )

    async def analyze_audio(
        self, user_id: str, request: AudioAnalyzeRequest
    ) -> DetectionIngestResponse:
        """
        Tiếp nhận đoạn âm thanh thô hoặc đặc trưng từ Client để phân tích phía Server.
        """
        audio_bytes = b""
        if request.audio_base64:
            try:
                audio_bytes = base64.b64decode(request.audio_base64, validate=True)
            except Exception as e:
                raise AppException(message="Invalid base64 audio", code="INVALID_AUDIO", status_code=422) from e

        meta: Dict[str, Any] = {
            "sample_rate": request.sample_rate,
            "decibel_peak": request.decibel_peak,
        }
        if request.features:
            meta.update(request.features)

        detected_signals: List[DetectionSignal] = []

        # 1. Gọi YAMNet Detector (Mô hình Deep Learning chính chuẩn Google)
        if audio_bytes:
            if not self.yamnet.is_available():
                raise AppException(
                    message="Audio classification model is unavailable",
                    code="AUDIO_MODEL_UNAVAILABLE",
                    status_code=503,
                )
            try:
                detected_signals.extend(await asyncio.to_thread(self.yamnet.detect, audio_bytes, meta))
            except ValueError as exc:
                raise AppException(message="Invalid PCM/WAV audio", code="INVALID_AUDIO", status_code=422) from exc
            except RuntimeError as exc:
                raise AppException(message="Audio classification failed", code="AUDIO_INFERENCE_FAILED", status_code=503) from exc
        elif request.features:
            detected_signals.extend(self.yamnet.detect_features(meta))

        # Only explicit features may use pitch heuristics. Raw microphone noise
        # must not become a scream when the ML model is unavailable.
        if not detected_signals and not audio_bytes and request.features and "pitch_hz" in request.features:
            detected_signals.extend(self.vocal_burst.detect_features(meta))

        # 3. Đưa signals vừa nhận diện vào luồng Ingest chung
        if not detected_signals:
            # Trường hợp âm thanh hoàn toàn bình thường
            detected_signals.append(
                DetectionSignal(
                    event_type=AudioEventType.ABNORMAL_UNKNOWN,
                    model_type=DetectorModelType.YAMNET,
                    confidence=0.1,
                    risk_level=DetectionRiskLevel.NEGLIGIBLE,
                    metadata=meta,
                )
            )

        from app.modules.detection.schemas import DetectionSignalInput

        ingest_req = DetectionSignalIngestRequest(
            signals=[
                DetectionSignalInput(
                    event_type=s.event_type,
                    model_type=s.model_type,
                    confidence=s.confidence,
                    start_offset_seconds=s.start_offset_seconds,
                    end_offset_seconds=s.end_offset_seconds,
                    decibel_peak=request.decibel_peak,
                    raw_labels=s.raw_labels,
                )
                for s in detected_signals
            ],
            latitude=request.latitude,
            longitude=request.longitude,
            accuracy_meters=request.accuracy_meters,
            battery_level=request.battery_level,
        )

        ingest_res = await self.ingest_signals(user_id, ingest_req)

        if request.monitoring_session_id:
            # Only the actual Screaming label opens this workflow. Generic shout,
            # laughter, crying and loudness are not sufficient evidence.
            candidates = [s for s in detected_signals
                if s.event_type == AudioEventType.SCREAM and s.confidence >= .30
                and any(label.lower() == 'screaming' for label in (s.raw_labels or {}))]
            if candidates:
                from app.modules.detection.alerts.schemas import AlertCandidate
                from app.modules.detection.alerts.service import get_alert_service
                now = datetime.now(timezone.utc)
                ingest_res.alert = await get_alert_service().create(user_id, AlertCandidate(
                    monitoring_session_id=request.monitoring_session_id,
                    idempotency_key=f'{request.monitoring_session_id}:{request.window_end_sample}',
                    captured_at=request.captured_at or now,
                    confidence=max(s.confidence for s in candidates),
                    safety_check_instance_id=request.safety_check_instance_id,
                    latitude=request.latitude, longitude=request.longitude))
        return ingest_res

    def get_config(self) -> DetectionConfigResponse:
        """Lấy thông số cấu hình và danh sách model AI hiện hành."""
        active = []
        if self.yamnet.is_available():
            active.append(self.yamnet.name)
        if self.vocal_burst.is_available():
            active.append(self.vocal_burst.name)

        return DetectionConfigResponse(
            confidence_threshold=self.settings.DETECTION_CONFIDENCE_THRESHOLD,
            window_seconds=self.settings.DETECTION_WINDOW_SECONDS,
            min_consecutive_frames=self.settings.DETECTION_MIN_CONSECUTIVE_FRAMES,
            emergency_risk_threshold=self.settings.DETECTION_EMERGENCY_RISK_THRESHOLD,
            cooldown_seconds=self.settings.DETECTION_COOLDOWN_SECONDS,
            active_detectors=active,
        )

    def list_history(self, user_id: str, limit: int = 20) -> List[DetectionEventRecordResponse]:
        """Truy vấn danh sách các sự kiện phát hiện âm thanh trong quá khứ của người dùng."""
        raw_events = self.repository.list_events_by_user(user_id, limit=limit)
        results: List[DetectionEventRecordResponse] = []

        for e in raw_events:
            loc = None
            if e.get("location"):
                loc = GeoPointSchema(**e["location"])

            try:
                ev_type = AudioEventType(e.get("event_type", AudioEventType.ABNORMAL_UNKNOWN.value))
            except ValueError:
                ev_type = AudioEventType.ABNORMAL_UNKNOWN

            try:
                risk_lvl = DetectionRiskLevel(e.get("risk_level", DetectionRiskLevel.NEGLIGIBLE.value))
            except ValueError:
                risk_lvl = DetectionRiskLevel.NEGLIGIBLE

            results.append(
                DetectionEventRecordResponse(
                    event_id=e["event_id"],
                    user_id=e["user_id"],
                    event_type=ev_type,
                    risk_level=risk_lvl,
                    confidence=float(e.get("confidence", 0.0)),
                    emergency_triggered=bool(e.get("emergency_triggered", False)),
                    session_id=e.get("session_id"),
                    location=loc,
                    created_at=e.get("created_at"),
                )
            )

        return results
