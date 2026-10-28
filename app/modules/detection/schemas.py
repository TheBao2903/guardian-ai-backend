"""
=============================================================================
FILE: app/modules/detection/schemas.py
MODULE: Detection - Schemas & DTOs
ROLE / RESPONSIBILITY:
    - Định nghĩa DTO cho việc tiếp nhận tín hiệu nhận diện âm thanh (Signals Ingestion),
      phân tích âm thanh thô (Raw Audio Analysis), và kết quả thẩm định rủi ro (Risk Decision).
    - Hỗ trợ chuẩn hóa dữ liệu từ cả Edge Client AI (On-device YAMNet / VocalBurst)
      lẫn Server-side Audio Analysis.
    - Tuân thủ ADR-009 (Tách biệt phát hiện âm thanh khỏi quyết định khẩn cấp),
      ADR-010 (Chống false positive bằng Temporal Aggregation), ADR-011.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/detection.py (AudioEventType, DetectorModelType, DetectionRiskLevel)
    - app/shared/schemas/detection_signal.py (DetectionSignal)
    - app/shared/schemas/location.py (GeoPointSchema)
    - Sử dụng bởi: `app/modules/detection/router.py`, `service.py`, `decision/`.

INPUT / OUTPUT:
    - DTOs: DetectionSignalIngestRequest, AudioAnalyzeRequest, RiskDecisionResult,
            DetectionIngestResponse, DetectionConfigResponse, DetectionEventRecordResponse.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from app.modules.detection.alerts.schemas import AlertResponse

from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType
from app.shared.schemas.detection_signal import DetectionSignal
from app.shared.schemas.location import GeoPointSchema, OptionalCoordinatesRequest


class DetectionSignalInput(BaseModel):
    """Một tín hiệu nhận diện âm thanh đơn lẻ được gửi từ Client/Edge AI."""
    event_type: AudioEventType = Field(
        ...,
        description="Loại sự kiện âm thanh phát hiện (SCREAM, DISTRESS_CRY, GUNSHOT...)",
    )
    model_type: DetectorModelType = Field(
        default=DetectorModelType.YAMNET,
        description="Model AI thực hiện phát hiện",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của phát hiện (0.0 đến 1.0)",
    )
    start_offset_seconds: float = Field(0.0, ge=0.0, description="Thời điểm bắt đầu trong đoạn âm thanh")
    end_offset_seconds: float = Field(0.0, ge=0.0, description="Thời điểm kết thúc trong đoạn âm thanh")
    decibel_peak: Optional[float] = Field(None, description="Cường độ âm thanh đỉnh (dB)")
    raw_labels: Optional[Dict[str, float]] = Field(None, description="Điểm số thô của các nhãn mô hình")


class DetectionSignalIngestRequest(OptionalCoordinatesRequest):
    """Payload tiếp nhận danh sách các tín hiệu âm thanh từ Client/Edge AI."""
    signals: List[DetectionSignalInput] = Field(
        ...,
        min_length=1,
        description="Danh sách các frame tín hiệu phát hiện được",
    )
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Vĩ độ GPS hiện tại")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Kinh độ GPS hiện tại")
    accuracy_meters: Optional[float] = Field(None, ge=0.0, description="Độ chính xác GPS (m)")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Phần trăm pin thiết bị")
    notes: Optional[str] = Field(None, max_length=500, description="Ghi chú thêm từ client")


class AudioAnalyzeRequest(OptionalCoordinatesRequest):
    model_config = ConfigDict(allow_inf_nan=False)
    monitoring_session_id: str | None = Field(None, min_length=1, max_length=100)
    window_end_sample: int = Field(0, ge=0)
    captured_at: datetime | None = None
    safety_check_instance_id: str | None = Field(None, max_length=100, pattern=r'^[^/]+$')
    """Payload gửi đoạn âm thanh thô hoặc đặc trưng để Backend AI phân tích."""
    audio_base64: Optional[str] = Field(
        None,
        max_length=1500000,
        description="Chuỗi base64 của file âm thanh ngắn (WAV/PCM 16kHz mono)",
    )
    sample_rate: int = Field(16000, ge=8000, le=48000, description="Tần số lấy mẫu âm thanh (Hz)")
    decibel_peak: Optional[float] = Field(None, description="Cường độ âm thanh đỉnh đo được tại client (dB)")
    features: Optional[Dict[str, Any]] = Field(None, description="Đặc trưng âm thanh trích xuất trước (nếu có)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Vĩ độ GPS hiện tại")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Kinh độ GPS hiện tại")
    accuracy_meters: Optional[float] = Field(None, ge=0.0, description="Độ chính xác GPS (m)")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Phần trăm pin thiết bị")
    session_id: Optional[str] = Field(None, description="Mã phiên SOS khẩn cấp liên kết")


class RiskDecisionResult(BaseModel):
    """Kết quả thẩm định rủi ro từ Risk Decision Engine."""
    risk_level: DetectionRiskLevel = Field(..., description="Cấp độ rủi ro đánh giá (NEGLIGIBLE đến EMERGENCY)")
    is_emergency: bool = Field(False, description="True nếu vượt ngưỡng nguy cấp cần kích hoạt SOS")
    aggregated_confidence: float = Field(..., ge=0.0, le=1.0, description="Độ tin cậy tổng hợp trong cửa sổ trượt")
    primary_event_type: Optional[AudioEventType] = Field(None, description="Loại sự kiện âm thanh chủ đạo")
    consecutive_detections: int = Field(0, description="Số frame phát hiện liên tiếp đạt ngưỡng")
    temporal_consistency_score: float = Field(0.0, ge=0.0, le=1.0, description="Độ bền vững theo thời gian")
    reason: str = Field(..., description="Giải thích lý do đưa ra quyết định thẩm định rủi ro")


class DetectionIngestResponse(BaseModel):
    alert: AlertResponse | None = None
    """Kết quả trả về cho Client sau khi xử lý tín hiệu âm thanh."""
    signals_processed: int = Field(..., description="Số lượng tín hiệu đã tiếp nhận và phân tích")
    risk_level: DetectionRiskLevel = Field(..., description="Cấp độ rủi ro hiện tại")
    is_emergency: bool = Field(..., description="Đạt ngưỡng khẩn cấp hay không")
    emergency_triggered: bool = Field(False, description="Phiên SOS thực sự đã được kích hoạt hay chưa")
    session_id: Optional[str] = Field(None, description="Mã phiên SOS khẩn cấp nếu có kích hoạt")
    cooldown_active: bool = Field(False, description="True nếu đang trong thời gian giãn cách (Cooldown)")
    cooldown_remaining_seconds: int = Field(0, description="Số giây cooldown còn lại nếu có")
    message: str = Field(..., description="Thông báo kết quả phân tích")
    signals: List[DetectionSignal] = Field(default_factory=list, description="Danh sách signals đã chuẩn hóa")


class DetectionConfigResponse(BaseModel):
    """Các thông số cấu hình và ngưỡng quyết định hiện tại của Decision Engine."""
    confidence_threshold: float = Field(..., description="Ngưỡng tin cậy tối thiểu cho 1 frame")
    window_seconds: float = Field(..., description="Độ rộng cửa sổ tổng hợp thời gian (giây)")
    min_consecutive_frames: int = Field(..., description="Số frame liên tiếp tối thiểu để xác nhận")
    emergency_risk_threshold: float = Field(..., description="Ngưỡng điểm tin cậy tổng hợp để coi là Khẩn cấp")
    cooldown_seconds: int = Field(..., description="Thời gian giãn cách chống bão báo động (giây)")
    active_detectors: List[str] = Field(..., description="Danh sách các detector model đang sẵn sàng")


class DetectionEventRecordResponse(BaseModel):
    """Bản ghi sự kiện phát hiện âm thanh trong lịch sử lưu trữ."""
    event_id: str = Field(..., description="ID sự kiện lưu trữ")
    user_id: str = Field(..., description="ID người dùng")
    event_type: AudioEventType = Field(..., description="Loại sự kiện âm thanh")
    risk_level: DetectionRiskLevel = Field(..., description="Cấp độ rủi ro")
    confidence: float = Field(..., description="Độ tin cậy")
    emergency_triggered: bool = Field(..., description="Đã kích hoạt SOS hay chưa")
    session_id: Optional[str] = Field(None, description="Mã phiên SOS nếu có")
    location: Optional[GeoPointSchema] = Field(None, description="Tọa độ GPS ghi nhận")
    created_at: Any = Field(..., description="Thời điểm ghi nhận")
