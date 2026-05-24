from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class GoProState(StrEnum):
    UNKNOWN = "unknown"
    CREDENTIALS_MISSING = "credentials_missing"
    RECONFIGURE_REQUIRED = "reconfigure_required"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PREVIEW_STARTING = "preview_starting"
    PREVIEW_RUNNING = "preview_running"
    PREVIEW_STOPPED = "preview_stopped"
    UNREACHABLE = "unreachable"
    DEGRADED = "degraded"
    ERROR = "error"


class VisualState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class GoProReconfigureState(StrEnum):
    IDLE = "idle"
    STARTED = "started"
    CANCELLED = "cancelled"


class GoProStatus(BaseModel):
    status: GoProState
    camera_identifier: str
    preview_running: bool
    visual_status: VisualState
    last_frame_at: datetime | None = None
    message: str | None = None


class GoProReconfigureStatus(BaseModel):
    status: GoProReconfigureState
    job_id: str | None = None
    started_at: datetime | None = None
    message: str | None = None
