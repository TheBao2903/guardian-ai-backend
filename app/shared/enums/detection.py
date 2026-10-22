"""
=============================================================================
FILE: app/shared/enums/detection.py
MODULE: Shared - Detection Enums
ROLE / RESPONSIBILITY:
    - Định nghĩa các loại sự kiện âm thanh bất thường và nguy hiểm được phát hiện bởi AI.
    - Định nghĩa các loại model AI nhận diện âm thanh trong hệ thống (YAMNet, VocalBurst, Whisper).
    - Định nghĩa các cấp độ rủi ro (Risk Level) để phục vụ Temporal Aggregation & Decision Layer.
    - Đảm bảo tuân thủ ADR-009, ADR-010, ADR-011.

CONNECTIONS / DEPENDENCIES:
    - Được sử dụng bởi: `app/modules/detection/`, `app/modules/emergency/`,
      các Schemas và Repositories.

INPUT / OUTPUT:
    - Enums: AudioEventType, DetectorModelType, DetectionRiskLevel.
=============================================================================
"""

from enum import Enum


class AudioEventType(str, Enum):
    """Các loại âm thanh bất thường / nguy hiểm được phân loại bởi các model AI."""
    # Nhóm 1: Tiếng phát ra từ thanh quản con người (Vocal Distress - Model VocalBurst & YAMNet)
    SCREAM = "SCREAM"                           # Tiếng la hét hoảng loạn, thét kinh hoàng
    DISTRESS_CRY = "DISTRESS_CRY"               # Tiếng khóc thét, rên rỉ đau đớn
    CALL_FOR_HELP = "CALL_FOR_HELP"             # Tiếng kêu cứu khẩn cấp ("Cứu tôi với", "Help me")

    # Nhóm 2: Âm thanh bạo lực / đột nhập / vũ khí (Violence & Intrusion - Model YAMNet)
    GLASS_SHATTER = "GLASS_SHATTER"             # Tiếng đập vỡ kính, vỡ cửa kính đột nhập
    GUNSHOT = "GUNSHOT"                         # Tiếng súng nổ
    EXPLOSION = "EXPLOSION"                     # Tiếng nổ lớn bất thường
    VIOLENT_STRUGGLE = "VIOLENT_STRUGGLE"       # Tiếng ẩu đả, va đập đồ đạc, giằng co dữ dội

    # Nhóm 3: Mối đe dọa môi trường & tai nạn (Accident & Threat - Model YAMNet)
    AGGRESSIVE_BARK = "AGGRESSIVE_BARK"         # Tiếng chó dữ gầm gừ, sủa hung hãn tấn công
    CAR_CRASH_SOUND = "CAR_CRASH_SOUND"         # Tiếng rít phanh gấp, va chạm giao thông lớn
    ENVIRONMENTAL_ALARM = "ENVIRONMENTAL_ALARM" # Tiếng còi báo cháy, báo động xung quanh

    # Nhóm 4: Âm thanh bất thường chưa rõ loại
    ABNORMAL_UNKNOWN = "ABNORMAL_UNKNOWN"       # Âm thanh vượt ngưỡng decibel bất thường nhưng chưa phân loại


class DetectorModelType(str, Enum):
    """Các loại AI model phụ trách nhận diện âm thanh trong hệ thống."""
    YAMNET = "YAMNET"                           # Google YAMNet: General Audio Event Classifier
    VOCAL_BURST = "VOCAL_BURST"                 # VocalBurst Locator: Chuyên nhận diện tiếng hét và distress
    FASTER_WHISPER = "FASTER_WHISPER"           # Faster-Whisper: Nhận diện từ khóa cầu cứu bằng giọng nói
    CUSTOM_ENSEMBLE = "CUSTOM_ENSEMBLE"         # Bộ kết hợp đa model (Ensemble)


class DetectionRiskLevel(str, Enum):
    """Cấp độ rủi ro đánh giá sau khi tổng hợp các khung âm thanh (Temporal Aggregation)."""
    NEGLIGIBLE = "NEGLIGIBLE"                   # Không đáng kể (Confidence thấp hoặc âm thanh thoáng qua)
    SUSPICIOUS = "SUSPICIOUS"                   # Đáng ngờ (Bắt đầu theo dõi và tăng tần suất lấy mẫu)
    WARNING = "WARNING"                         # Cảnh báo (Hiển thị nhắc nhở xác nhận trên màn hình máy)
    EMERGENCY = "EMERGENCY"                     # Nguy cấp (Kích hoạt Emergency Workflow thông báo người thân)
