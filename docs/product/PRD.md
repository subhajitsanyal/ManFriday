# Man Friday PRD

## 1. Product Summary

Man Friday is a hands-free visual copilot for DIY projects. It uses a GoPro as
the visual input, an Android app for voice interaction and UI, a self-hosted
LiveKit stack for realtime audio, and a Mac backend for GoPro control, frame
sampling, retrieval, safety policy, and OpenAI-compatible model calls.

The product is Android-first. iPhone support is planned after the Android MVP.

## 2. Goals

- Provide useful visual Q&A while the user's hands are occupied.
- Use the GoPro as the primary visual input.
- Keep the Android app thin for MVP: voice I/O, setup, controls, latest frame,
  transcript, citations, and status.
- Run the MVP backend on the user's Mac on the same Wi-Fi as the Android phone
  and GoPro.
- Use self-hosted LiveKit to avoid subscription lock-in.
- Use an OpenAI-compatible provider abstraction so the backend can use OpenAI
  cloud first and a local OpenAI-compatible model later.
- Search local documents and configured online resources before using web search.
- Make the MVP implementation testable with explicit latency, state, and failure
  behavior.

## 3. Non-Goals For MVP

- Fully standalone phone-only operation.
- iPhone app implementation.
- Continuous raw video-to-LLM streaming.
- Full live preview in the Android app as a hard MVP requirement.
- Persistent project memory across days.
- Cloud-hosted backend.
- Direct Android GoPro control.
- Broad GoPro model compatibility.

## 4. MVP Target Environment

- Android phone.
- User's Mac laptop as backend host.
- Self-hosted LiveKit server running locally on the Mac.
- GoPro on the same Wi-Fi as the Mac and Android phone.
- OpenAI cloud model for first MVP.
- Local OpenAI-compatible model endpoint supported later through config.

MVP officially supports the user's current GoPro only:

- Camera serial suffix: `2312`.
- Validated Python dependency: `open-gopro==0.22.0`.
- Validated control path: COHN credentials plus UDP preview stream.

Broader Open GoPro compatibility is a later goal, not an MVP guarantee.

## 5. Product Scope

### MVP Included

- Android app with two screens:
  - Setup/settings screen.
  - Active copilot screen.
- Local Mac backend built with Python FastAPI plus LiveKit Agents Python.
- Self-hosted LiveKit server running locally.
- Shared local secret authentication for Android-to-backend calls.
- Backend-issued LiveKit room tokens.
- Push-to-talk voice interaction.
- Voice answer plus on-screen transcript.
- Latest sampled frame display.
- Manual Look button.
- Session memory.
- Hybrid retrieval from local docs and configured online URLs.
- Optional web search fallback.
- Safety-first assistant behavior enforced by prompt plus backend policy layer.
- User-controlled debug mode.

### Stretch

- Near-live or live preview inside Android app.
- Watch-this mode with periodic sampled frames during active guidance.
- Android-side GoPro control via OpenGoPro Kotlin SDK.
- Android-side frame sampling.
- Persistent project memory.
- iPhone planning and prototype.

## 6. LiveKit Boundary

LiveKit is used for audio transport only in the MVP.

LiveKit carries:

- Android microphone audio to the backend LiveKit agent.
- Assistant voice audio back to Android.
- Basic room/session connection.

REST/WebSocket carries all app and product state:

- Authentication.
- LiveKit token issuance.
- Session lifecycle.
- GoPro status.
- Start/stop stream.
- Latest frame metadata and image URLs.
- Look/pinned-frame state.
- Transcript text.
- Citations.
- Errors.
- Debug mode.
- Assistant state.

LiveKit room lifecycle:

- User taps Start Session in Android.
- Android calls backend with the shared local secret.
- Backend creates a session ID and LiveKit room name.
- Backend issues an Android LiveKit token and starts/joins the agent.
- One active DIY session maps to one LiveKit room.
- Android disconnect/reconnect does not end the session automatically.
- User taps End Session to discard live memory.
- Backend may auto-expire inactive sessions after a configurable timeout.

