# Man Friday Delivery Plan

## Status

Current phase: Phase 2, GoPro And Frame Pipeline.

Program objective: deliver an Android-first local MVP where an Android app authenticates to a Mac FastAPI backend, joins self-hosted LiveKit for audio, starts GoPro preview, displays sampled frames, supports push-to-talk visual Q&A, uses local/configured retrieval with citations, applies safety policy, and passes the documented release gates.

## MVP Boundaries

- Android first.
- Mac-hosted local backend.
- Self-hosted LiveKit.
- LiveKit carries audio only.
- REST and WebSocket carry product state.
- GoPro support targets the validated camera serial suffix `2312` using `open-gopro==0.22.0`, COHN credentials, and UDP preview.
- No continuous raw video-to-model streaming.
- No persistent project memory.
- No iOS, cloud backend, or phone-side GoPro control for MVP.

## Managed Agents

| Agent | Primary owned scope | Current phase focus |
| --- | --- | --- |
| Backend Control Plane Agent | FastAPI config, auth, sessions, LiveKit tokens, events, WebSocket, API contracts | Phase 0 and Phase 1 |
| Android Client Agent | Android setup, active copilot UI, REST/WebSocket, LiveKit client, secure storage | Phase 0 and Phase 1 |
| GoPro And Frame Pipeline Agent | GoPro service, COHN credentials, preview, sampler, frame cache, Look | Phase 2 |
| Voice And Model Agent | LiveKit agent worker, STT/LLM/TTS providers, turn orchestration | Phase 1 skeleton and Phase 3 |
| Retrieval, Safety, And Debug Agent | ingestion, retrieval, citations, safety, debug artifacts | Phase 4 and Phase 5 preparation |
| QA, Release, And Integration Agent | fixture strategy, phase gates, validation, latency, demo, release readiness | All phases |

## Execution Order

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

## Phase 0: Repository And Development Baseline

Goal: create the skeleton needed to work safely and repeatably.

Exit criteria:

- Backend starts locally.
- Android app builds.
- `GET /health` is reachable without auth.
- Basic backend and Android baseline tests pass.
- `.env.example` covers required MVP config keys.
- Local startup commands are documented.

Work items:

| ID | Task | Owner | Dependencies | Evidence required | Status |
| --- | --- | --- | --- | --- | --- |
| P0-01 | Create backend package skeleton and dependency manager | Backend Control Plane | none | `backend/manfriday` importable; backend test command documented | Implemented |
| P0-02 | Add typed config model and `.env.example` | Backend Control Plane | P0-01 | config tests; required keys listed | Implemented |
| P0-03 | Add FastAPI app with unauthenticated `GET /health` | Backend Control Plane | P0-01 | health test and local curl output | Implemented |
| P0-04 | Create Android Compose app skeleton with setup/active navigation | Android Client | none | Android build succeeds | Implemented and verified |
| P0-05 | Document local development startup and CI-style commands | QA, Release, And Integration | P0-01, P0-04 | README or engineering startup doc | Implemented |
| P0-06 | Define fixture strategy for non-hardware validation | QA, Release, And Integration | none | fixture plan covers frame, LiveKit, model, retrieval, Android mocks | Implemented |

Integration checkpoint:

- Run backend locally, verify `/health`, build Android skeleton, and publish the first startup path.

## Phase 1: Auth, Sessions, Events, And LiveKit Token Slice

Goal: establish the control plane before GoPro or model work.

Exit criteria:

- Android can authenticate, start a session, receive LiveKit room/token details, join LiveKit, end the session, and recover from app reconnect.
- REST and WebSocket auth reject missing, malformed, and wrong secrets.
- Session/token/WebSocket tests pass with fake LiveKit settings.

Work items:

| ID | Task | Owner | Dependencies | Evidence required | Status |
| --- | --- | --- | --- | --- | --- |
| P1-01 | Finalize `/session/start`, `/session/end`, `/session/status`, and event envelope schemas | TPM with Backend and Android | P0-03 | contract reviewed in docs/tests before implementation | Implemented |
| P1-02 | Implement bearer auth for REST and WebSocket | Backend Control Plane | P0-02 | auth tests; no secret logging | Implemented |
| P1-03 | Implement in-memory session store and idle expiration | Backend Control Plane | P1-01 | lifecycle and expiration tests | Implemented |
| P1-04 | Implement LiveKit room naming/token issuance | Backend Control Plane | P1-03 | fake LiveKit token tests | Implemented |
| P1-05 | Implement bounded WebSocket event bus and reconnect snapshot | Backend Control Plane | P1-03 | WebSocket tests | Implemented |
| P1-06 | Add LiveKit agent worker skeleton that can join a room | Voice And Model | P1-04 | worker starts against local/fake LiveKit | Worker entrypoint implemented; real room join pending Phase 3 |
| P1-07 | Wire Android setup/auth/session/LiveKit connection | Android Client | P1-01, P1-04 | mocked tests and local manual flow | Implemented; local manual LiveKit validation pending |

Integration checkpoint:

- Android setup flow starts a backend session, joins the returned LiveKit room, disconnects, reconnects, and ends the session.

## Phase 2: GoPro And Frame Pipeline

Goal: make visual state real and testable.

Exit criteria:

- Backend samples real GoPro frames at 2 FPS.
- Android displays the latest frame and age.
- Visual degraded state appears within 5 seconds of sampler failure.
- Look pins a frame for 60 seconds.
- Frame behavior passes fixture-backed tests.

Key contracts to review before implementation:

- `GoProStatus` states and error codes.
- `Frame` metadata, exact `frame_id` semantics, JPEG URL behavior, cache headers.
- `frame.latest.updated` and `frame.pinned` event payloads.
- Look TTL and question-time frame selection semantics.

Implemented fixture-backed slice:

- Authenticated `GET /gopro/status`, `POST /gopro/start-preview`, and
  `POST /gopro/stop-preview`.
- Authenticated `POST /gopro/reconfigure` and
  `POST /gopro/reconfigure/cancel` with explicit credential-clear
  confirmation.
- Backend `GoProController` boundary with fixture and Open GoPro skeleton
  implementations; the Open GoPro skeleton reports saved COHN credential
  presence without starting real hardware preview yet.
- In-memory fixture frame store with stable `frame_id`, metadata, JPEG bytes,
  stale-frame detection, and Look pinning.
- Fixture frame sampler boundary with idempotent preview start/stop and
  degraded-state reporting for sampler failure or stale frames.
- Authenticated `GET /frame/latest`, `GET /frame/{frame_id}.jpg`, and
  `POST /frame/look`.
- Session-scoped `frame.latest.updated` and `frame.pinned` WebSocket events.
- Android active screen can refresh and display the authenticated latest JPEG,
  frame metadata, age, and trigger Look.

Remaining Phase 2 work:

- Real Open GoPro connection, reachability checks, preview start/stop, and
  hardware provisioning for the reconfigure flow.
- `ffmpeg` UDP frame sampler with 2 FPS cadence and restart handling.
- Local hardware validation of sampler failure and degraded state timing.

Integration checkpoint:

- Start preview from Android, show latest frame and age, pin a Look frame, kill sampler, and verify degraded state.

## Phase 3: Voice Agent And Simple Vision Turn

Goal: complete the first spoken visual Q&A path without retrieval.

Exit criteria:

- User can ask a spoken visual question and hear a spoken response.
- Transcript shows user text, assistant text, and frame reference.
- No-fresh-frame turns proceed without image and show degraded visual context.
- Quick Q&A response starts within target latency under normal conditions.

Key contracts to review before implementation:

- Push-to-talk start/stop signal path.
- Provider interface schemas for STT, LLM, and TTS.
- Assistant state events.
- Transcript event shape and stable `turn_id`/`frame_id` references.

Implemented mock-backed slice:

- Backend provider interfaces for STT, vision-language model, and TTS.
- Deterministic mock STT/LLM/TTS providers for orchestration tests.
- OpenAI-backed STT, Responses API model, and TTS provider adapters behind
  config, with fake-client tests for request shape and response parsing.
- AWS Bedrock Claude Messages adapter behind config, with native SigV4 request
  signing, Sonnet 4.5 as the default inference profile ID, shared AWS
  credentials profile fallback, live smoke validation, and fake-client tests for
  Anthropic Messages payload shape and response parsing.
