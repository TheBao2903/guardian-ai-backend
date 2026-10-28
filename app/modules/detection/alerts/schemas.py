from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.shared.schemas.location import OptionalCoordinatesRequest


class AlertCandidate(OptionalCoordinatesRequest):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    monitoring_session_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)
    event_type: Literal['SCREAM'] = 'SCREAM'
    confidence: float = Field(ge=0.3, le=1)
    captured_at: datetime
    safety_check_instance_id: str | None = Field(None, max_length=100, pattern=r'^[^/]+$')
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class DeliverySummary(BaseModel):
    total: int = 0
    sent: int = 0
    pending: int = 0
    failed: int = 0
    uncertain: int = 0
    status: str = 'NOT_STARTED'


class AlertResponse(BaseModel):
    alert_id: str
    status: Literal['PENDING', 'CANCELLED', 'DISPATCHING', 'SOS_CREATED']
    created_at: datetime
    deadline_at: datetime
    server_time: datetime
    emergency_session_id: str | None = None
    delivery: DeliverySummary = Field(default_factory=DeliverySummary)