## 7. Authentication And Local Trust

MVP uses a shared local secret.

Requirements:

- Backend reads `MANFRIDAY_LOCAL_SECRET` from `.env`.
- Android setup screen asks for backend URL and local secret.
- REST calls include the secret using an authorization header.
- WebSocket connection authenticates with the same secret.
- Backend issues LiveKit tokens only after validating the secret.
- Debug endpoints require the same secret.
- MVP assumes trusted local Wi-Fi plus shared secret.
- HTTPS is not required for first local MVP, but should be supported later.

Recommended header:

```text
Authorization: Bearer <MANFRIDAY_LOCAL_SECRET>
```

## 8. User Experience

### Setup Flow

1. User starts LiveKit server on the Mac.
2. User starts FastAPI backend/agent on the Mac.
3. User opens Android app.
4. User enters backend URL and local secret.
5. Android verifies backend health.
6. User taps Start Session.
7. Backend creates session and LiveKit room, then returns LiveKit token.
8. Android joins LiveKit room.
9. User starts GoPro preview from Android.
10. Backend reuses saved COHN credentials or returns a reconfigure-required state.
11. Android shows GoPro/backend/visual status and latest sampled frame.

### Reconfigure GoPro Flow

1. User taps Reconfigure GoPro.
2. Backend asks for confirmation.
3. Backend clears saved COHN credentials only after confirmation.
4. User puts GoPro into pairing/connect mode.
5. Backend runs BLE/Wi-Fi/COHN provisioning.
6. Backend saves new COHN credentials locally.
7. Backend starts preview stream and frame sampler.

### Active Copilot Flow

1. User points GoPro at work area.
2. User holds push-to-talk.
3. User asks a spoken question.
4. User releases push-to-talk.
5. Backend finalizes speech capture, selects a frame, retrieves context, applies
   safety policy, calls model, and speaks response through LiveKit.
6. Android displays transcript, citations, and the frame used for analysis.

### Manual Look Flow

1. User taps Look.
2. Backend selects/captures a frame and pins it for 60 seconds.
3. Android displays the pinned frame.
4. Follow-up questions within the TTL use that pinned frame by default.
5. User can tap Look again to replace the pinned frame.
6. After TTL expires, frame selection returns to normal fresh/latest behavior.

## 9. Voice Requirements

MVP voice pipeline uses LiveKit agent plugins for STT, LLM, and TTS.

MVP provider defaults:

- STT provider: OpenAI.
- LLM provider: OpenAI.
- TTS provider: OpenAI.
- STT, LLM, and TTS are all provider-configurable so they can later point to
  local or OpenAI-compatible services.

Responsibilities:

- Android sends and receives audio through LiveKit.
- Backend LiveKit agent performs:
  - speech-to-text
  - prompt assembly
  - frame context injection
  - retrieval context injection
  - model call
  - text-to-speech
- Backend emits transcript/citation/status events over REST/WebSocket.

Voice/provider config:

```text
STT_PROVIDER=openai
STT_MODEL=<default OpenAI transcription model>
TTS_PROVIDER=openai
TTS_MODEL=<default OpenAI speech model>
TTS_VOICE=<default voice>
MODEL_PROVIDER=openai
MODEL_NAME=<vision-capable OpenAI model>
```

Push-to-talk semantics:

- Hold-to-talk for MVP.
- Button down starts listening.
- Button up stops listening, selects frame, and submits the question.
- Max recording duration: 20 seconds.
- Release before speech is detected discards the turn.
- If fresh frame selection fails, backend proceeds without visual input and marks
  visual context unavailable.

Later:

- Wake word or hands-free always-listening mode.
- Earbud button trigger.
- Interruption/barge-in handling.
- Tap-to-start/tap-to-stop mode.

## 10. Visual And Frame Requirements

