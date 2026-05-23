from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel


class FrameSource(StrEnum):
    LATEST = "latest"
    LOOK = "look"
    FIXTURE = "fixture"
    UNKNOWN = "unknown"


class FrameMetadata(BaseModel):
    frame_id: str
    captured_at: datetime
    width: int
    height: int
    jpeg_bytes: bytes
    is_pinned: bool = False
    pin_expires_at: datetime | None = None
    used_for_analysis: bool = False
    source: FrameSource = FrameSource.UNKNOWN

    def age_ms(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        return max(0, int((current - self.captured_at).total_seconds() * 1000))


class FrameUnavailable(BaseModel):
    status: str = "unavailable"
    visual_status: str
    message: str
