from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    ENDED = "ended"


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: f"sess_{uuid4().hex}")
    app_instance_id: str | None = None
    livekit_room_name: str
    created_at: datetime = Field(default_factory=utc_now)
    last_activity_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE
    debug_enabled: bool = False
    memory: dict = Field(default_factory=dict)
    active_livekit_participants: list[str] = Field(default_factory=list)
