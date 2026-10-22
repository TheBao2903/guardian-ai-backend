"""
=============================================================================
FILE: app/infrastructure/storage/r2/__init__.py
MODULE: Infrastructure - Cloudflare R2
ROLE / RESPONSIBILITY:
    - Package initialization cho Cloudflare R2 Client.
    - Export R2StorageClient và helper lấy instance.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/storage/r2/client.py

INPUT / OUTPUT:
    - Expose R2StorageClient, get_r2_client.
=============================================================================
"""

from app.infrastructure.storage.r2.client import R2StorageClient, get_r2_client

__all__ = ["R2StorageClient", "get_r2_client"]
