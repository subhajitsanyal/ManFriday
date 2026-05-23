# Man Friday Engineering Spec

## 1. Purpose

This document translates the product requirements in
`docs/product/PRD.md` into an implementation-oriented engineering plan for the
Android-first MVP.

The MVP is a local, Mac-hosted visual copilot for DIY work:

- Android app for setup, push-to-talk audio, status, frames, transcript, and
  citations.
- Self-hosted LiveKit for audio transport only.
- Python FastAPI backend on the Mac for auth, sessions, GoPro control, frame
  sampling, retrieval, safety, and state.
- Separate LiveKit agent worker for STT, LLM, TTS, and turn orchestration.
- GoPro preview stream decoded on the Mac and sampled at 2 FPS.
- OpenAI cloud provider first, with OpenAI-compatible provider boundaries.

## 2. Engineering Goals

- Produce a thin but complete end-to-end path before optimizing individual
  subsystems.
- Keep product state outside LiveKit. LiveKit carries audio only.
- Make hardware-dependent code replaceable with fixture-backed tests.
- Keep secrets only on the Mac backend and encrypted Android storage.
- Make failure states explicit and user-visible.
- Avoid hidden coupling between Android, GoPro hardware, and model providers.
- Build the first implementation around the user's validated GoPro path:
  camera serial suffix `2312`, `open-gopro==0.22.0`, COHN credentials, and UDP
  preview stream.

## 3. Non-Goals For This Spec

- iOS implementation.
- Cloud deployment.
- Continuous raw video-to-model streaming.
- Persistent project memory.
- Phone-side GoPro control.
- Recursive website crawling.
- Multi-user or internet-exposed auth.

## 4. Target Repository Layout

```text
ManFriday/
  android/
    app/
      src/main/
        java|kotlin/...
        res/...
    build.gradle.kts
    settings.gradle.kts
  backend/
    manfriday/
      api/
      auth/
      config/
      debug/
      events/
      frames/
      gopro/
      livekit/
      memory/
      models/
      retrieval/
      safety/
      sessions/
      voice_agent/
    tests/
      fixtures/
    pyproject.toml
    .env.example
  docs/
    engineering/
      EngineeringSpec.md
    product/
      PRD.md
    research/
  knowledge/
    local-docs/
    online-sources/
      sources.yaml
```

The backend package should be importable as `manfriday`. The FastAPI process
and LiveKit agent worker should share package modules but start through separate
entrypoints.

## 5. Process Architecture

```text
Android App
  REST/WebSocket             LiveKit audio
       |                          |
       v                          v
FastAPI Backend <----------> LiveKit Server <----------> Agent Worker
       |
       +--> GoPro control + UDP frame sampler
       +--> Retrieval indexes
       +--> Safety policy
       +--> Session memory
       +--> Debug artifacts
```

### Process Responsibilities

FastAPI backend owns:

- `.env` configuration loading and validation.
- Shared-secret auth for REST and WebSocket.
- Session lifecycle.
- LiveKit room/token issuance.
- GoPro preview start/stop/reconfigure commands.
- UDP frame sampler lifecycle.
- Latest-frame and pinned-frame cache.
- Retrieval ingestion and query APIs.
- Safety rule service.
- WebSocket event bus.
- Debug artifact persistence.

LiveKit agent worker owns:

- Joining LiveKit rooms as the assistant participant.
- Push-to-talk turn lifecycle integration.
- STT, LLM, and TTS orchestration.
- Requesting turn context from FastAPI/internal service modules.
- Streaming voice response back through LiveKit.
- Emitting transcript/status events through the backend event channel.

Android app owns:

- Setup/settings UI.
- Encrypted storage of backend URL and local secret.
- REST/WebSocket connection.
- LiveKit audio connection.
- Push-to-talk control.
- Latest frame display using backend JPEG URLs.
- Transcript, citations, errors, and state display.

## 6. Backend Module Design

### `config`

Loads environment variables into typed settings.

Recommended implementation:

- `pydantic-settings` for config parsing.
- One `Settings` object per process.
- Explicit startup validation for required MVP config.
- Config values grouped by domain: auth, LiveKit, model, voice, retrieval,
  GoPro, frame sampler, debug, sessions.

Required outputs:

- `settings.local_secret`
- `settings.livekit`
- `settings.model`
- `settings.stt`
- `settings.tts`
- `settings.retrieval`
- `settings.gopro`
- `settings.frames`
- `settings.debug`
- `settings.sessions`

### `auth`

Validates the local shared secret.

Behavior:

- `GET /health` is unauthenticated and returns only basic service state.
- All other REST routes require `Authorization: Bearer <secret>`.
- WebSocket handshake validates the same bearer token.
- Missing, malformed, or wrong secret returns `401`.
- Auth failures must not log the provided token.

### `sessions`

Maintains active sessions in memory for MVP.

Core model:

```text
Session
  session_id
  livekit_room_name
  created_at
  last_activity_at
  expires_at
  status: active | expired | ended
  debug_enabled
  memory
  active_livekit_participants
```

Behavior:

- `POST /session/start` creates a new active session or resumes a resumable
  active session for the app instance.
- `POST /session/end` ends the session, clears live memory, unpins frames, and
  leaves GoPro stream state unchanged.
- Idle expiration defaults to 2 hours.
- Activity reset rules follow the PRD.
- Expiration emits `session.expired`.

### `events`

Provides a typed internal event bus and WebSocket fanout.

Requirements:

- Every event includes `event_id`, `type`, `session_id`, and `timestamp`.
- Events are serialized as JSON.
- Event payloads use stable IDs for turns, frames, and sources.
- WebSocket clients may reconnect and should receive current status snapshots
  after connection.
- Backend should avoid unbounded queues per client. Slow clients can be dropped
  after a configured queue limit.

### `gopro`

Wraps Open GoPro control and COHN credential handling.

Interfaces:

```text
GoProService
  get_status() -> GoProStatus
  start_preview() -> GoProStatus
  stop_preview() -> GoProStatus
  reconfigure(confirm_clear_credentials: bool) -> ReconfigureJob
  cancel_reconfigure() -> ReconfigureStatus
```

Status states:

```text
unknown
credentials_missing
reconfigure_required
connecting
connected
preview_starting
preview_running
preview_stopped
unreachable
degraded
error
```

Credential rules:

- Saved COHN credentials are reused by default.
- Saved credentials are never silently deleted.
- Reconfigure requires `confirm_clear_credentials: true`.
- If confirmation is absent, return `confirmation_required`.
- Reconfigure progress is published over WebSocket.

### `frames`

Owns UDP preview decoding, sampling, frame cache, and Look semantics.

Components:

- `FrameSampler`: owns the `ffmpeg` subprocess.
- `FrameStore`: stores latest frame, pinned frame, and active transcript frames
  in memory.
- `FrameSelector`: chooses the frame for a voice turn.
- `FrameDebugWriter`: persists analysis frames only when debug mode is enabled.

Frame metadata:

```text
Frame
  frame_id
  captured_at
  age_ms
  width
  height
  jpeg_bytes
  is_pinned
  pin_expires_at
  used_for_analysis
  source: latest | look | fixture | unknown
```

Sampler behavior:

- Decode GoPro UDP preview through `ffmpeg`.
- Target 2 FPS.
- JPEG quality approximately 80.
- Keep latest frame in memory.
- Restart or mark visual degraded if `ffmpeg` exits.
- Mark visual degraded if no sampled frame arrives for more than 5 seconds.
- Emit `frame.latest.updated` at max 2 FPS while an active client is connected.

Question-time selection:

1. Use active pinned Look frame if available.
2. Else use latest cached frame if age is `<= 2s`.
3. Else wait up to `1s` for a newer frame.
4. Else proceed without visual input and mark visual unavailable.

Look behavior:

- `POST /frame/look` pins a frame for 60 seconds.
- Look can replace an existing pin.
- Follow-up turns use the pinned frame by default until TTL expires.

### `memory`

Stores live session context.

Contents:

- User transcript text.
- Assistant transcript text.
- Retrieved snippet IDs and source IDs.
- Frame metadata for frames used in answers.
- Task-state summary:
  - user goal
  - identified object/project
  - relevant tools/materials
  - unresolved questions
  - safety flags

Memory is in-memory only for MVP unless debug mode is enabled. It is discarded
when a session ends or expires.

### `retrieval`

Provides ingestion and search across local docs, configured URLs, and optional
web search.

Submodules:

- `loaders`: markdown, text, PDF, and URL fetchers.
- `chunking`: source-aware text chunking.
- `bm25`: keyword index.
- `vectors`: SentenceTransformers embeddings and FAISS store.
- `ranking`: merge/rerank and source preference rules.
- `web`: Tavily provider.
- `metadata`: source and chunk metadata models.

Source priority:

1. Local session context.
2. Local document directory.
3. Configured online resources.
4. Optional web search fallback.

Ingestion behavior:

- Load existing indexes on startup.
- Do not re-index automatically on every startup.
- Support `manfriday ingest`.
- Support authenticated `POST /retrieval/ingest`.
- Skip unsupported files with warnings.
- Report failed files/URLs in a summary.

Suggested MVP dependencies:

- PDF parser: `pypdf` first unless research later shows a stronger need.
- BM25: `rank-bm25` for the first MVP.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector store: FAISS persisted locally.

### `safety`

Applies deterministic safety checks around model calls.

Pipeline stages:

1. Classify STT text before retrieval/model call.
2. Add visual/source-informed safety flags before model call.
3. Check model response before transcript/TTS finalization.

High-risk categories:

- Live electrical work.
- Gas lines.
- Structural/load-bearing changes.
- Hazardous chemicals.
- Power tools and blades.
- Ladders/heights.
- Heat/fire.

Outputs:

```text
SafetyAssessment
  risk_level: low | moderate | high
  categories: list[str]
  flags: list[str]
  response_constraint: none | caution | refuse_detailed_instruction
  user_visible_warning
```

High-risk responses should acknowledge the task, state the risk, avoid
step-by-step hazardous instruction, recommend de-energizing/ventilation/PPE or a
professional as appropriate, and offer safe general guidance.

### `models`

Isolates model-provider details behind OpenAI-compatible interfaces.

Interfaces:

```text
VisionLanguageModel
  complete_turn(request: ModelTurnRequest) -> ModelTurnResponse

SpeechToTextProvider
  transcribe(audio|stream) -> Transcript

TextToSpeechProvider
  synthesize(text|stream) -> Audio
```

MVP provider:

- OpenAI cloud.

Later provider:

- Local OpenAI-compatible endpoint configured through `MODEL_BASE_URL`,
  `MODEL_API_KEY`, and `MODEL_NAME`.

Android must not change when providers change.

### `voice_agent`

Coordinates a spoken turn inside the LiveKit agent worker.

Turn flow:

1. Detect push-to-talk start from LiveKit/client state.
2. Capture audio until button release or 20-second limit.
3. Run STT.
4. Create `turn_id`.
5. Ask backend service for selected frame.
6. Run retrieval against user text and session context.
7. Run pre-model safety assessment.
8. Assemble prompt with session memory, frame, citations, and safety flags.
9. Call model.
10. Run post-model safety check.
11. Stream or play TTS through LiveKit.
12. Emit transcript, citations, frame reference, timing, and completion events.
13. Update session memory.

The agent worker should call internal backend services through HTTP in manual
multi-process mode. If later co-located, the same interfaces can be invoked
directly.

### `debug`

Persists targeted troubleshooting artifacts only when debug mode is enabled.

Path:

```text
backend/debug_artifacts/
  session_<session_id>/
    manifest.json
    transcript.jsonl
    frames/
      <frame_id>.jpg
    retrieval/
      <turn_id>.json
    model/
      <turn_id>.json
    events.jsonl
    timings.jsonl
```

Rules:

- Save frames used for analysis, not every sampled frame.
- Save transcripts, source snippets, timings, errors, and model metadata.
- Strip API keys, auth headers, local secret, and Wi-Fi password.
- Keep last 10 debug sessions by default.

## 7. API Contract

All routes except `GET /health` require bearer auth.

### Common Error Shape

```json
{
  "error": {
    "code": "gopro_unreachable",
    "message": "GoPro is not reachable at the saved COHN address.",
    "retryable": true
  }
}
```

### `GET /health`

Unauthenticated basic service status.

Response:

```json
{
  "status": "ok",
  "service": "manfriday-backend",
  "version": "0.1.0",
  "time": "2026-05-23T20:15:01.123Z"
}
```

### `POST /session/start`

Creates a session, creates a LiveKit room, starts/targets the agent worker, and
returns Android connection details.

Response:

```json
{
  "session_id": "sess_...",
  "livekit": {
    "url": "ws://localhost:7880",
    "room": "manfriday_sess_...",
    "token": "..."
  },
  "expires_at": "2026-05-23T22:15:01.123Z",
  "debug_enabled": false
}
```