- `VoiceTurnOrchestrator` with stable `turn_id`, pinned-frame-first selection,
  no-fresh-frame degraded context, assistant state events, transcript events,
  response started/completed events with `response_start` and `total` timing,
  retryable error events, and compact session memory turn records.
- Authenticated push-to-talk start/release endpoints that publish listening
  state on button down, run the mock turn on release, enforce the 20-second max
  duration, and discard release-before-speech turns with retryable events.
- Android Hold to Talk press/release wiring to the backend push-to-talk
  endpoints, assistant state display, and transcript rendering from WebSocket
  transcript events with frame/degraded visual context.
- Android-native speech recognition sends final user text to the backend on
  push-to-talk release, and Android-native TTS speaks final assistant transcript
  events.
- Configured-provider smoke helper is available via `manfriday-voice-smoke`.
- Configured Bedrock smoke validated `response_start=2217ms`, under the
  5-second Phase 3 target.
- Android emulator typed Ask path validates backend, Bedrock, transcript, and
  TTS interaction. Emulator SpeechRecognizer returns `NO_SPEECH_DETECTED`; final
  spoken STT validation is deferred to a physical Android device.

Remaining Phase 3 work:

- Physical Android spoken push-to-talk validation.
- Revisit LiveKit audio capture/playback only if Android-native STT/TTS does not
  meet latency or reliability targets.

Integration checkpoint:

- Mock STT/LLM/TTS turn first, then Bedrock Claude-backed turn with selected
  frame attached.

## Phase 4: Local And Configured-Source Retrieval

Goal: ground answers in local docs and trusted configured URLs.

Exit criteria:

- `manfriday ingest` builds indexes.
- `POST /retrieval/ingest` returns per-source summary.
- Agent responses include citations when retrieved context is used.
- Android renders citations.
- Retrieval tests pass for local docs and configured URLs.

Key contracts to review before implementation:

- Source/chunk metadata schema.
- Retrieval result schema for prompt assembly and citation rendering.
- Ingestion summary error shape.
- Confidence and source priority rules.

Implemented slice:

- Retrieval metadata dataclasses for local/configured/web sources, chunks,
  per-source ingestion results, skipped sources, failures, and summaries.
- Deterministic local Markdown/text ingestion with stable source/chunk IDs,
  title/section extraction, content hashes, timestamps, manual-source detection,
  unsupported-file skips, and file-size limits.
- `manfriday ingest` CLI command that builds local Markdown/text source and chunk
  summaries from `RETRIEVAL_LOCAL_DOCS_DIR`.
- Authenticated `POST /retrieval/ingest` endpoint returning indexed counts,
  skipped files, failures, source/chunk counts, and per-source summaries.
- Dependency-light pure-Python BM25/keyword index built from current
  `SourceMetadata` and `ChunkMetadata`, including section metadata in searchable
  text and deterministic local/manual source preference.
- Authenticated `POST /retrieval/query` endpoint returning ranked chunks,
  source metadata, score components, and stable result ordering.
- Retrieval context builder that pulls top keyword-ranked chunks for the user
  question and injects source/title/section metadata into OpenAI and Bedrock
  model prompts.
- Configured URL ingestion from `RETRIEVAL_ONLINE_SOURCES_PATH` with a
  dependency-light trusted-source YAML reader, stdlib HTTP fetcher, timeout,
  max-size and content-type checks, and per-source failure reporting.
- Local PDF ingestion with file-size and page-count limits, page-aware chunk
  metadata, extraction-failure reporting, and query response page metadata.
- Local and configured URL sources are merged for `manfriday ingest`,
  `POST /retrieval/ingest`, `POST /retrieval/query`, and voice retrieval
  context.
- `manfriday ingest` and `POST /retrieval/ingest` persist source/chunk metadata
  to `RETRIEVAL_INDEX_DIR/index.json`; query and voice retrieval prefer that
  index when it is available and fall back to live rebuild when it is missing,
  unreadable, or empty.
