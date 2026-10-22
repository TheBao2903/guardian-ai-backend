"""
=============================================================================
FILE: app/modules/detection/detectors/base.py
MODULE: Detection - Base Audio Detector Interface
ROLE / RESPONSIBILITY:
    - Định nghĩa lớp cơ sở trừu tượng (Abstract Base Class) cho tất cả các AI Model phân loại âm thanh.
    - Cung cấp interface thống nhất cho việc phân tích âm thanh thô hoặc đặc trưng (Features).
    - Chuẩn hóa kết quả đầu ra thành danh sách các `DetectionSignal` độc lập.
    - Tuân thủ ADR-009, ADR-022.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/detection.py (AudioEventType, DetectorModelType, DetectionRiskLevel)
    - app/shared/schemas/detection_signal.py (DetectionSignal)
    - Kế thừa bởi: `YAMNetDetector`, `VocalBurstDetector`.

INPUT / OUTPUT:
    - Input: audio_bytes hoặc dictionary features.
    - Output: List[DetectionSignal].
=============================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.shared.enums.detection import DetectorModelType
from app.shared.schemas.detection_signal import DetectionSignal


class BaseAudioDetector(ABC):
    """Giao diện trừu tượng cho tất cả các mô hình phân loại âm thanh bất thường."""

    def __init__(self, model_type: DetectorModelType, name: str) -> None:
        self.model_type = model_type
        self.name = name

    @abstractmethod
    def is_available(self) -> bool:
        """Kiểm tra mô hình đã sẵn sàng hoạt động hay chưa."""
        pass

    @abstractmethod
    def detect(
        self, audio_bytes: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> List[DetectionSignal]:
        """
        Phân tích mảng byte âm thanh thô và trả về danh sách tín hiệu phát hiện được.
        """
        pass

    @abstractmethod
    def detect_features(
        self, features: Dict[str, Any]
    ) -> List[DetectionSignal]:
        """
        Phân tích dựa trên các đặc trưng âm thanh được trích xuất sẵn từ client/edge.
        """
        pass