### `POST /session/end`

Ends the current session and clears live memory.

Response:

```json
{
  "session_id": "sess_...",
  "status": "ended"
}
```

### `GET /session/status`

Returns a snapshot suitable for Android reconnect.

Response:

```json
{
  "session_id": "sess_...",
  "status": "active",
  "expires_at": "2026-05-23T22:15:01.123Z",
  "assistant_state": "idle",
  "debug_enabled": false
}
```

### `GET /gopro/status`

Response:

```json
{
  "status": "preview_running",
  "camera_identifier": "2312",
  "preview_running": true,
  "visual_status": "healthy",
  "last_frame_at": "2026-05-23T20:15:01.123Z",
  "message": null
}
```

### `POST /gopro/start-preview`

Idempotently starts preview and frame sampling.

Failure codes:

- `gopro_reconfigure_required`
- `gopro_unreachable`
- `preview_start_failed`
- `frame_sampler_failed`

### `POST /gopro/stop-preview`

Idempotently stops preview and sampling.

### `POST /gopro/reconfigure`

Request:

```json
{
  "confirm_clear_credentials": true
}
```

If confirmation is missing or false, return `confirmation_required`.

### `POST /gopro/reconfigure/cancel`

Cancels an active reconfigure job where possible.

### `POST /frame/look`

Pins the selected frame for 60 seconds.

Response:

```json
{
  "frame_id": "frame_...",
  "captured_at": "2026-05-23T20:15:01.123Z",
  "pin_expires_at": "2026-05-23T20:16:01.123Z",
  "jpeg_url": "/frame/frame_....jpg"
}
```

### `GET /frame/latest`

Returns latest frame metadata, or a clear unavailable state if no frame exists.

Response:

```json
{
  "frame_id": "frame_2026_05_23T20_15_01_123Z",
  "captured_at": "2026-05-23T20:15:01.123Z",
  "age_ms": 184,
  "width": 1280,
  "height": 720,
  "is_pinned": false,
  "pin_expires_at": null,
  "used_for_analysis": false,
  "jpeg_url": "/frame/frame_2026_05_23T20_15_01_123Z.jpg"
}
```

### `GET /frame/{frame_id}.jpg`

Returns JPEG bytes.

Headers:

```text
Content-Type: image/jpeg
Cache-Control: no-store
```

### `POST /retrieval/ingest`

Triggers ingestion for local docs and configured online sources.

Response:

```json
{
  "status": "completed",
  "local_files_indexed": 12,
  "urls_indexed": 3,
  "skipped": [
    {
      "source": "large_manual.pdf",
      "reason": "file_too_large"
    }
  ],
  "failed": []
}
```

### `POST /debug/mode`

Request:

```json
{
  "enabled": true
}
```

Response:

```json
{
  "debug_enabled": true
}
```

## 8. WebSocket Contract

Path:

```text
GET /ws?session_id=<session_id>
```

Auth:

- Bearer token in header where supported.
- If Android WebSocket library cannot set headers reliably, allow a short-lived
  backend-issued WebSocket token later. Do not put the long-lived local secret in
  query params for MVP unless there is no viable library alternative.

Event envelope:

```json
{
  "event_id": "evt_...",
  "type": "frame.latest.updated",
  "session_id": "sess_...",
  "timestamp": "2026-05-23T20:15:01.123Z",
  "payload": {}
}
```

MVP event types:

- `session.status.changed`
- `gopro.status.changed`
- `frame.latest.updated`
- `frame.pinned`
- `assistant.transcript.delta`
- `assistant.response.started`
- `assistant.response.completed`
- `assistant.error`
- `retrieval.sources.selected`
- `safety.warning`
- `debug.mode.changed`
- `gopro.reconfigure.started`
- `gopro.reconfigure.progress`
- `gopro.reconfigure.completed`
- `gopro.reconfigure.failed`
- `gopro.reconfigure.cancelled`
- `session.expired`

## 9. Android App Design

### Technology Choices

Recommended first implementation:

- Kotlin.
- Jetpack Compose.
- Retrofit or Ktor client for REST.
- OkHttp WebSocket or Ktor WebSocket.
- LiveKit Android SDK.
- AndroidX Security Crypto or Keystore-backed encrypted storage.

