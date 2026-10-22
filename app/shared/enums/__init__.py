"""
=============================================================================
FILE: app/shared/enums/__init__.py
MODULE: Shared - Enums Package
ROLE / RESPONSIBILITY:
    - Re-export toàn bộ Enums chuẩn hóa của hệ thống Guardian AI.

CONNECTIONS / DEPENDENCIES:
    - app/shared/enums/detection.py
    - app/shared/enums/emergency.py
    - app/shared/enums/safety_check.py
    - app/shared/enums/user.py
    - app/shared/enums/contact.py

INPUT / OUTPUT:
    - Expose tất cả Enums domain.
=============================================================================
"""

from app.shared.enums.contact import ContactRelationship, NotificationChannel
from app.shared.enums.detection import AudioEventType, DetectionRiskLevel, DetectorModelType
from app.shared.enums.emergency import EmergencySeverity, EmergencyStatus, EmergencyTriggerType
from app.shared.enums.safety_check import DefaultTemplateId, SafetyCheckStatus
from app.shared.enums.user import BloodType, MedicalPrivacyLevel

__all__ = [
    "AudioEventType",
    "DetectorModelType",
    "DetectionRiskLevel",
    "EmergencyStatus",
    "EmergencyTriggerType",
    "EmergencySeverity",
    "SafetyCheckStatus",
    "DefaultTemplateId",
    "BloodType",
    "MedicalPrivacyLevel",
    "ContactRelationship",
    "NotificationChannel",
]
