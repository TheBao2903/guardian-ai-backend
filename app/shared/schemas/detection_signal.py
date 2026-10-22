"""
=============================================================================
FILE: app/shared/schemas/detection_signal.py
MODULE: Shared - Detection Signal Contract
ROLE / RESPONSIBILITY:
    - Định nghĩa cấu trúc chuẩn hóa cho tín hiệu nhận diện âm thanh (DetectionSignal).
    - Chuẩn hóa đầu ra từ các AI model khác nhau (YAMNet, VocalBurst, Whisper)
      về cùng một định dạng thống nhất trước khi chuyển vào Temporal Aggregation.
    - Đảm bảo tuân thủ ADR-009 (Separate Detection from Emergency Decision).

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/detection.py (AudioEventType, DetectorModelType, DetectionRiskLevel)
    - Sử dụng bởi: Detection module, Emergency decision engine.

INPUT / OUTPUT:
    - DetectionSignal: { signal_id, event_type, model_type, confidence, risk_level, ... }.
=============================================================================
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType


class DetectionSignal(BaseModel):
    """Bản tin tín hiệu nhận diện âm thanh chuẩn hóa từ tầng AI Model."""
    signal_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Mã định danh duy nhất của tín hiệu phát hiện",
    )
    event_type: AudioEventType = Field(
        ...,
        description="Loại sự kiện âm thanh phát hiện (SCREAM, GUNSHOT, GLASS_SHATTER...)",
    )
    model_type: DetectorModelType = Field(
        ...,
        description="Model AI thực hiện phân loại (YAMNET, VOCAL_BURST...)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của mô hình (0.0 đến 1.0)",
    )
    risk_level: DetectionRiskLevel = Field(
        default=DetectionRiskLevel.NEGLIGIBLE,
        description="Mức độ rủi ro sơ bộ được gán cho tín hiệu",
    )
    start_offset_seconds: float = Field(
        0.0,
        ge=0.0,
        description="Vị trí thời gian bắt đầu sự kiện trong đoạn âm thanh (giây)",
    )
    end_offset_seconds: float = Field(
        0.0,
        ge=0.0,
        description="Vị trí thời gian kết thúc sự kiện trong đoạn âm thanh (giây)",
    )
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Thời điểm server ghi nhận tín hiệu (UTC)",
    )
    raw_labels: Optional[Dict[str, float]] = Field(
        default=None,
        description="Nhãn phân loại thô cùng điểm số tương ứng từ model",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Thông tin ngữ cảnh bổ sung (sample_rate, decibel_peak, device_id...)",
    )

    def is_high_risk(self, threshold: float = 0.75) -> bool:
        """Kiểm tra tín hiệu có vượt ngưỡng nguy cơ cao hay không."""
        return self.confidence >= threshold and self.event_type in {
            AudioEventType.SCREAM,
            AudioEventType.CALL_FOR_HELP,
            AudioEventType.GUNSHOT,
            AudioEventType.EXPLOSION,
            AudioEventType.VIOLENT_STRUGGLE,
        }