### App Layers

```text
ui/
  setup/
  copilot/
data/
  BackendApi
  ManFridayWebSocket
  LiveKitAudioClient
  SecureSettingsStore
domain/
  SessionController
  GoProController
  CopilotStateStore
model/
```

### Setup Screen

Controls:

- Backend URL field.
- Local secret field.
- Connect/disconnect.
- Health status.
- Start/end session.
- LiveKit status.
- GoPro status.
- Start/stop preview.
- Reconfigure GoPro.
- Debug mode toggle.
- Clear stored credentials.

Behavior:

- Health check should complete or fail within 2 seconds.
- Backend URL and secret are stored only after a successful auth check.
- If encrypted storage fails, do not store the secret insecurely.

### Active Copilot Screen

Controls and views:

- Latest sampled frame.
- Frame age/status.
- Push-to-talk button.
- Look button.
- Transcript.
- Citations/sources.
- Assistant state.
- GoPro/backend/visual status.

States:

- disconnected
- connecting
- connected
- backend unavailable
- LiveKit unavailable
- GoPro unavailable
- visual degraded
- listening
- thinking
- speaking
- error

### Push-To-Talk Semantics

- Button down starts listening.
- Button up stops listening and submits the turn.
- Max recording duration is 20 seconds.
- Release before speech is detected discards the turn.
- UI must show listening, thinking, and speaking states distinctly.

## 10. Retrieval Design Details

### Source Metadata

```text
Source
  source_id
  type: local_file | configured_url | web
  title
  uri
  tags
  retrieved_at
  manufacturer_or_manual: bool
```

### Chunk Metadata

```text
Chunk
  chunk_id
  source_id
  text
  page
  section
  token_count
  bm25_score
  vector_score
  combined_score
```

### Ranking Rules

- Merge BM25 and vector results using normalized scores.
- Prefer local docs over configured online resources when scores are close.
- Prefer manufacturer/manual sources over generic sources when scores are close.
- Use web fallback only when enabled and confidence is low or the user asks.
- Transcript must indicate when web search was used.

### Index Artifacts

```text
backend/indexes/
  bm25/
  faiss/
  metadata.sqlite
```

SQLite is recommended for source/chunk metadata because it is local, durable,
and easy to inspect.

## 11. Prompt And Turn Assembly

Model input should be assembled from structured blocks:

```text
System:
  Man Friday assistant persona and safety rules.

Session:
  Current task-state summary and recent turns.

User:
  STT transcript.

Visual:
  Frame metadata and image if available.

Sources:
  Retrieved snippets with source IDs, titles, and URLs/paths.

Safety:
  Risk assessment and required response constraints.
```

Response requirements:

- Direct, concise spoken answer.
- Cite sources when retrieval was used.
- Admit when visual context is unavailable.
- Ask for another angle or closer view when confidence is low.
- Follow safety constraints.

## 12. Observability

Minimum structured logs:

- request ID
- session ID
- turn ID
- event type
- GoPro status transitions
- frame sampler start/stop/restart
- retrieval timing and result counts
- model provider/model and latency
- STT/TTS latency
- safety flags
- errors with sanitized details

Minimum timing metrics per turn:

- audio capture duration
- STT duration
- frame selection duration
- retrieval duration
- model first-token or first-response latency
- TTS start latency
- total release-to-response-start latency

## 13. Testing Strategy

### Unit Tests

- Config parsing and required variable validation.
- Shared-secret auth success/failure.
- Session lifecycle and idle expiration.
- Frame selection logic, including stale frame and Look TTL.
- Safety category detection and response constraints.
- Retrieval ranking merge behavior.
- Debug redaction.
- Common API error serialization.

### Integration Tests Without Hardware

- FastAPI auth/session routes.
- LiveKit token issuance using fake LiveKit settings.
- Frame API with fixture JPEGs.
- Frame sampler against a local video fixture or recorded UDP-like stream.
- Retrieval ingestion over fixture markdown/text/PDF.
- Configured URL ingestion using a local test HTTP server.
- Model provider using a mock OpenAI-compatible server.
- Agent turn orchestration with mocked STT/LLM/TTS.

### Android Tests

- Setup screen with mocked backend health/auth responses.
- Secure settings behavior.
- Session start/end state transitions.
- WebSocket event reduction into UI state.
- Latest frame rendering from mocked image responses.
- Push-to-talk button state transitions.
- Transcript/citation rendering.