The model must not receive continuous raw video in MVP.

Backend frame sampler:

- Decode GoPro UDP preview stream on Mac using an `ffmpeg` subprocess.
- Target sample rate: 2 FPS.
- JPEG quality target: approximately 80.
- Cache latest frame metadata and JPEG.
- `ffmpeg` is a required local dependency for MVP.
- Backend monitors the `ffmpeg` process and restarts or marks visual degraded on
  process exit.
- Non-debug mode keeps latest frame, pinned frame, and frames attached to active
  transcript events in memory only.
- Debug mode saves frames used for analysis by default, not every sampled frame.
- If sampling stops for more than 5 seconds, backend marks visual status as
  degraded.

Question-time frame selection:

- If a pinned Look frame is active, use it.
- Otherwise use latest cached frame if its age is <= 2 seconds.
- If latest frame is stale, wait up to 1 second for a newer frame.
- If no fresh frame is available, proceed without image and tell the user visual
  context is unavailable.
- The "frame used for analysis" is the exact `frame_id` attached to the model
  request and displayed in the transcript.

Frame retention:

- Non-debug mode: in-memory only.
- Debug mode: save frames used for analysis, frame metadata, and timing.

## 11. Knowledge Retrieval Requirements

Man Friday answers using prioritized context:

1. Session context:
   - Current conversation.
   - Current task-state summary.
   - Latest/pinned GoPro frame metadata.
2. Local document directory:
   - Configured directory on Mac backend.
   - Manuals, PDFs, markdown, text notes, project notes, and supported docs.
3. Configured online resources:
   - MVP starts with manually added URLs fetched and indexed ahead of time.
   - Later supports allowed-domain live search.
4. Web search fallback:
   - Optional and controlled by config.
   - Runs only when enabled and either explicitly requested or local/configured
     retrieval confidence is low.

Retrieval strategy:

- Hybrid retrieval from day one:
  - keyword/BM25 index
  - vector embedding index using local SentenceTransformers embeddings
  - merge/rerank results
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Vector store: FAISS persisted locally.
- Prefer local docs over indexed online resources when confidence is similar.
- Prefer manufacturer/manual documentation over generic web results.
- Web search transcript must indicate that web search was used.
- Web sources must be cited.
- If web is disabled and confidence is low, Man Friday says it lacks enough
  sourced context and asks whether to search online.
- Web search provider: Tavily.
- Web search config:

```text
WEB_SEARCH_ENABLED=false
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
WEB_SEARCH_TIMEOUT_SECONDS=5
WEB_SEARCH_MAX_RESULTS=5
```

- Tavily result metadata must include title, URL, snippet, provider rank, and
  retrieved timestamp.

Configured online resources:

- User adds trusted URLs to a backend config file under
  `knowledge/online-sources`.
- File format: YAML URL list.
- MVP supports manually listed URLs only.
- MVP does not recursively crawl sites and does not support live domain search.
- Backend fetches those URLs during ingestion.
- Fetched pages are stored/indexed with source metadata.
- Failed URL fetches are reported per source but do not fail the full ingestion.

Example `knowledge/online-sources/sources.yaml`:

```yaml
sources:
  - id: gopro-docs
    type: url
    url: https://example.com/manual
    title: GoPro Manual
    tags: [gopro, camera]
    refresh: manual
```

Ingestion:

- Backend loads existing indexes on startup.
- Backend does not automatically re-index on every startup.
- Ingestion can be triggered by CLI:

```bash
manfriday ingest
```

- Ingestion can also be triggered by authenticated REST:

```text
POST /retrieval/ingest
```

Ingestion limits:

- Max local file size: 50 MB.
- Max PDF pages indexed per file: 300.
- Max configured URLs: 100.
- Max fetched URL size: 25 MB.
- URL fetch timeout: 15 seconds.
- Unsupported files are skipped with warning.
- Failed files/URLs are reported in the ingestion summary.

## 12. Session Memory Requirements

