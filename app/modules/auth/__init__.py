"""
=============================================================================
FILE: app/modules/auth/__init__.py
MODULE: Auth Package
ROLE / RESPONSIBILITY:
    - Đánh dấu thư mục auth là Python package.
    - Export auth router và dependency xác thực get_current_user.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/router.py
    - app/modules/auth/dependencies.py

INPUT / OUTPUT:
    - Re-export auth_router, get_current_user.
=============================================================================
"""

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.router import router as auth_router

__all__ = ["auth_router", "get_current_user"]