### Hardware Validation

- COHN credential reuse.
- Reconfigure flow.
- GoPro preview start/stop.
- Real UDP stream reliability.
- 2 FPS sampling stability.
- End-to-end spoken visual Q&A latency.

## 14. Acceptance Gates

### Backend Gate

- `pytest` passes.
- `ruff` or equivalent linting passes.
- `.env.example` covers all required config.
- API returns documented error shapes.
- No secret values appear in logs or debug artifacts.

### Android Gate

- Unit/UI tests pass.
- App stores secret only in encrypted storage.
- Setup and active screens handle all required states.
- App can recover from backend/WebSocket reconnect.

### End-To-End Gate

- Android authenticates to Mac backend.
- Backend issues a LiveKit token.
- Android joins a local LiveKit room.
- User starts a session explicitly.
- User starts/stops GoPro preview from Android.
- Backend samples frames at 2 FPS.
- Android displays latest frame with age normally under 2 seconds.
- User can ask a spoken question with push-to-talk.
- Backend attaches the selected frame ID to the model request and transcript.
- Retrieval sources appear in transcript when used.
- Safety policy can constrain a high-risk prompt.
- User hears a spoken answer within the target latency under normal conditions.

## 15. Execution Roadmap

### Phase 0: Repository And Development Baseline

Goal: create the skeleton needed to work safely and repeatably.

Deliverables:

- Backend Python package skeleton.
- Android project skeleton.
- `.env.example`.
- Local development README.
- Basic CI-style commands documented.
- Health endpoint.
- Empty but typed config model.

Milestones:

1. Create backend package and dependency manager.
2. Add FastAPI app with `GET /health`.
3. Add Android Compose app shell with Setup and Active Copilot navigation.
4. Add `.env.example` with all PRD config keys.
5. Add first tests for config and health.

Exit criteria:

- Backend starts locally.
- Android app builds.
- Health endpoint is reachable.
- Basic tests pass.

### Phase 1: Auth, Sessions, Events, And LiveKit Token Slice

Goal: establish the control plane before GoPro or model work.

Deliverables:

- Shared-secret auth middleware/dependencies.
- Session start/end/status endpoints.
- WebSocket event bus.
- LiveKit token issuance.
- Agent worker skeleton that can join a room.
- Android setup flow connects to backend and LiveKit.

Milestones:

1. Implement bearer auth for REST and WebSocket.
2. Implement in-memory session store and idle expiration.
3. Implement `POST /session/start`, `POST /session/end`,
   `GET /session/status`.
4. Add LiveKit room/token creation.
5. Add WebSocket connect/reconnect and status snapshot.
6. Wire Android Setup screen to health/auth/session APIs.
7. Wire Android LiveKit connection using returned token.

Exit criteria:

- Android can authenticate, start a session, join a LiveKit room, end the
  session, and recover from app reconnect.
- Auth/session/token tests pass.

### Phase 2: GoPro And Frame Pipeline

Goal: make visual state real and testable.

Deliverables:

- GoPro service wrapper.
- COHN credential reuse and reconfigure flow.
- Start/stop preview endpoints.
- `ffmpeg` frame sampler.
- Latest frame cache.
- Look/pinned frame behavior.
- Frame metadata/JPEG endpoints.
- Android latest frame display.

Milestones:

1. Define GoPro status and error models.
2. Implement credential DB path/config loading.
3. Implement idempotent start/stop preview endpoint behavior.
4. Implement sampler from local fixture first.
5. Implement sampler against GoPro UDP preview stream.
6. Add latest-frame cache and stale/degraded detection.
7. Implement `/frame/latest`, `/frame/{frame_id}.jpg`, and `/frame/look`.
8. Push `frame.latest.updated` over WebSocket.
9. Add Android latest frame image, age, visual status, and Look button.
10. Add hardware validation script/checklist for the supported GoPro.

Exit criteria:

- Backend samples real GoPro frames at 2 FPS.
- Android displays the latest frame and age.
- Visual degraded state appears within 5 seconds of sampler failure.
- Look pins a frame for 60 seconds.
- Frame tests pass with fixtures.

### Phase 3: Voice Agent And Simple Vision Turn

Goal: complete the first spoken visual Q&A path without retrieval.

