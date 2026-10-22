"""
=============================================================================
FILE: app/infrastructure/firestore/__init__.py
MODULE: Infrastructure - Firestore
ROLE / RESPONSIBILITY:
    - Package initialization cho module hạ tầng Firestore.
    - Export các client và helper khởi tạo Firestore.

CONNECTIONS / DEPENDENCIES:
    - app/infrastructure/firestore/client.py

INPUT / OUTPUT:
    - Expose get_firestore_client, init_firebase.
=============================================================================
"""

from app.infrastructure.firestore.client import get_firestore_client, init_firebase

__all__ = ["get_firestore_client", "init_firebase"]