Sessions start and end explicitly.

Lifecycle:

- User taps Start Session.
- Backend creates session ID and LiveKit room.
- User taps End Session to discard live session memory.
- Android disconnect/reconnect does not end session automatically.
- Backend may auto-expire inactive sessions after a configurable timeout, default
  2 hours.

Activity that resets idle expiration:

- authenticated REST call for the session
- active WebSocket heartbeat
- LiveKit participant connected
- user voice turn starts/completes
- assistant response starts/completes
- Look action
- GoPro start/stop command

Activity that does not reset idle expiration:

- frame sampler producing frames by itself
- GoPro stream running with no user/app interaction

On session expiration:

- Backend ends the LiveKit room/agent session.
- Backend clears live session memory.
- Backend unpins frames.
- GoPro stream state is left unchanged unless auto-stop is later configured.
- Android receives `session.expired`.
- Android transcript becomes read-only until user starts a new session.

MVP memory contents:

- User transcript text.
- Assistant transcript text.
- Retrieved snippets and source IDs used in answers.
- Frame metadata for frames used in answers.
- Current task-state summary:
  - user goal
  - identified object/project
  - relevant tools/materials
  - unresolved questions
  - safety flags

Raw frame images:

- Latest frame, pinned frame, and active transcript frames may remain in memory.
- Raw frame images are not persisted unless debug mode is enabled.

Persistent project memory is later.

## 13. Safety Requirements

Man Friday behaves like a safety-first shop assistant:

- Direct and concise.
- Practical and grounded.
- Cautious around hazards.
- Willing to ask for another angle or closer view.
- Avoids overconfident guesses.
- Explains enough to be useful while the user's hands are busy.

Safety is enforced by both:

- backend policy layer
- model/system prompt

Backend policy:

- Applies deterministic/rule-based detection for high-risk categories.
- Can override or constrain model response for high-risk cases.
- Emits safety flags into session memory.

Safety checks run at three stages:

1. After STT and before retrieval/model call, classify the user request text for
   obvious high-risk categories.
2. After retrieval/frame context and before model call, add visual/source-informed
   safety flags to prompt context.
3. After model response and before TTS/transcript finalization, check for unsafe
   operational instructions and replace or constrain the response if needed.

Risk-tiered behavior:

- Low confidence: ask for another angle, closer view, or more context.
- Moderate risk: provide general guidance with a clear caution.
- High risk: refuse detailed hazardous instructions and recommend a qualified
  professional or authoritative source.

High-risk categories:

- Live electrical work.
- Gas lines.
- Structural/load-bearing changes.
- Hazardous chemicals.
- Power tools and blades.
- Ladders/heights.
- Heat/fire.

High-risk response template:

1. Acknowledge the task.
2. State the risk.
3. Avoid step-by-step hazardous instruction.
4. Recommend de-energizing, ventilating, PPE, or a professional as appropriate.
5. Offer safe, general, non-operational guidance.

Allowed safety behavior:

- general safety principles
- visual identification
- low-risk checks
- non-operational explanations
- de-energize/unplug/ventilate/PPE guidance

Refused or constrained behavior:

- step-by-step hazardous operations
- live electrical work
- gas line work
- structural/load-bearing modifications
- tool guard or safety bypasses
- hazardous chemical handling beyond general precautions

## 14. Data Privacy And Retention

Default:

- Do not persist frames, audio, or transcripts beyond live session memory.

Debug mode:

- User-controlled.
- Requires local secret auth.
- Saves only targeted troubleshooting artifacts:
  - transcripts
  - retrieved source snippets
  - frame metadata
  - frames used for analysis
  - backend timing metrics
  - errors/events
  - model request/response metadata excluding API keys/secrets

Debug mode does not save:

- every sampled frame
- continuous audio
- API secrets

Debug artifact location and format:

```text
ManFriday/backend/debug_artifacts/
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

Debug retention:

- Keep last 10 debug sessions by default.
- Configurable with `DEBUG_MAX_SESSIONS`.
- Manual cleanup command can be added later.

Debug redaction:

- Strip API keys, auth headers, local secret, and Wi-Fi password.
- Model metadata may include provider, model, token counts, and timing, but not
  secrets.

API keys:

- Stored only on Mac backend `.env`.
- Android app must not store OpenAI/local-model credentials in MVP.

## 15. Architecture

```text
Android App
  - Setup/settings screen
  - Active copilot screen
  - LiveKit client for audio only
  - REST/WebSocket client for app state/control
  - Latest sampled frame display
  - Transcript/citation display

Self-hosted LiveKit Server on Mac
  - Realtime audio transport
  - Room connection

Mac Backend: Python FastAPI + LiveKit Agents Python
  - Auth and LiveKit token issuance
  - Session lifecycle
  - LiveKit voice agent
  - STT/LLM/TTS plugin orchestration
  - GoPro control/provisioning
  - UDP stream frame sampler
  - Latest-frame cache
  - Session memory
  - Safety policy layer
  - Retrieval pipeline
  - OpenAI-compatible model client
  - REST/WebSocket API

GoPro
  - Wi-Fi/COHN camera control
  - UDP preview stream

Model Provider
  - OpenAI cloud for MVP
  - Local OpenAI-compatible endpoint later
