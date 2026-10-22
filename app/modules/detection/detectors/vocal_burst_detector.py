"""
=============================================================================
FILE: app/modules/detection/detectors/vocal_burst_detector.py
MODULE: Detection - VocalBurst Distress & Scream Detector
ROLE / RESPONSIBILITY:
    - Chuyên biệt hóa nhận diện các âm thanh khẩn cấp từ thanh quản con người:
      + SCREAM (Tiếng la hét kinh hoàng)
      + DISTRESS_CRY (Tiếng khóc thét, rên rỉ đau đớn)
      + CALL_FOR_HELP (Tiếng kêu cứu thất thanh)
    - Phân tích các đặc trưng âm học: Tần số cơ bản F0, Zero Crossing Rate (ZCR),
      Cường độ âm lượng Peak Decibel, và năng lượng dải tần cao.
    - Tuân thủ ADR-009, ADR-011.

CONNECTIONS / DEPENDENCIES:
    - app/modules/detection/detectors/base.py (BaseAudioDetector)
    - app/shared/enums/detection.py (AudioEventType, DetectorModelType, DetectionRiskLevel)
    - app/shared/schemas/detection_signal.py (DetectionSignal)

INPUT / OUTPUT:
    - Input: audio_bytes hoặc features dictionary.
    - Output: List[DetectionSignal].
=============================================================================
"""

import math
import struct
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.modules.detection.detectors.base import BaseAudioDetector
from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType
from app.shared.schemas.detection_signal import DetectionSignal


class VocalBurstDetector(BaseAudioDetector):
    """Mô hình chuyên biệt phát hiện tiếng la hét (Scream) và âm thanh đau đớn từ thanh quản."""

    def __init__(self) -> None:
        super().__init__(
            model_type=DetectorModelType.VOCAL_BURST,
            name="VocalBurst Scream & Distress Detector",
        )
        self._ready: bool = True

    def is_available(self) -> bool:
        return self._ready

    def detect_features(self, features: Dict[str, Any]) -> List[DetectionSignal]:
        """
        Phân tích dựa trên các đặc tính âm học (Acoustic Descriptors) trích xuất từ thiết bị:
        - pitch_hz: Tần số cơ bản (F0). Giọng nói thường: 100-300Hz; Tiếng hét: 600-1500Hz+.
        - decibel_peak: Âm lượng đỉnh (> 75 dB).
        - spectral_centroid: Trọng tâm phổ dải tần cao.
        - scream_probability: Điểm xác suất mô hình VocalBurst on-device nếu có.
        """
        signals: List[DetectionSignal] = []
        now = datetime.now(timezone.utc)

        # 1. Nếu client đã tính sẵn xác suất scream/distress từ mô hình on-device
        prob = features.get("scream_probability") or features.get("vocal_burst_score")
        if prob is not None:
            conf = float(prob)
            if conf >= 0.50:
                is_critical = conf >= 0.75
                signals.append(
                    DetectionSignal(
                        signal_id=str(uuid.uuid4()),
                        event_type=AudioEventType.SCREAM,
                        model_type=self.model_type,
                        confidence=round(conf, 4),
                        risk_level=DetectionRiskLevel.EMERGENCY if is_critical else DetectionRiskLevel.WARNING,
                        detected_at=now,
                        raw_labels={"scream": conf},
                        metadata={
                            "detector": self.name,
                            "decibel_peak": features.get("decibel_peak"),
                            "pitch_hz": features.get("pitch_hz"),
                        },
                    )
                )
                return signals

        # 2. Heuristic phân tích dựa trên đặc tính âm học
        pitch = float(features.get("pitch_hz", 0.0))
        decibel = float(features.get("decibel_peak", 0.0))
        duration = float(features.get("duration_seconds", 0.5))

        # Tiếng hét có đặc trưng: Âm lượng cao (> 75 dB) + Tần số cao vút (600Hz - 2000Hz)
        if decibel >= 75.0 and pitch >= 600.0:
            confidence = min(0.96, 0.55 + (pitch / 3000.0) + (decibel - 75.0) / 100.0)
            confidence = round(confidence, 4)
            signals.append(
                DetectionSignal(
                    signal_id=str(uuid.uuid4()),
                    event_type=AudioEventType.SCREAM,
                    model_type=self.model_type,
                    confidence=confidence,
                    risk_level=DetectionRiskLevel.EMERGENCY if confidence >= 0.80 else DetectionRiskLevel.WARNING,
                    detected_at=now,
                    raw_labels={"scream": confidence},
                    metadata={
                        "detector": self.name,
                        "decibel_peak": decibel,
                        "pitch_hz": pitch,
                        "duration_seconds": duration,
                    },
                )
            )
        elif decibel >= 70.0 and 400.0 <= pitch < 600.0:
            # Tiếng khóc thét hoặc rên rỉ đau đớn (Distress Cry)
            confidence = round(min(0.85, 0.50 + (decibel - 70.0) / 80.0), 4)
            signals.append(
                DetectionSignal(
                    signal_id=str(uuid.uuid4()),
                    event_type=AudioEventType.DISTRESS_CRY,
                    model_type=self.model_type,
                    confidence=confidence,
                    risk_level=DetectionRiskLevel.WARNING,
                    detected_at=now,
                    raw_labels={"distress_cry": confidence},
                    metadata={
                        "detector": self.name,
                        "decibel_peak": decibel,
                        "pitch_hz": pitch,
                    },
                )
            )

        return signals

    def detect(
        self, audio_bytes: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> List[DetectionSignal]:
        """
        Phân tích mảng byte âm thanh PCM 16-bit:
        - Ước lượng Pitch qua Zero-Crossing Rate (ZCR).
        - Tính toán năng lượng âm lượng RMS.
        """
        metadata = metadata or {}
        if not audio_bytes or len(audio_bytes) < 64:
            return []

        # Bỏ qua RIFF header 44 bytes nếu là file WAV chuẩn
        raw_pcm = audio_bytes
        if len(raw_pcm) > 44 and raw_pcm[:4] == b"RIFF" and raw_pcm[8:12] == b"WAVE":
            raw_pcm = raw_pcm[44:]

        try:
            sample_count = len(raw_pcm) // 2
            samples = struct.unpack(f"<{sample_count}h", raw_pcm[: sample_count * 2])
            sample_rate = int(metadata.get("sample_rate", 16000))

            # Tính RMS decibel
            sum_squares = sum(s * s for s in samples)
            rms = math.sqrt(sum_squares / max(sample_count, 1))
            decibel = 20 * math.log10(max(rms, 1.0))

            # Ước lượng Zero Crossing Rate (ZCR)
            zero_crossings = 0
            for i in range(1, sample_count):
                if (samples[i - 1] >= 0 and samples[i] < 0) or (samples[i - 1] < 0 and samples[i] >= 0):
                    zero_crossings += 1

            zcr = zero_crossings / max(sample_count, 1)
            # Ước lượng tần số cơ bản tương đối từ ZCR
            estimated_pitch = round((zcr * sample_rate) / 2.0, 1)

            features = dict(metadata)
            features["decibel_peak"] = round(decibel, 2)
            features["pitch_hz"] = estimated_pitch

            return self.detect_features(features)

        except Exception:
            return self.detect_features(metadata)
