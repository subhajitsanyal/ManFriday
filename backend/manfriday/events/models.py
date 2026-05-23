from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    type: str
    session_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict
