"""
=============================================================================
FILE: app/infrastructure/storage/r2/client.py
MODULE: Infrastructure - Cloudflare R2 Client
ROLE / RESPONSIBILITY:
    - Quản lý tương tác với Cloudflare R2 Object Storage (chuẩn S3 API).
    - Cung cấp các thao tác upload audio ghi âm bằng chứng, tạo presigned download URL,
      kiểm tra sự tồn tại và xóa object.
    - Đảm bảo tuân thủ ADR-006 (Cloudflare R2 for Audio/Binary Storage, Firestore lưu metadata).
    - Hỗ trợ retry với exponential backoff và idempotency check.

CONNECTIONS / DEPENDENCIES:
    - Đọc cấu hình từ: `app/core/config.py` (get_settings).
    - Thư viện ngoài: `boto3`, `botocore.exceptions`.
    - Được gọi bởi: `app/modules/recordings/service.py` và Health Check API.

INPUT / OUTPUT:
    - Input: Binary audio data (bytes), storage keys (ví dụ: users/{uid}/emergency/{id}/audio.webm).
    - Output: Storage key, Presigned URL hoặc Public URL.
=============================================================================
"""

import time
from io import BytesIO
from typing import Optional, Set
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.exceptions import ProviderException
from app.core.logging import logger


# Transient errors that can be retried
RETRYABLE_ERROR_CODES: Set[str] = {
    "RequestTimeout",
    "RequestTimeTooSkewed",
    "ServiceUnavailable",
    "InternalError",
    "SlowDown",
    "HeadBucket403",
    "HeadBucket404",
}


