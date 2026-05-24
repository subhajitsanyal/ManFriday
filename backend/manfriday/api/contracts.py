from datetime import datetime

from pydantic import BaseModel, Field


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


class PushToTalkStartRequest(BaseModel):
    session_id: str


class PushToTalkStartResponse(BaseModel):
    session_id: str
    turn_id: str
    status: str
    started_at: datetime
    max_duration_seconds: int


class PushToTalkReleaseRequest(BaseModel):
    session_id: str
    user_text: str | None = None
    audio_ref: str | None = "mock://android/push-to-talk"
    has_speech: bool = True


class CitationResponse(BaseModel):
    citation_id: str
    source_id: str
    chunk_id: str
    source_title: str
    source_uri: str
    source_type: str
    section: str | None
    score: float


class PushToTalkReleaseResponse(BaseModel):
    session_id: str
    turn_id: str
    status: str
    user_text: str | None = None
    assistant_text: str | None = None
    frame_id: str | None = None
    visual_status: str | None = None
    timing_ms: dict[str, int] | None = None
    citations: list[CitationResponse] = Field(default_factory=list)


class RetrievalSkippedResponse(BaseModel):
    source: str
    reason: str


class RetrievalFailureResponse(BaseModel):
    source: str
    reason: str


class RetrievalSourceResponse(BaseModel):
    source_id: str
    type: str
    title: str
    uri: str
    chunk_count: int
    content_hash: str | None
    manufacturer_or_manual: bool
    retrieved_at: str | None


class RetrievalIngestResponse(BaseModel):
    status: str
    local_files_indexed: int
    urls_indexed: int
    source_count: int
    chunk_count: int
    skipped: list[RetrievalSkippedResponse]
    failed: list[RetrievalFailureResponse]
    sources: list[RetrievalSourceResponse]


class RetrievalQueryRequest(BaseModel):
    query: str
    limit: int = 5


class RetrievalChunkResponse(BaseModel):
    chunk_id: str
    source_id: str
    source_type: str
    source_title: str
    source_uri: str
    manufacturer_or_manual: bool
    chunk_index: int
    page: int | None
    section: str | None
    text: str
    score: float
    bm25_score: float
    keyword_score: float


class RetrievalQueryResponse(BaseModel):
    query: str
    source_count: int
    chunk_count: int
    result_count: int
    results: list[RetrievalChunkResponse]


class GoProStatusResponse(BaseModel):
    status: str
    camera_identifier: str
    preview_running: bool
    visual_status: str
    last_frame_at: datetime | None
    message: str | None


class GoProReconfigureRequest(BaseModel):
    confirm_clear_credentials: bool = False


class GoProReconfigureResponse(BaseModel):
    status: str
    job_id: str | None
    started_at: datetime | None
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
