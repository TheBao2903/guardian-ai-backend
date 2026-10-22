"""
=============================================================================
FILE: app/modules/detection/detectors/__init__.py
MODULE: Detection Detectors Package
ROLE / RESPONSIBILITY:
    - Khởi tạo package cho các bộ phân loại âm thanh (Audio Detectors).
    - Cung cấp interface trừu tượng và các detector: YAMNetDetector, VocalBurstDetector.

CONNECTIONS / DEPENDENCIES:
    - app/modules/detection/detectors/base.py
    - app/modules/detection/detectors/yamnet_detector.py
    - app/modules/detection/detectors/vocal_burst_detector.py

INPUT / OUTPUT:
    - Export các lớp detector.
=============================================================================
"""

from app.modules.detection.detectors.base import BaseAudioDetector
from app.modules.detection.detectors.vocal_burst_detector import VocalBurstDetector
from app.modules.detection.detectors.yamnet_detector import YAMNetDetector

__all__ = ["BaseAudioDetector", "YAMNetDetector", "VocalBurstDetector"]
