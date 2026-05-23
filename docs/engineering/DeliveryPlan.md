# Man Friday Delivery Plan

## Status

Current phase: Phase 0, Repository And Development Baseline.

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
| GoPro And Frame Pipeline Agent | GoPro service, COHN credentials, preview, sampler, frame cache, Look | Phase 2 preparation |
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
| P1-01 | Finalize `/session/start`, `/session/end`, `/session/status`, and event envelope schemas | TPM with Backend and Android | P0-03 | contract reviewed in docs/tests before implementation | Pending Phase 0 |
| P1-02 | Implement bearer auth for REST and WebSocket | Backend Control Plane | P0-02 | auth tests; no secret logging | Pending Phase 0 |
| P1-03 | Implement in-memory session store and idle expiration | Backend Control Plane | P1-01 | lifecycle and expiration tests | Pending Phase 0 |
| P1-04 | Implement LiveKit room naming/token issuance | Backend Control Plane | P1-03 | fake LiveKit token tests | Pending Phase 0 |
| P1-05 | Implement bounded WebSocket event bus and reconnect snapshot | Backend Control Plane | P1-03 | WebSocket tests | Pending Phase 0 |
| P1-06 | Add LiveKit agent worker skeleton that can join a room | Voice And Model | P1-04 | worker starts against local/fake LiveKit | Pending Phase 0 |
| P1-07 | Wire Android setup/auth/session/LiveKit connection | Android Client | P1-01, P1-04 | mocked tests and local manual flow | Pending Phase 0 |

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

Integration checkpoint:

- Mock STT/LLM/TTS turn first, then OpenAI-backed turn with selected frame attached.

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
| Complete `.env.example` and typed settings | All backend agents, QA | Backend Control Plane | Phase 0 | Not started |
| `/session/start` response contract | Android, Voice, QA | Backend Control Plane | Phase 1 | Not started |
| WebSocket auth strategy | Android, Backend, QA | TPM decision with Backend/Android | Phase 1 | Open decision |
| LiveKit room/session naming convention | Android, Voice, QA | Backend Control Plane | Phase 1 | Not started |
| Event envelope and assistant state events | Android, Voice, Retrieval/Safety, QA | Backend Control Plane | Phase 1 | Not started |
| Frame metadata and `frame_id` semantics | Voice, Android, QA | GoPro And Frame Pipeline | Phase 2 | Not started |
| Fixture frame/video strategy | GoPro, Android, Voice, QA | QA, Release, And Integration | Phase 2 | Not started |
| Push-to-talk implementation pattern | Android, Voice, QA | TPM decision with Voice/Android | Phase 3 | Open decision |
| Retrieval result/citation schema | Voice, Android, QA | Retrieval, Safety, And Debug | Phase 4 | Not started |
| Debug artifact redaction contract | Backend, Voice, Retrieval/Safety, QA | Retrieval, Safety, And Debug | Phase 5 | Not started |

## Immediate Next Actions

1. Backend Control Plane Agent starts P0-01 through P0-03.
2. Android Client Agent starts P0-04.
3. QA, Release, And Integration Agent starts P0-05 and P0-06.
4. TPM schedules Phase 1 contract review after Phase 0 skeletons exist.
