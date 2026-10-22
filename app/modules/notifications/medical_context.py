"""Build emergency notification fields from saved medical data, never inference."""
from app.shared.enums.user import MedicalPrivacyLevel


_EMPTY_VALUES = {'', 'unknown', 'không có', 'chưa cập nhật', 'none', 'n/a'}


def _text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value.casefold() not in _EMPTY_VALUES else None


def _items(value):
    values = value.split(',') if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)):
        return []
    return [text for item in values if (text := _text(item)) is not None]


def emergency_medical_fields(user, medical):
    """Honor sharing and explicit clears; fall back only for absent legacy fields."""
    privacy = medical.get('privacy_level', MedicalPrivacyLevel.EMERGENCY_SHARABLE.value)
    if privacy not in (MedicalPrivacyLevel.EMERGENCY_SHARABLE.value,
                       MedicalPrivacyLevel.LOCK_SCREEN_PUBLIC.value):
        return {}

    def value(field):
        return medical[field] if field in medical else user.get(field)

    return {
        'blood_type': _text(value('blood_type')),
        'allergies': _items(value('allergies')),
        'medications': _items(value('medications')),
        'chronic_conditions': _items(value('chronic_conditions')),
        'medical_notes': _text(value('medical_notes')),
    }