Deliverables:

- Provider interfaces for STT, LLM, and TTS.
- OpenAI-backed MVP provider implementation.
- Agent turn lifecycle.
- Frame selection at turn time.
- Transcript events.
- Session memory update.
- Android push-to-talk and transcript view.

Milestones:

1. Define provider interfaces and model request/response schemas.
2. Implement OpenAI cloud provider adapters behind config.
3. Implement push-to-talk turn lifecycle.
4. Implement frame selection semantics.
5. Assemble prompt with session memory, user text, and selected frame.
6. Emit `assistant.response.started`, transcript deltas, completion, and errors.
7. Play TTS response through LiveKit.
8. Add Android push-to-talk state handling and transcript rendering.
9. Add mock provider tests for agent orchestration.

Exit criteria:

- User can ask a spoken visual question and hear a spoken response.
- Transcript shows user text, assistant text, and frame reference.
- If no fresh frame exists, backend proceeds without image and reports degraded
  visual context.
- Quick Q&A response starts within the PRD target under normal conditions.

### Phase 4: Local And Configured-Source Retrieval

Goal: ground answers in local docs and trusted configured URLs.

Deliverables:

- Ingestion CLI.
- Authenticated ingestion endpoint.
- Local file loaders.
- Configured URL loader.
- BM25 index.
- FAISS vector index.
- Source/chunk metadata store.
- Retrieval query service.
- Citation display in Android transcript.

Milestones:

1. Define source/chunk metadata schema.
2. Implement markdown/text ingestion.
3. Implement PDF ingestion with page limits.
4. Implement configured URL ingestion from YAML.
5. Implement BM25 indexing.
6. Implement SentenceTransformers embeddings and FAISS persistence.
7. Implement merge/rerank with source priority rules.
8. Add retrieval context into prompt assembly.
9. Emit `retrieval.sources.selected`.
10. Render citations in Android transcript.

Exit criteria:

- `manfriday ingest` builds indexes.
- `POST /retrieval/ingest` returns a per-source summary.
- Agent responses include citations when retrieved context is used.
- Retrieval tests pass for local docs and configured URLs.

### Phase 4a: Optional Web Search Fallback

Goal: add controlled web fallback without weakening source preference.

Deliverables:

- Tavily provider.
- Web-search config and timeout handling.
- Web result metadata.
- Prompt and transcript indication when web search was used.

Milestones:

1. Add web-search config validation.
2. Implement Tavily client with timeout and max result limits.
3. Trigger web only when enabled and local/configured confidence is low or user
   explicitly requests it.
4. Normalize web citations.
5. Add Android indication for web-used turns.

Exit criteria:

- Web search is off by default.
- Web results are cited and labeled.
- Low-confidence behavior asks for permission/context when web is disabled.

### Phase 5: Safety, Debug, And Reliability Hardening

Goal: make the MVP safer, diagnosable, and resilient.

Deliverables:

- Safety classifier/rules.
- Safety prompt block.
- Post-model safety response check.
- Debug mode endpoint and artifact writer.
- Redaction.
- Timing metrics.
- Recovery behavior for LiveKit, WebSocket, GoPro, and sampler failures.

Milestones:

1. Implement deterministic high-risk category matching.
2. Add safety assessment to session memory and prompt assembly.
3. Add high-risk response constraints/templates.
4. Add post-model response validation.
5. Implement debug artifact structure.
6. Add redaction tests.
7. Add timing metrics for each turn.
8. Add Android state handling for degraded/error states.
9. Run scripted failure cases: backend restart, WebSocket disconnect, sampler
   exit, stale frame, model timeout.

Exit criteria:

- High-risk prompts are constrained.
- Debug mode saves targeted artifacts only.
- Secrets are redacted.
- Required UI states are reachable and understandable.
- Failure behavior matches PRD.

### Phase 6: End-To-End MVP Validation

Goal: prove the MVP works as a product flow.

Deliverables:

- End-to-end demo script.
- Hardware validation checklist.
- Latency report.
- Known issues document.
- Packaging/startup docs.
- Optional Docker Compose for LiveKit, FastAPI, and agent worker.

Milestones:

1. Run clean install/startup from docs.
2. Start LiveKit, FastAPI, and agent worker manually.
3. Start Android app and connect.
4. Start session and GoPro preview.
5. Ask visual question.
6. Ask follow-up using session memory.
7. Use Look and verify pinned frame semantics.
8. Trigger retrieval citation.
9. Trigger safety warning.
10. Measure latency targets.
11. Document remaining gaps.