- `manfriday ingest` and `POST /retrieval/ingest` also persist a lightweight
  vector-style sidecar index to `RETRIEVAL_INDEX_DIR/vector_index.json`; query
  and voice retrieval merge BM25/keyword scores with vector scores when the
  sidecar matches the current chunk metadata, otherwise they fall back to the
  keyword baseline.
- Assistant transcript events, push-to-talk API responses, and session memory
  now include citation references when retrieval context is used.
- Android parses citation arrays from transcript events and renders compact
  citation rows under assistant messages using source title, URI, and section.
- Fixture coverage for local `.md`, `.txt`, unsupported files, size-limit skips,
  stable IDs, source metadata, and chunk metadata.
- Query coverage for keyword matching, section matching, stable ordering,
  local/manual source preference, authenticated API access, and empty/missing
  index behavior.
- Voice turn coverage proves retrieved chunks are included in model prompts,
  citations carry URI/title/section metadata, and no-result retrieval does not
  block answers.
- Android unit coverage verifies citation parsing from transcript events and
  citation display labels.
- Configured URL coverage uses a local fixture HTTP server to validate indexed
  URL counts, failures, CLI/API summaries, and URL-ranked query results.
- PDF coverage validates page text extraction, page metadata, page-limit skips,
  size-limit skips, extraction failures, and PDF-ranked query results.
- Index persistence coverage validates metadata roundtrip, stale index
  preference, missing-index fallback, and unreadable-index fallback.
- Merge/rerank coverage validates keyword-only fallback, stale/missing vector
  sidecar behavior, stable merged ordering, local/manual tie preference, and
  voice citations from merged results.

Integration checkpoint:

- Ingest fixture docs and a local test URL, ask a question that cites retrieved context, and render citations in Android transcript.

## Phase 4a: Optional Web Search Fallback

Goal: add controlled web fallback without weakening source preference.

Exit criteria:

- Web search is off by default.
- Web-used turns are clearly labeled and cited.
- When web is disabled and confidence is low, assistant asks for more context or permission to search rather than inventing.

Integration checkpoint:

- Mock Tavily response produces labeled citations; disabled-web low confidence path is visible in transcript.

## Phase 5: Safety, Debug, And Reliability Hardening

Goal: make the MVP safer, diagnosable, and resilient.

Exit criteria:

- High-risk prompts are constrained.
- Debug mode saves targeted artifacts only.
- Secrets are redacted.
- Required UI states are reachable.
- Scripted failure cases pass.

Scripted failure cases:

- Backend restart.
- WebSocket disconnect.
- LiveKit unavailable.
- Sampler process exit.
- Stale frame.
- GoPro unreachable.
- Model timeout.
- Retrieval low confidence.

Implemented slice:

- Retrieval context now carries a structured safety policy with confidence,
  fallback reason, and model-facing instructions.
- Retrieval-backed model prompts include the safety policy before retrieved
  chunks, so no-result and low-confidence turns are explicitly constrained.
- Low-confidence retrieval detects generic-word-only matches and treats them as
  unsupported instead of grounding answers on weak overlap.
- The voice turn layer replaces procedural/tool-like model responses when
  retrieval confidence is low, returning a clear answer path that asks for the
  relevant manual/source or more context.
- Debug sessions write targeted retrieval decision artifacts to
  `DEBUG_ARTIFACTS_DIR/<session>/<turn>/retrieval.json`, including query,
  confidence, fallback reason, selected chunks, score components, citations,
  and safety action.
- Debug retrieval payloads are attached to transcript events and session memory
  only when the session has debug enabled.
- Tests cover low-confidence guard behavior, generic-word low-confidence
  classification, direct debug artifact writing, and authenticated debug-session
  artifact writing through push-to-talk.
- General high-risk prompt classification covers dangerous tool operations,
  electrical/fire/battery risk, medical/legal/financial advice, and requests to
  bypass safety controls.
- Pre-model safety constraints bypass the model for high-risk instruction
  requests and return a safer path with manufacturer documentation or qualified
  expert guidance.
- Post-model safety enforcement replaces unsafe procedural output while
  preserving a helpful alternative.
- Assistant transcript events, completed events, push-to-talk API responses,
  and session memory include safety action/category metadata when applicable.