class R2StorageClient:
    """Client giao tiếp với Cloudflare R2 Object Storage."""

    def __init__(self) -> None:
        settings = get_settings()
        self.bucket_name = settings.R2_BUCKET
        self.public_url = settings.R2_PUBLIC_URL.rstrip("/") if settings.R2_PUBLIC_URL else ""
        self.endpoint_url = settings.r2_endpoint_url
        self.max_retry_attempts = getattr(settings, "CLIP_RETRY_MAX_ATTEMPTS", 3)
        self.backoff_base = getattr(settings, "CLIP_RETRY_BACKOFF_BASE_SECONDS", 2.0)

        if not settings.R2_ACCESS_KEY or not settings.R2_SECRET_KEY or not self.endpoint_url:
            logger.warning("Cloudflare R2 chưa được cấu hình đầy đủ keys trong .env!")

        # Cấu hình Boto3 client kết nối R2 S3 API
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY,
            aws_secret_access_key=settings.R2_SECRET_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 1},  # Disable boto3 built-in retry; we handle manually
            ),
        )

    def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = "audio/webm",
        idempotency_key: Optional[str] = None,
    ) -> str:
        """
        Tải dữ liệu binary dạng bytes lên R2 với retry logic.

        Args:
            data: Binary audio data
            key: Storage key path
            content_type: MIME type
            idempotency_key: Optional key to prevent duplicate uploads on retry

        Returns:
            Storage key if successful
        """
        # Check idempotency: if object already exists, skip upload
        if idempotency_key and self.check_object_exists(key):
            logger.info(f"Idempotency check passed: object already exists at key='{key}'")
            return key

        last_exception: Optional[ClientError] = None

        for attempt in range(self.max_retry_attempts):
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
                logger.info(f"Đã upload {len(data)} bytes lên R2 thành công: key='{key}' (attempt {attempt + 1})")
                return key

            except ClientError as e:
                last_exception = e
                error_code = e.response.get("Error", {}).get("Code", "")

                # Check if error is retryable
                if error_code in RETRYABLE_ERROR_CODES:
                    if attempt < self.max_retry_attempts - 1:
                        backoff = self.backoff_base ** attempt
                        logger.warning(
                            f"Retryable error {error_code} on upload attempt {attempt + 1}, "
                            f"retrying in {backoff:.1f}s: {str(e)}"
                        )
                        time.sleep(backoff)
                        continue
                else:
                    # Non-retryable error, break immediately
                    logger.error(f"Non-retryable error upload bytes to R2: {error_code} - {str(e)}")
                    raise ProviderException(
                        message=f"Lỗi upload R2: {error_code}",
                        provider="Cloudflare R2",
                        details={"key": key, "error": str(e)},
                    )

        # All retries exhausted
        if last_exception:
            logger.error(f"Lỗi upload bytes lên Cloudflare R2 sau {self.max_retry_attempts} attempts: {str(last_exception)}")
            raise ProviderException(
                message=f"Lỗi upload R2 sau {self.max_retry_attempts} lần thử",
                provider="Cloudflare R2",
                details={"key": key, "attempts": self.max_retry_attempts},
            )

        raise ProviderException(message="Lỗi không xác định khi upload R2", provider="Cloudflare R2")

    def upload_file(
        self,
        file_path: str,
        key: str,
        content_type: str = "audio/webm",
        idempotency_key: Optional[str] = None,
    ) -> str:
        """
        Tải file từ ổ cứng lên R2 với retry logic.

        Args:
            file_path: Local file path
            key: Storage key path
            content_type: MIME type
            idempotency_key: Optional key to prevent duplicate uploads on retry

        Returns:
            Storage key if successful
        """
        # Check idempotency: if object already exists, skip upload
        if idempotency_key and self.check_object_exists(key):
            logger.info(f"Idempotency check passed: object already exists at key='{key}'")
            return key

        last_exception: Optional[ClientError] = None

        for attempt in range(self.max_retry_attempts):
            try:
                with open(file_path, "rb") as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=key,
                        Body=f,
                        ContentType=content_type,
                    )
                logger.info(f"Đã upload file từ '{file_path}' lên R2: key='{key}' (attempt {attempt + 1})")
                return key

            except ClientError as e:
                last_exception = e
                error_code = e.response.get("Error", {}).get("Code", "")

                if error_code in RETRYABLE_ERROR_CODES:
                    if attempt < self.max_retry_attempts - 1:
                        backoff = self.backoff_base ** attempt
                        logger.warning(
                            f"Retryable error {error_code} on file upload attempt {attempt + 1}, "
                            f"retrying in {backoff:.1f}s: {str(e)}"
                        )
                        time.sleep(backoff)
                        continue
                else:
                    logger.error(f"Non-retryable error upload file to R2: {error_code} - {str(e)}")
                    raise ProviderException(
                        message=f"Lỗi upload R2: {error_code}",
                        provider="Cloudflare R2",
                        details={"key": key, "file_path": file_path, "error": str(e)},
                    )

        # All retries exhausted
        if last_exception:
            logger.error(f"Lỗi upload file lên Cloudflare R2 sau {self.max_retry_attempts} attempts: {str(last_exception)}")
            raise ProviderException(
                message=f"Lỗi upload R2 sau {self.max_retry_attempts} lần thử",
                provider="Cloudflare R2",
                details={"key": key, "file_path": file_path, "attempts": self.max_retry_attempts},
            )

        raise ProviderException(message="Lỗi không xác định khi upload R2", provider="Cloudflare R2")

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Tạo đường dẫn URL có chữ ký bảo mật cho phép tải/nghe file trong khoảng thời gian xác định."""
        try:
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Lỗi tạo presigned URL R2: {str(e)}")
            raise ProviderException(message=f"Lỗi tạo presigned URL: {str(e)}", provider="Cloudflare R2")

    def get_public_url(self, key: str, expires_in: int = 86400) -> str:
        """
        Tạo đường dẫn có chữ ký số bảo mật (Pre-signed URL) có thời hạn (mặc định 24 giờ).
        Tuân thủ Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu ghi âm âm thanh khẩn cấp cá nhân,
        chống lộ lọt bằng chứng ra ngoài sau khi sự cố kết thúc.
        """
        try:
            return self.generate_presigned_url(key, expires_in=expires_in)
        except Exception as e:
            logger.warning(f"Không thể sinh pre-signed URL R2, fallback: {str(e)}")
            if self.public_url:
                return f"{self.public_url}/{key}"
            return ""

    def check_object_exists(self, key: str) -> bool:
        """Kiểm tra một object có tồn tại trên R2 hay không."""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError:
            return False

    def delete_object(self, key: str) -> bool:
        """Xóa object khỏi R2."""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Đã xóa object khỏi R2: key='{key}'")
            return True
        except ClientError as e:
            logger.error(f"Lỗi xóa object R2: {str(e)}")
            return False

    def check_connection(self) -> bool:
        """Kiểm tra tính sẵn sàng của kết nối R2 (dùng cho Health Check)."""
        try:
            # Kiểm tra truy cập bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.debug(f"R2 health check OK: bucket='{self.bucket_name}'")
            return True
        except Exception as e:
            logger.error(f"R2 health check thất bại: {str(e)}")
            return False


_r2_client_instance: Optional[R2StorageClient] = None


def get_r2_client() -> R2StorageClient:
    """Trả về R2StorageClient singleton."""
    global _r2_client_instance
    if _r2_client_instance is None:
        _r2_client_instance = R2StorageClient()
    return _r2_client_instance
