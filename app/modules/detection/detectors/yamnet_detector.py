"""
=============================================================================
FILE: app/modules/detection/detectors/yamnet_detector.py
MODULE: Detection - YAMNet Baseline Detector
ROLE / RESPONSIBILITY:
    - Triển khai bộ phân loại âm thanh tổng quát dựa trên chuẩn Google YAMNet (AudioSet ontology).
    - Ánh xạ các nhãn lớp âm thanh sang 11 `AudioEventType` chuẩn hóa của hệ thống Guardian AI.
    - Phân tích cả byte âm thanh thô lẫn vector xác suất / đặc trưng từ Edge AI.
    - Tuân thủ ADR-009 (Tách biệt phát hiện âm thanh khỏi Emergency Decision).

CONNECTIONS / DEPENDENCIES:
    - app/modules/detection/detectors/base.py (BaseAudioDetector)
    - app/shared/enums/detection.py (AudioEventType, DetectorModelType, DetectionRiskLevel)
    - app/shared/schemas/detection_signal.py (DetectionSignal)

INPUT / OUTPUT:
    - Input: audio_bytes hoặc features dictionary.
    - Output: List[DetectionSignal].
=============================================================================
"""

import csv
import os
import uuid
import wave
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
import numpy as np

from app.core.logging import logger
from app.modules.detection.detectors.base import BaseAudioDetector
from app.modules.detection.detectors.audio_input import decode_waveform
from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType
from app.shared.schemas.detection_signal import DetectionSignal

# Bản đồ ánh xạ từ nhãn AudioSet/YAMNet sang AudioEventType của Guardian AI
AUDIOSET_LABEL_MAPPING: Dict[str, AudioEventType] = {
    "screaming": AudioEventType.SCREAM,
    "scream": AudioEventType.SCREAM,
    "shout": AudioEventType.SCREAM,
    "yell": AudioEventType.SCREAM,
    "crying, sobbing": AudioEventType.DISTRESS_CRY,
    "crying": AudioEventType.DISTRESS_CRY,
    "wail, moan": AudioEventType.DISTRESS_CRY,
    "glass": AudioEventType.GLASS_SHATTER,
    "glass breaking": AudioEventType.GLASS_SHATTER,
    "shatter": AudioEventType.GLASS_SHATTER,
    "gunshot, gunfire": AudioEventType.GUNSHOT,
    "gunshot": AudioEventType.GUNSHOT,
    "cap gun": AudioEventType.GUNSHOT,
    "explosion": AudioEventType.EXPLOSION,
    "burst, pop": AudioEventType.EXPLOSION,
    "boom": AudioEventType.EXPLOSION,
    "fighting": AudioEventType.VIOLENT_STRUGGLE,
    "struggle": AudioEventType.VIOLENT_STRUGGLE,
    "wrestling": AudioEventType.VIOLENT_STRUGGLE,
    "bark": AudioEventType.AGGRESSIVE_BARK,
    "dog": AudioEventType.AGGRESSIVE_BARK,
    "growling": AudioEventType.AGGRESSIVE_BARK,
    "car crash": AudioEventType.CAR_CRASH_SOUND,
    "skidding": AudioEventType.CAR_CRASH_SOUND,
    "tire squeal": AudioEventType.CAR_CRASH_SOUND,
    "siren": AudioEventType.ENVIRONMENTAL_ALARM,
    "fire alarm": AudioEventType.ENVIRONMENTAL_ALARM,
    "smoke detector": AudioEventType.ENVIRONMENTAL_ALARM,
    "alarm": AudioEventType.ENVIRONMENTAL_ALARM,
}

