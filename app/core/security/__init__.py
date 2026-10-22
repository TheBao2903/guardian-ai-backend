"""
=============================================================================
PACKAGE: app.core.security
MODULE: Security utilities
ROLE / RESPONSIBILITY:
    - Cung cấp các helper bảo mật cho hệ thống:
      + PinHasher: Hash & verify mã PIN 4 số bằng bcrypt.
      + (Mở rộng: JWT, rate limit, encryption sau).

CONNECTIONS / DEPENDENCIES:
    - bcrypt library (pip install bcrypt==4.1.2)
=============================================================================
"""

from app.core.security.pin_hasher import PinHasher

__all__ = ["PinHasher"]
