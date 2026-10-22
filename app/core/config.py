"""
=============================================================================
FILE: app/core/config.py
MODULE: Core - Configuration
ROLE / RESPONSIBILITY:
    - Quản lý toàn bộ cấu hình hệ thống bằng Pydantic BaseSettings.
    - Tự động nạp biến môi trường từ file .env.
    - Tự động phát hiện file chứng thực Firebase Service Account trong app/config/.
    - Cấu hình thông số Cloudflare R2, Telegram Bot, CORS và chế độ runtime.

CONNECTIONS / DEPENDENCIES:
    - Đọc: file .env tại thư mục gốc backend.
    - Đọc: file *.json chứng thực Firebase trong app/config/.
    - Được gọi bởi: Toàn bộ các module trong backend thông qua `get_settings()`.

INPUT / OUTPUT:
    - Input: Environment variables, .env file, Firebase JSON credentials.
    - Output: Settings object (singleton) với type safety.
=============================================================================
"""

import glob
import os
from functools import lru_cache
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_default_firebase_credentials() -> str:
    """Tự động tìm kiếm file Service Account JSON trong app/config/ nếu không chỉ định rõ."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_dir = os.path.join(base_dir, "config")
    matches = glob.glob(os.path.join(config_dir, "*firebase-adminsdk*.json"))
    if not matches:
        matches = glob.glob(os.path.join(config_dir, "*.json"))
    return matches[0] if matches else ""


class Settings(BaseSettings):
    """Cấu hình ứng dụng tập trung."""
    model_config = SettingsConfigDict(
        env_file=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. Ứng dụng & Môi trường
    APP_NAME: str = "Guardian AI Backend"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"
    JWT_SECRET: str = "guardian-ai-secure-jwt-secret-key-2026-production-min32bytes"
    JWT_ALGORITHM: str = "HS256"

    # 2. CORS Origins
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    @field_validator("DEBUG", mode="before")
    @classmethod
    def assemble_debug(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes", "debug", "dev", "development")
        return bool(v)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # 3. Firebase Credentials & Firestore
    FIREBASE_CREDENTIALS_PATH: str = Field(default_factory=_find_default_firebase_credentials)
    FIREBASE_CREDENTIALS_JSON: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_WEB_API_KEY: str = "AIzaSyCnsRihZcg25Ey1YmxSg9kVw-xn-SJvTsw"

    # 4. Cloudflare R2 Object Storage
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_BUCKET: str = "guardian-ai-audio"
    R2_PUBLIC_URL: str = ""

    @property
    def r2_endpoint_url(self) -> str:
        """Endpoint S3 API của Cloudflare R2 dựa trên Account ID."""
        if self.R2_ACCOUNT_ID:
            return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return ""

    # 5. Telegram Bot API
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_API_BASE_URL: str = "https://api.telegram.org"

    # 6. Safety Check & Emergency Thresholds (Configurable theo ADR-009, ADR-031)
    DEFAULT_SAFETY_CHECK_GRACE_PERIOD_SECONDS: int = 60
    MAX_SAFETY_CHECK_EXTENSIONS: int = 3
    SCHEDULER_INTERVAL_SECONDS: int = 30

    # 7. AI Audio Detection & Decision Engine (ADR-009, ADR-010, ADR-011)
    DETECTION_COOLDOWN_SECONDS: int = 30          # Cooldown giữa các lần trigger khẩn cấp
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.80  # Ngưỡng tin cậy tổng thể 80%
    DETECTION_WINDOW_SECONDS: float = 4.0         # Cửa sổ phân tích trượt 4s
    DETECTION_MIN_CONSECUTIVE_FRAMES: int = 2     # Yêu cầu ít nhất 2 frame liên tiếp phát hiện
    DETECTION_EMERGENCY_RISK_THRESHOLD: float = 0.80

    # 8. Business Limits & Cost Optimization (Startup Safeguards - ADR-036)
    MAX_EMERGENCY_CONTACTS_PER_USER: int = 10
    MAX_WATCHERS_PER_USER: int = 10

    # 9. Audio Clip Recording & Upload (ADR-New)
    CLIP_MAX_PRE_ROLL_SECONDS: float = 5.0
    CLIP_MAX_POST_ROLL_SECONDS: float = 5.0
    CLIP_MAX_TOTAL_DURATION_SECONDS: float = 15.0
    CLIP_MAX_CLIPS_PER_SESSION: int = 3
    CLIP_MAX_PENDING_UPLOADS: int = 2
    CLIP_MAX_PENDING_BYTES: int = 20 * 1024 * 1024  # 20MB
    CLIP_RETRY_MAX_ATTEMPTS: int = 3
    CLIP_RETRY_BACKOFF_BASE_SECONDS: float = 2.0
    CLIP_IDEMPOTENCY_WINDOW_SECONDS: int = 300  # 5 minutes


@lru_cache()
def get_settings() -> Settings:
    """Trả về instance singleton Settings được cache."""
    return Settings()
