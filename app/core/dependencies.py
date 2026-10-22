"""
=============================================================================
FILE: app/core/dependencies.py
MODULE: Core - Common Dependencies
ROLE / RESPONSIBILITY:
    - Cung cấp các Dependency Injection cơ sở cho FastAPI routers.
    - Cung cấp singleton Settings, Firestore Client và R2 Storage Client.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/infrastructure/firestore/client.py (get_firestore_client)
    - app/infrastructure/storage/r2/client.py (get_r2_client)
    - Được gọi bởi: Toàn bộ router và service trong backend thông qua `Depends()`.

INPUT / OUTPUT:
    - Output: Settings, FirestoreClient, R2StorageClient instances.
=============================================================================
"""

from fastapi import Depends
from google.cloud.firestore import Client as FirestoreClient

from app.core.config import Settings, get_settings
from app.infrastructure.firestore.client import get_firestore_client
from app.infrastructure.storage.r2.client import R2StorageClient, get_r2_client


def get_app_settings() -> Settings:
    """Dependency cung cấp Application Settings."""
    return get_settings()


def get_db() -> FirestoreClient:
    """Dependency cung cấp Firestore Database Client."""
    return get_firestore_client()


def get_r2_storage() -> R2StorageClient:
    """Dependency cung cấp Cloudflare R2 Client."""
    return get_r2_client()