- Tests cover pre-model model bypass, post-model unsafe-output replacement,
  normal visual/retrieval flows, and API/transcript safety metadata.
- Authenticated debug artifact endpoints list available JSON artifacts and
  return individual artifact payloads from `DEBUG_ARTIFACTS_DIR`.
- Shared debug redaction strips bearer tokens, API keys, AWS keys/session
  tokens, LiveKit secrets, model credentials, and known settings secrets before
  artifacts are written.
- Redaction coverage proves secrets are removed from settings-derived values,
  headers, prompt/query text, and retrieval source metadata.
- Completed turn timing now reports `stt`, `frame_select`, `retrieval`,
  `safety_pre`, `model`, `safety_post`, `response_start`, `tts`, and `total`.
- Scripted reliability coverage now exercises backend session reconnect after a
  WebSocket disconnect, stale-frame degraded visual responses, GoPro unavailable
  and sampler-failure states, model timeout/failure handling, and retrieval
  low-confidence behavior.
- Android now parses assistant safety action/category and turn timing metadata,
  renders safety and timing details under assistant transcript rows, and exposes
  normalized UI states for backend unavailable, LiveKit unavailable, GoPro
  unavailable, visual degraded/unavailable, listening, thinking, speaking,
  safety constrained, low confidence, and error paths.

Integration checkpoint:

- Run all failure scripts, verify user-visible states, inspect debug artifacts for retention and redaction.

## Phase 6: End-To-End MVP Validation

Goal: prove the MVP works as a product flow.

Exit criteria:

- PRD MVP success criteria are satisfied.
- Known limitations are documented.
- Next stretch work is clearly separated from MVP completion.

Demo script:

1. Start LiveKit server on the Mac.
2. Start FastAPI backend.
3. Start LiveKit agent worker.
4. Start Android app.
5. Verify backend health.
6. Start session and join LiveKit.
7. Start GoPro preview.
8. Verify sampled frame age normally stays under 2 seconds.
9. Ask a spoken visual question.
10. Ask a follow-up that uses session memory.
11. Tap Look and verify pinned frame use.
12. Ask a retrieval-backed question and verify citations.
13. Ask a high-risk safety scenario and verify constrained response.
14. Review latency report and known issues.

## Cross-Agent Dependency Tracker

| Dependency | Needed by | Owner | Required by phase | Status |
| --- | --- | --- | --- | --- |
| Complete `.env.example` and typed settings | All backend agents, QA | Backend Control Plane | Phase 0 | Complete |
| `/session/start` response contract | Android, Voice, QA | Backend Control Plane | Phase 1 | Implemented |
| WebSocket auth strategy | Android, Backend, QA | TPM decision with Backend/Android | Phase 1 | Bearer header for MVP |
| LiveKit room/session naming convention | Android, Voice, QA | Backend Control Plane | Phase 1 | Implemented |
| Event envelope and assistant state events | Android, Voice, Retrieval/Safety, QA | Backend Control Plane | Phase 1 | Implemented for session snapshots |
| Frame metadata and `frame_id` semantics | Voice, Android, QA | GoPro And Frame Pipeline | Phase 2 | Implemented for fixture frames |
| Fixture frame/video strategy | GoPro, Android, Voice, QA | QA, Release, And Integration | Phase 2 | Fixture JPEG path and sampler boundary implemented |
| Push-to-talk implementation pattern | Android, Voice, QA | TPM decision with Voice/Android | Phase 3 | Open decision |
| Retrieval result/citation schema | Voice, Android, QA | Retrieval, Safety, And Debug | Phase 4 | Ranked chunk query contract implemented; citation rendering pending |
| Debug artifact redaction contract | Backend, Voice, Retrieval/Safety, QA | Retrieval, Safety, And Debug | Phase 5 | Not started |

## Immediate Next Actions

1. Add real GoPro service boundary for COHN credential reuse and preview state.
2. Replace the fixture sampler internals with an `ffmpeg` sampler implementation
   behind the existing sampler boundary.
3. Add sampler restart/backoff behavior around `ffmpeg` process exits.
4. Run local manual Phase 1 and Phase 2 checkpoints with LiveKit and hardware.
