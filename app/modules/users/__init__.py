"""
=============================================================================
FILE: app/modules/users/__init__.py
MODULE: Users Package
ROLE / RESPONSIBILITY:
    - Đánh dấu thư mục users là Python package.
    - Export users router.

CONNECTIONS / DEPENDENCIES:
    - app/modules/users/router.py

INPUT / OUTPUT:
    - Re-export users_router.
=============================================================================
"""

from app.modules.users.router import router as users_router

__all__ = ["users_router"]
