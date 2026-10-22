"""
=============================================================================
FILE: app/core/logging.py
MODULE: Core - Logging & Data Sanitization
ROLE / RESPONSIBILITY:
    - Thiết lập hệ thống logging tập trung cho Guardian AI backend.
    - Cung cấp bộ lọc SensitiveDataFilter để tự động che giấu (redact/mask)
      các dữ liệu nhạy cảm: Firebase Tokens, Passwords, Headers bí mật, Medical data.
    - Đảm bảo tuân thủ nguyên tắc Privacy Rule trong CONVENTIONS.md.

CONNECTIONS / DEPENDENCIES:
    - Sử dụng: Python standard library `logging`.
    - Được gọi bởi: Toàn bộ các service, router, scheduler trong backend.

INPUT / OUTPUT:
    - Input: Log records từ mọi nơi trong app.
    - Output: Formatted & sanitized log output ra console/file.
=============================================================================
"""

import logging
import re
import sys
from typing import Any

# Các từ khóa nhạy cảm cần lọc
SENSITIVE_PATTERNS = [
    (re.compile(r'(Bearer\s+)[A-Za-z0-9_\-\.]+', re.IGNORECASE), r'\1[REDACTED_TOKEN]'),
    (re.compile(r'("?(?:password|secret|access_key|secret_key|token)"?\s*[:=]\s*")[^",\s]+(")', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'("?(?:password|secret|access_key|secret_key|token)"?\s*[:=]\s*)[^\'",\s{}]+', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'("?(?:medical_notes|allergies|conditions)"?\s*[:=]\s*"?[^"]+"?)', re.IGNORECASE), r'"medical_data":[REDACTED]'),
]



class SensitiveDataFilter(logging.Filter):
    """Bộ lọc tự động che giấu thông tin nhạy cảm trong log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in SENSITIVE_PATTERNS:
                record.msg = pattern.sub(repl, record.msg)
        return True


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Khởi tạo và cấu hình logging cho toàn ứng dụng."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Định dạng log
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Handler xuất ra stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Tránh duplicate handler khi reload
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers = [handler]

    # Logger riêng cho Guardian AI
    app_logger = logging.getLogger("guardian_ai")
    app_logger.setLevel(level)

    # Giảm ồn từ các thư viện ngoài
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)

    return app_logger


# Logger mặc định dùng trong toàn bộ app
logger = logging.getLogger("guardian_ai")
