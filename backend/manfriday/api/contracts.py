from datetime import datetime

from pydantic import BaseModel


class SessionStartRequest(BaseModel):
    app_instance_id: str | None = None
    debug_enabled: bool | None = None


class LiveKitResponse(BaseModel):
    url: str
    room: str
    token: str


class SessionStartResponse(BaseModel):
    session_id: str
    livekit: LiveKitResponse
    expires_at: datetime
    debug_enabled: bool


class SessionEndRequest(BaseModel):
    session_id: str


class SessionEndResponse(BaseModel):
    session_id: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    expires_at: datetime
    assistant_state: str
    debug_enabled: bool


class GoProStatusResponse(BaseModel):
    status: str
    camera_identifier: str
    preview_running: bool
    visual_status: str
    last_frame_at: datetime | None
    message: str | None


class FrameMetadataResponse(BaseModel):
    frame_id: str
    captured_at: datetime
    age_ms: int
    width: int
    height: int
    is_pinned: bool
    pin_expires_at: datetime | None
    used_for_analysis: bool
    jpeg_url: str


class FrameUnavailableResponse(BaseModel):
    status: str = "unavailable"
    visual_status: str
    message: str


class LookResponse(BaseModel):
    frame_id: str
    captured_at: datetime
    pin_expires_at: datetime
    jpeg_url: str