Exit criteria:

- MVP success criteria from the PRD are satisfied.
- Known limitations are documented.
- Next stretch work is unblocked.

## 16. Incremental Development Order

The safest order is:

1. Backend health/config/auth.
2. Session and LiveKit token control plane.
3. Android setup and LiveKit connection.
4. Fixture-backed frame APIs.
5. Real GoPro frame sampler.
6. Android frame display.
7. Mock voice turn.
8. OpenAI-backed voice turn.
9. Retrieval ingestion/query.
10. Citation rendering.
11. Safety enforcement.
12. Debug artifacts.
13. End-to-end hardening.

This order keeps each phase demoable while minimizing the number of unknowns in
flight at once.

## 17. Key Technical Risks

### GoPro Stream Reliability

Risk: UDP preview and `ffmpeg` process behavior may be less stable than API
control.

Mitigation:

- Build sampler restart/degraded-state logic early.
- Keep fixture-based sampler tests.
- Preserve hardware validation scripts.

### LiveKit Agent Push-To-Talk Semantics

Risk: LiveKit audio plugins may prefer always-on or VAD-driven flows.

Mitigation:

- Prototype push-to-talk before retrieval work.
- Keep Android UI state and agent state explicit.
- If necessary, use app events to gate when agent processes audio.

### Latency

Risk: STT, retrieval, vision model, and TTS can exceed the 5-second response
start target.

Mitigation:

- Measure each stage from Phase 3 onward.
- Stream model/TTS when available.
- Bound frame wait to 1 second and retrieval with short timeouts.

### Android Secret Handling

Risk: local secret could accidentally be stored insecurely.

Mitigation:

- Implement encrypted storage before persisting credentials.
- If secure storage fails, require re-entry.

### Retrieval Complexity

Risk: hybrid retrieval plus URL ingestion can delay the MVP.

Mitigation:

- Ship local markdown/text first.
- Add PDF, configured URLs, vectors, and web fallback incrementally.

### Safety Coverage

Risk: rule-based detection misses dangerous requests or over-constrains benign
ones.

Mitigation:

- Start with explicit high-risk categories.
- Add scenario tests.
- Keep model prompt and backend policy independent.

## 18. Initial Implementation Backlog

### Project

- Create backend package.
- Add `pyproject.toml`.
- Add FastAPI health app.
- Add `.env.example`.
- Add local dev docs.
- Add Android Compose skeleton.

### Backend Control Plane

- Auth dependency/middleware.
- Session store.
- Session APIs.
- WebSocket event bus.
- LiveKit token service.
- Agent worker entrypoint.

### GoPro/Frames

- GoPro config model.
- COHN credential manager.
- GoPro service wrapper.
- Preview start/stop.
- Reconfigure job.
- `ffmpeg` sampler.
- Frame cache.
- Look pinning.
- Frame API tests.

### Voice/Model

- Provider interfaces.
- OpenAI provider implementation.
- Mock provider implementation for tests.
- Agent turn orchestration.
- Prompt assembly.
- TTS playback.
- Transcript events.

### Retrieval

- Source/chunk schema.
- Markdown/text loader.
- PDF loader.
- URL loader.
- BM25 index.
- FAISS vector index.
- Merge/rerank.
- Ingestion CLI.
- Ingestion endpoint.
- Tavily provider.

### Safety/Debug

- Safety rules.
- Safety prompt block.
- Post-response checker.
- Debug mode API.
- Artifact writer.
- Redaction utilities.
- Timing metrics.

### Android

- Setup screen.
- Active Copilot screen.
- REST client.
- WebSocket client.
- LiveKit client.
- Secure settings store.
- State reducer/view model.
- Latest frame rendering.
- Push-to-talk control.
- Transcript/citation rendering.

## 19. Open Engineering Decisions

- Final OpenAI STT, vision-capable LLM, and TTS model IDs.
- Whether to use Retrofit or Ktor for Android networking.
- Exact LiveKit agent push-to-talk implementation pattern.
- Whether source/chunk metadata should start in SQLite or JSON files.
- Whether Docker Compose lands before or after Phase 5.
- How Android should authenticate WebSocket if headers are problematic.