```

## 16. Backend Runtime And Configuration

Backend framework:

- Python FastAPI for REST/WebSocket.
- LiveKit Agents Python for the voice agent.
- LiveKit agent runs as a separate worker process from day one.
- FastAPI and the agent worker are started separately in manual dev mode and as
  separate services in Docker Compose.

MVP processes:

- LiveKit server.
- FastAPI backend.
- LiveKit agent worker.

FastAPI owns:

- auth
- session state
- REST/WebSocket
- GoPro/frame pipeline
- retrieval service APIs
- LiveKit token issuance

Agent worker owns:

- joining LiveKit rooms
- STT/LLM/TTS voice pipeline
- asking FastAPI/backend services for session context, frame, retrieval, and
  safety context

Startup:

- Manual startup first:
  - start LiveKit server
  - start FastAPI backend
  - start LiveKit agent worker
  - start Android app
- Docker Compose soon after:
  - LiveKit server
  - FastAPI backend
  - LiveKit agent worker
  - retrieval/indexing runs inside backend initially using local persisted
    FAISS/BM25 files

Required config:

```text
MANFRIDAY_LOCAL_SECRET
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
MODEL_PROVIDER
MODEL_BASE_URL
MODEL_API_KEY
MODEL_NAME
STT_PROVIDER
STT_MODEL
TTS_PROVIDER
TTS_MODEL
TTS_VOICE
EMBEDDING_PROVIDER
EMBEDDING_MODEL
VECTOR_STORE
VECTOR_INDEX_DIR
GOPRO_IDENTIFIER
GOPRO_WIFI_SSID
GOPRO_WIFI_PASSWORD
GOPRO_COHN_DB_PATH
FRAME_UDP_PORT
FRAME_SAMPLE_FPS
FRAME_JPEG_QUALITY
LOCAL_DOCS_DIR
ONLINE_SOURCES_CONFIG
WEB_SEARCH_ENABLED
WEB_SEARCH_PROVIDER
TAVILY_API_KEY
WEB_SEARCH_TIMEOUT_SECONDS
WEB_SEARCH_MAX_RESULTS
DEBUG_MODE_DEFAULT
DEBUG_MAX_SESSIONS
SESSION_IDLE_TIMEOUT_SECONDS
```

## 17. Model Provider Abstraction

Backend config supports:

```text
MODEL_BASE_URL
MODEL_API_KEY
MODEL_NAME
MODEL_PROVIDER
```

MVP provider:

- OpenAI cloud.

Later provider:

- Local OpenAI-compatible model endpoint.

The backend must isolate provider-specific logic behind a model client interface
so Android does not change when providers change.

STT and TTS must follow the same provider-abstraction pattern:

- STT config: `STT_PROVIDER`, `STT_MODEL`.
- TTS config: `TTS_PROVIDER`, `TTS_MODEL`, `TTS_VOICE`.
- MVP defaults use OpenAI providers.
- Later providers may be local or OpenAI-compatible where supported.

## 18. GoPro Integration Requirements

MVP uses the existing Python exploration path as the basis for backend control.

COHN credential behavior:

- Store COHN credentials locally on the Mac.
- Reuse credentials by default.
- Start-preview first tries saved credentials.
- If saved IP is unreachable, backend returns clear `gopro_unreachable` state.
- User can click Reconfigure GoPro in Android setup screen.
- Reconfigure clears saved credentials and runs BLE/Wi-Fi/COHN provisioning.
- Backend never silently wipes or replaces credentials without user action.

Reconfigure API behavior:

- `POST /gopro/reconfigure` requires explicit request-body confirmation:

```json
{
  "confirm_clear_credentials": true
}
```

- If confirmation is missing or false, backend returns
  `confirmation_required`.
- Reconfigure progress is reported over WebSocket.
- Reconfigure can be cancelled with `POST /gopro/reconfigure/cancel`.

Start/stop ownership:

- Backend is the owner of preview stream during MVP.
- Start-preview is idempotent:
  - if stream is already running, return success with current status.
  - if GoPro is unreachable, return `gopro_unreachable`.
  - if credentials are missing, return `gopro_reconfigure_required`.
- Stop-preview is idempotent:
  - if stream is already stopped, return success with stopped status.

Failure recovery:

- If stream drops, backend marks GoPro/visual state degraded.
- If frame sampler has no frame for >5 seconds, mark visual degraded.
- User-visible state must explain whether the issue is GoPro connection, stream,
  frame sampler, or backend.

## 19. Backend API Contract

All REST and WebSocket calls require the local secret except unauthenticated
`GET /health`, which may expose only basic service status.

### REST Endpoints

```text
GET  /health
POST /session/start
POST /session/end
GET  /session/status
GET  /gopro/status
POST /gopro/start-preview
POST /gopro/stop-preview
POST /gopro/reconfigure
POST /gopro/reconfigure/cancel
POST /frame/look
GET  /frame/latest
GET  /frame/{frame_id}.jpg
POST /retrieval/ingest
POST /debug/mode
```

`POST /session/start` creates or resumes a session and returns the LiveKit token.
There is no standalone `POST /livekit/token` endpoint in MVP. If token refresh
is needed later, add `POST /session/{session_id}/livekit-token`.

Common error shape:

```json
{
  "error": {
    "code": "gopro_unreachable",
    "message": "GoPro is not reachable at the saved COHN address.",
    "retryable": true
  }
}
```

### `GET /frame/latest`

Returns JSON metadata:

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

Returns JPEG bytes:

```text
Content-Type: image/jpeg
```

### WebSocket Events

```text
session.status.changed
gopro.status.changed
frame.latest.updated
frame.pinned
assistant.transcript.delta
assistant.response.started
assistant.response.completed
assistant.error
retrieval.sources.selected
safety.warning
debug.mode.changed
gopro.reconfigure.started
gopro.reconfigure.progress
gopro.reconfigure.completed
gopro.reconfigure.failed
gopro.reconfigure.cancelled
session.expired
```

Event payloads must include:

- `session_id`
- event type
- timestamp
- stable IDs for frames, transcript turns, and sources where applicable

Latest frame delivery:

- WebSocket push is primary.
- Backend pushes `frame.latest.updated` at max 2 FPS while the active copilot
  screen is connected.
- Android fetches JPEG bytes from `jpeg_url`.
- If WebSocket disconnects or frame events become stale, Android polls
  `GET /frame/latest` every 2 seconds.
- JPEG responses should use cache-control headers that prevent accidental stale
  display.

## 20. Android App Requirements

### Permissions

- Microphone permission required.
- Network access required.
- Bluetooth audio uses Android system routing.
- No custom audio device selector in MVP.
- Android camera permission is not required for MVP.

### Setup Screen

- Backend URL field.
- Local secret field.
- Connect/disconnect button.
- Backend URL and local secret are stored with Android Keystore-backed encrypted
  storage.
- User can clear/reset stored backend credentials from Setup screen.
- If encrypted storage fails, app asks user to re-enter the secret rather than
  storing it insecurely.
- Backend health status.
- LiveKit connection status.
- Session start/end controls.
- GoPro status.
- Start/stop stream control.
- Reconfigure GoPro button.
- Debug mode toggle.

### Active Copilot Screen

- Latest sampled frame.
- Frame age/status.
- Push-to-talk button.
- Look button.
- Transcript.
- Citations/sources when used.
- Response state.
- GoPro/backend/visual status.

### Required UI States

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

Transcript entries should support:

- user speech text
- assistant speech text
- frame thumbnail/reference
- citations/sources
- safety warnings
- errors

## 21. Latency And Quality Targets

Acceptance thresholds:

- Backend health visible in app within 2 seconds of entering URL/secret.
- GoPro start-preview succeeds or returns clear failure within 15 seconds when
  credentials are valid.
- Latest frame age shown in app and normally stays under 2 seconds while stream
  is healthy.
- Push-to-talk max recording duration is 20 seconds.
- Quick Q&A response starts within 5 seconds after push-to-talk release in
  normal conditions.
- If no fresh frame is available, user receives a clear degraded-visual message.
- Transcript shows user question, assistant answer, frame reference, and source
  citations when sources are used.
- Backend marks visual degraded within 5 seconds if GoPro stream/frame sampling
  drops.

Latency budget target:

- Frame selection: <= 1 second additional wait.
- Retrieval: short timeout, degrade gracefully to available context.
- Model response: stream partial text/voice when possible.

## 22. MVP Success Criteria

MVP acceptance target:

- Android app authenticates to Mac backend with shared local secret.
- Backend issues LiveKit token after auth.
- Android joins local LiveKit room.
- User starts a session explicitly.
- User can start/stop GoPro preview from Android.
- Backend samples GoPro frames at 2 FPS.
- Android shows latest frame metadata/image.
- User can ask spoken question with hold-to-talk.
- Backend selects correct frame according to frame semantics.
- Backend retrieves context using hybrid local/configured-source retrieval.
- Backend applies safety policy.
- Backend sends question + frame + retrieved context to model.
- User hears spoken answer.
- App shows transcript, frame reference, and citations.
- Session memory carries context across follow-up questions.

Stretch demo target:

- Near-live or live visual feed in app.
- Watch-this mode.
- Persistent project memory preview.

## 23. Roadmap

### Phase 0: Project Setup

- Create repo structure.
- Preserve GoPro exploration code.
- Capture PRD and decisions.

### Phase 1: GoPro/Frame Pipeline

- Package GoPro control into backend module.
- Implement COHN credential reuse/reconfigure behavior.
- Implement start/stop preview endpoints.
- Decode UDP stream and sample latest frame at 2 FPS.
- Implement latest-frame cache.
- Implement `/frame/latest` and JPEG endpoint.
- Validate low-latency ffplay workflow remains available.

### Phase 2: Backend Agent Skeleton

- Run self-hosted LiveKit locally.
- Implement FastAPI app.
- Implement shared-secret auth.
- Implement session lifecycle and LiveKit token issuance.
- Create LiveKit agent.
- Add model provider abstraction.
- Add session memory.
- Add simple image+question model call.

### Phase 3: Android Thin Client

- Create Android project.
- Add setup/settings screen.
- Add backend REST/WebSocket client.
- Add LiveKit client connection.
- Add session start/end.
- Add GoPro controls.
- Add latest-frame view.
- Add hold-to-talk.
- Add transcript/citation view.

### Phase 4: Retrieval

- Local document ingestion.
- Configured URL ingestion.
- BM25 index.
- Vector embedding index.
- Merge/rerank results.
- Web fallback toggle.
- Source display in transcript.

### Phase 4a: Web Search Fallback

- Tavily provider integration.
- Web search config and timeout handling.
- Citation metadata mapping.
- Transcript indication when web search is used.

### Phase 5: End-to-End MVP

- Start stream from Android.
- Ask visual question.
- Capture/select frame.
- Retrieve context.
- Get spoken answer.
- Validate latency, safety, and failure behavior.

### Phase 6: Packaging And Stretch

- Docker Compose for LiveKit and backend.
- Docker Compose includes LiveKit server, FastAPI backend, and LiveKit agent
  worker only for MVP.
- Watch-this mode.
- Live preview in app.
- Android-side GoPro control with OpenGoPro SDK.
- Persistent project memory.
- iPhone planning.

## 24. Initial Task Backlog

### Project

- Add engineering architecture document.
- Add backend skeleton.
- Add Android skeleton.
- Add `.env.example`.
- Add local development startup docs.

### GoPro/Frame Pipeline

- Move exploration code into backend module or reference from `MiscExplorations`.
- Define GoPro config model.
- Implement COHN DB management.
- Implement start-preview endpoint.
- Implement stop-preview endpoint.
- Implement reconfigure endpoint.
- Implement UDP frame sampler.
- Implement latest-frame cache.
- Implement frame metadata/JPEG endpoints.

### Backend

- Create FastAPI app.
- Add shared-secret auth middleware.
- Add WebSocket event bus.
- Add session store.
- Add LiveKit token issuer.
- Add LiveKit agent process.
- Add OpenAI-compatible model client.
- Add STT/TTS provider config.
- Add timing metrics.

### Android

- Create Android project.
- Add Setup screen.
- Add Active Copilot screen.
- Add backend REST/WebSocket client.
- Add auth storage for local secret.
- Add LiveKit client connection.
- Add hold-to-talk control.
- Add transcript view.
- Add latest-frame view.
- Add state/error UI.

### Retrieval

- Define local docs directory config.
- Define online URLs config.
- Add text/markdown/PDF ingestion.
- Add BM25 index.
- Add vector index.
- Add source metadata model.
- Add retrieval API.
- Add web fallback toggle.
- Add Tavily web search provider.
- Add ingestion CLI.

### Safety

- Add system prompt/persona.
- Add deterministic high-risk category checks.
- Add response templates.
- Add safety flags in session memory.
- Add tests/evals with DIY scenarios.

### Testing

- Add auth/session API tests.
- Add LiveKit token issuance tests.
- Add frame API tests using fixture JPEG frames.
- Add frame sampler tests using recorded UDP sample or local video fixture.
- Add retrieval ingestion/search tests.
- Add safety classifier/rule tests.
- Add model provider tests using mock client.
- Add Android UI tests using mocked backend responses.
- Keep hardware validation tests for BLE/COHN provisioning, real GoPro
  start/stop, real UDP stream reliability, and end-to-end latency.

## 25. Testability Requirements

Components that must be testable without physical GoPro hardware:

- auth/session APIs
- LiveKit token issuance
- frame API using fixture JPEG frames
- frame sampler using recorded UDP sample or local video fixture
- retrieval ingestion/search
- safety classifier/rules
- model provider using mock client
- Android UI with mocked backend responses

Hardware-required validation:

- BLE/COHN provisioning
- real GoPro preview start/stop
- real UDP stream reliability
- end-to-end latency with GoPro

## 26. Remaining Open Questions

- Which exact OpenAI STT, LLM, and TTS model IDs should be the checked-in
  defaults at implementation time?
- Which exact BM25 library should be used?
- Which PDF parser should be used for ingestion?