# Bản đồ ánh xạ chỉ mục lớp (Class Index) AudioSet YAMNet sang AudioEventType
AUDIOSET_INDEX_MAPPING: Dict[int, AudioEventType] = {
    11: AudioEventType.SCREAM,  # Screaming
    6: AudioEventType.SCREAM,   # Shout
    9: AudioEventType.SCREAM,   # Yell
    10: AudioEventType.SCREAM,  # Children shouting
    19: AudioEventType.DISTRESS_CRY,  # Crying, sobbing
    20: AudioEventType.DISTRESS_CRY,  # Baby cry, infant cry
    22: AudioEventType.DISTRESS_CRY,  # Wail, moan
    33: AudioEventType.DISTRESS_CRY,  # Groan
    70: AudioEventType.AGGRESSIVE_BARK,  # Bark
    304: AudioEventType.ENVIRONMENTAL_ALARM,  # Car alarm
    316: AudioEventType.ENVIRONMENTAL_ALARM,  # Emergency vehicle
    317: AudioEventType.ENVIRONMENTAL_ALARM,  # Police car (siren)
    318: AudioEventType.ENVIRONMENTAL_ALARM,  # Ambulance (siren)
    319: AudioEventType.ENVIRONMENTAL_ALARM,  # Fire engine, fire truck (siren)
    382: AudioEventType.ENVIRONMENTAL_ALARM,  # Alarm
    390: AudioEventType.ENVIRONMENTAL_ALARM,  # Siren
    391: AudioEventType.ENVIRONMENTAL_ALARM,  # Civil defense siren
    393: AudioEventType.ENVIRONMENTAL_ALARM,  # Smoke detector, smoke alarm
    394: AudioEventType.ENVIRONMENTAL_ALARM,  # Fire alarm
    420: AudioEventType.EXPLOSION,  # Explosion
    421: AudioEventType.GUNSHOT,  # Gunshot, gunfire
    434: AudioEventType.GLASS_SHATTER,  # Crack
    435: AudioEventType.GLASS_SHATTER,  # Glass
    464: AudioEventType.GLASS_SHATTER,  # Breaking
    463: AudioEventType.CAR_CRASH_SOUND,  # Smash, crash
}


def _get_models_dir() -> str:
    """Xác định đường dẫn thư mục models."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(base_dir, "models")


def _ensure_yamnet_model_files(models_dir: str) -> None:
    """Tự động tải model YAMNet ONNX từ Hugging Face nếu chưa tồn tại trên đĩa."""
    os.makedirs(models_dir, exist_ok=True)
    onnx_path = os.path.join(models_dir, "yamnet.onnx")
    csv_path = os.path.join(models_dir, "yamnet_class_map.csv")

    try:
        if not os.path.exists(csv_path):
            logger.info("Đang tự động tải YAMNet class map từ Hugging Face...")
            r = httpx.get(
                "https://huggingface.co/zeropointnine/yamnet-onnx/resolve/main/yamnet_class_map.csv",
                follow_redirects=True,
                timeout=30.0,
            )
            if r.status_code == 200:
                with open(csv_path, "wb") as f:
                    f.write(r.content)

        if not os.path.exists(onnx_path):
            logger.info("Đang tự động tải model YAMNet ONNX (~15.3MB) từ Hugging Face...")
            r = httpx.get(
                "https://huggingface.co/zeropointnine/yamnet-onnx/resolve/main/yamnet.onnx",
                follow_redirects=True,
                timeout=60.0,
            )
            if r.status_code == 200:
                with open(onnx_path, "wb") as f:
                    f.write(r.content)
                logger.info("Tải model YAMNet ONNX thành công!")
    except Exception as e:
        logger.warning(f"Không thể tự động tải YAMNet model từ Hugging Face: {str(e)}")


class YAMNetDetector(BaseAudioDetector):
    """Mô hình phân loại âm thanh tổng quát theo chuẩn Google YAMNet (Hỗ trợ ONNX Deep Learning Inference)."""

    def __init__(self) -> None:
        super().__init__(
            model_type=DetectorModelType.YAMNET,
            name="Google YAMNet Audio Classifier",
        )
        self._ready: bool = False
        self._onnx_session: Any = None
        self._class_names: Dict[int, str] = {}
        self._init_onnx_model()

    def _init_onnx_model(self) -> None:
        """Khởi tạo phiên Inference ONNX Runtime cho model YAMNet."""
        try:
            import onnxruntime as ort

            models_dir = _get_models_dir()
            _ensure_yamnet_model_files(models_dir)

            onnx_path = os.path.join(models_dir, "yamnet.onnx")
            csv_path = os.path.join(models_dir, "yamnet_class_map.csv")

            if os.path.exists(csv_path):
                with open(csv_path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        self._class_names[int(row["index"])] = row["display_name"]

            if os.path.exists(onnx_path):
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                self._onnx_session = ort.InferenceSession(onnx_path, sess_options=opts)
                self._ready = True
                logger.info(f"YAMNet ONNX Model đã nạp thành công từ: {onnx_path}")
            else:
                logger.warning("File yamnet.onnx chưa có sẵn, audio model unavailable.")
        except Exception as e:
            logger.warning(f"Lỗi khi nạp YAMNet ONNX session: {str(e)}. Audio model unavailable.")

    def is_available(self) -> bool:
        """Report actual model readiness, rather than heuristic availability."""
        return self._ready

    def _determine_risk_level(self, event_type: AudioEventType, confidence: float) -> DetectionRiskLevel:
        """Đánh giá cấp độ rủi ro sơ bộ của tín hiệu dựa vào loại sự kiện và độ tin cậy."""
        if confidence < 0.50:
            return DetectionRiskLevel.NEGLIGIBLE

        critical_events = {
            AudioEventType.SCREAM,
            AudioEventType.GUNSHOT,
            AudioEventType.EXPLOSION,
            AudioEventType.VIOLENT_STRUGGLE,
            AudioEventType.CALL_FOR_HELP,
        }
        warning_events = {
            AudioEventType.DISTRESS_CRY,
            AudioEventType.GLASS_SHATTER,
            AudioEventType.CAR_CRASH_SOUND,
            AudioEventType.AGGRESSIVE_BARK,
            AudioEventType.ENVIRONMENTAL_ALARM,
        }

        if event_type in critical_events:
            return DetectionRiskLevel.EMERGENCY if confidence >= 0.80 else DetectionRiskLevel.WARNING
        elif event_type in warning_events:
            return DetectionRiskLevel.WARNING if confidence >= 0.75 else DetectionRiskLevel.SUSPICIOUS

        return DetectionRiskLevel.SUSPICIOUS

    def detect_features(self, features: Dict[str, Any]) -> List[DetectionSignal]:
        """
        Phân tích mảng xác suất hoặc các nhãn phân loại thô trích xuất từ Edge/Client.
        """
        signals: List[DetectionSignal] = []
        raw_labels = features.get("raw_labels") or {}
        now = datetime.now(timezone.utc)

        # Duyệt qua các nhãn phân loại thô và tìm nhãn trùng khớp
        for label_name, score in raw_labels.items():
            normalized_key = label_name.strip().lower()
            matched_type = AUDIOSET_LABEL_MAPPING.get(normalized_key)
            threshold = 0.30 if matched_type in {AudioEventType.SCREAM, AudioEventType.GUNSHOT, AudioEventType.EXPLOSION} else 0.40
            if matched_type and score >= threshold:
                risk_lvl = self._determine_risk_level(matched_type, score)
                signals.append(
                    DetectionSignal(
                        signal_id=str(uuid.uuid4()),
                        event_type=matched_type,
                        model_type=self.model_type,
                        confidence=round(float(score), 4),
                        risk_level=risk_lvl,
                        start_offset_seconds=float(features.get("start_offset_seconds", 0.0)),
                        end_offset_seconds=float(features.get("end_offset_seconds", 0.0)),
                        detected_at=now,
                        raw_labels={label_name: float(score)},
                        metadata={
                            "detector": self.name,
                            "matched_label": label_name,
                            "decibel_peak": features.get("decibel_peak"),
                        },
                    )
                )

        # Nếu có nhãn event_type trực tiếp trong features
        direct_event = features.get("event_type")
        if direct_event and not signals:
            try:
                ev_type = AudioEventType(direct_event)
                conf = float(features.get("confidence", 0.5))
                signals.append(
                    DetectionSignal(
                        signal_id=str(uuid.uuid4()),
                        event_type=ev_type,
                        model_type=self.model_type,
                        confidence=conf,
                        risk_level=self._determine_risk_level(ev_type, conf),
                        detected_at=now,
                        metadata=features,
                    )
                )
            except ValueError:
                pass

        return signals

    def detect(
        self, audio_bytes: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> List[DetectionSignal]:
        """
        Phân tích mảng byte âm thanh thô.
        Decode WAV/PCM to mono 16 kHz and run YAMNet frame classification.
        """
        metadata = metadata or {}
        if not audio_bytes or len(audio_bytes) < 32:
            return []

        try:
            waveform = decode_waveform(audio_bytes, int(metadata.get("sample_rate", 16000)))
        except (ValueError, EOFError, OSError, wave.Error) as exc:
            raise ValueError("Invalid PCM/WAV audio input") from exc
        if waveform.size == 0:
            return []
        decibel = 20 * np.log10(max(float(np.sqrt(np.mean(waveform ** 2))), 1e-8))

        # A successful negative inference must never fall through to heuristics.
        if self._onnx_session is not None:
            try:
                if waveform.size < 15600:
                    waveform = np.pad(waveform, (0, 15600 - waveform.size))
                outputs = self._onnx_session.run(None, {"waveform": waveform})
                scores = outputs[0]  # shape: (frames, 521)

                # Với các sự kiện nguy cấp dạng xung lực ngắn (tiếng hét, súng nổ, nổ, kính vỡ):
                # Sử dụng max score của các frame để không bị làm loãng bởi các frame im lặng xung quanh

                onnx_signals: List[DetectionSignal] = []
                now = datetime.now(timezone.utc)

                # Quét các lớp nguy hiểm trong AUDIOSET_INDEX_MAPPING
                for class_idx, event_type in AUDIOSET_INDEX_MAPPING.items():
                    threshold = 0.30 if event_type in {AudioEventType.SCREAM, AudioEventType.GUNSHOT, AudioEventType.EXPLOSION} else 0.40
                    label_name = self._class_names.get(class_idx, f"AudioSet_{class_idx}")

                    if scores.shape[0] > 1:
                        frame_scores = scores[:, class_idx]
                        high_frames = [(i, float(s)) for i, s in enumerate(frame_scores) if s >= threshold]
                        if high_frames:
                            # Sắp xếp theo score giảm dần, lấy tối đa 3 frame mạnh nhất
                            high_frames.sort(key=lambda x: x[1], reverse=True)
                            for frame_i, sc in high_frames[:3]:
                                risk_lvl = self._determine_risk_level(event_type, sc)
                                onnx_signals.append(
                                    DetectionSignal(
                                        signal_id=str(uuid.uuid4()),
                                        event_type=event_type,
                                        model_type=self.model_type,
                                        confidence=round(sc, 4),
                                        risk_level=risk_lvl,
                                        start_offset_seconds=round(frame_i * 0.48, 2),
                                        end_offset_seconds=round((frame_i + 1) * 0.48, 2),
                                        detected_at=now,
                                        raw_labels={label_name: round(sc, 4)},
                                        metadata={
                                            "detector": self.name,
                                            "class_index": class_idx,
                                            "matched_label": label_name,
                                            "frame_index": frame_i,
                                            "decibel_peak": round(decibel, 2),
                                            "inference_engine": "ONNX Runtime",
                                        },
                                    )
                                )
                    else:
                        sc = float(scores[0, class_idx])
                        if sc >= threshold:
                            risk_lvl = self._determine_risk_level(event_type, sc)
                            onnx_signals.append(
                                DetectionSignal(
                                    signal_id=str(uuid.uuid4()),
                                    event_type=event_type,
                                    model_type=self.model_type,
                                    confidence=round(sc, 4),
                                    risk_level=risk_lvl,
                                    detected_at=now,
                                    raw_labels={label_name: round(sc, 4)},
                                    metadata={
                                        "detector": self.name,
                                        "class_index": class_idx,
                                        "matched_label": label_name,
                                        "decibel_peak": round(decibel, 2),
                                        "inference_engine": "ONNX Runtime",
                                    },
                                )
                            )

                onnx_signals.sort(key=lambda s: s.confidence, reverse=True)
                return onnx_signals

            except Exception as e:
                raise RuntimeError("YAMNet audio inference failed") from e

        # Loudness cannot identify a scream, gunshot or explosion.
        # Explicit preclassified labels remain supported for feature ingestion.
        if "raw_labels" in metadata:
            return self.detect_features(metadata)
        return []
