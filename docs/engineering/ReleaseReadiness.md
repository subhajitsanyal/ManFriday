# Man Friday Release Readiness

## Current Readiness

Current phase: Phase 2, GoPro And Frame Pipeline.

MVP readiness status: Not ready. Phase 0 is complete, and the Phase 1 backend
control plane is in place. Android can start/end backend sessions, connect to
the returned LiveKit room, and open the authenticated WebSocket event stream.
Local manual LiveKit validation, real GoPro preview/sampler work, secure
settings storage, and Android tests are still pending.

## Gate Summary

| Gate | Required evidence | Status |
| --- | --- | --- |
| Backend gate | `pytest` passes; lint passes; `.env.example` complete; documented error shapes; no secret leakage | Phase 1 auth/session tests passing |
| Android gate | Unit/UI tests pass; encrypted secret storage; required UI states; reconnect behavior | LiveKit/WebSocket wiring implemented; secure storage and tests pending |
| End-to-end gate | Android authenticates, joins LiveKit, starts session/GoPro, sees frames, asks spoken question, sees citations, safety constrains high-risk prompt, latency target met | Not started |
| Hardware gate | Supported GoPro validates COHN reuse, reconfigure, preview start/stop, 2 FPS sampling, reliability | Fixture frame API passing; real hardware not started |
| Privacy/debug gate | Debug artifacts targeted; no continuous audio or sampled-frame persistence; redaction and retention pass | Not started |

## Phase Exit Checklist

### Phase 0

- [x] Backend package skeleton exists.
- [x] Backend starts locally.
- [x] `GET /health` returns documented service status.
- [x] Android skeleton builds.
- [x] `.env.example` includes all required config keys.
- [x] Local startup and test commands are documented.
- [x] Baseline config/health tests pass.

### Phase 1

- [x] REST bearer auth rejects missing, malformed, and wrong secrets.
- [x] WebSocket auth rejects missing, malformed, and wrong secrets.
- [x] `POST /session/start` returns session ID, LiveKit URL, room, token, expiry, and debug flag.
- [x] `POST /session/end` clears live memory hooks and returns ended status.
- [x] `GET /session/status` supports reconnect snapshot.
- [x] LiveKit token issuance works with fake/local settings.
- [x] Android starts session and joins returned LiveKit room.
- [x] Android reconnect recovers state.

### Phase 2

- [x] GoPro status and error models are implemented.
- [x] Backend GoPro controller boundary exists with fixture and Open GoPro skeletons.
- [x] Start/stop preview endpoints are idempotent.
- [x] Reconfigure requires `confirm_clear_credentials: true`.
- [x] Fixture frame sampler tests pass.
- [ ] Real GoPro preview produces sampled frames at 2 FPS.
- [x] `/frame/latest` and `/frame/{frame_id}.jpg` work.
- [x] `POST /frame/look` pins for 60 seconds.
- [x] Android displays latest frame image, metadata, and age.
- [x] Fixture visual degraded state appears within 5 seconds of sampler failure.

### Phase 3

- [x] STT, LLM, and TTS provider interfaces are defined.
- [x] Mock provider orchestration tests pass.
- [x] OpenAI-backed provider adapters are implemented behind config.
- [x] AWS Bedrock Claude provider adapter is implemented behind config.
- [x] Live AWS Bedrock Claude provider path is validated with shared AWS credentials.
- [x] Final STT/TTS provider path is selected for MVP as Android-native STT/TTS.
- [x] Backend push-to-talk enforces button down/up and 20-second max recording duration.
- [x] Backend release-before-speech discards turn.
- [x] Android sends recognized text to backend on push-to-talk release.
- [x] Android speaks final assistant text with native TTS.
- [x] Android transcript shows user text, assistant text, and frame reference.
- [x] Backend no-fresh-frame turn reports visual context unavailable.
- [x] Backend emits `response_start` and `total` timing for voice turns.
- [x] Android emulator typed Ask validates backend, Bedrock, transcript, and TTS.
- [ ] Android physical-device STT validates spoken push-to-talk.
- [x] Response starts within 5 seconds in configured Bedrock smoke: 2217 ms.

### Phase 4

- [x] Source/chunk metadata schema is implemented.
- [x] Markdown/text ingestion passes fixture tests.
- [x] `manfriday ingest` builds local Markdown/text metadata.
- [x] `POST /retrieval/ingest` returns authenticated per-source summary.
- [x] BM25/keyword index works for ingested Markdown/text chunks.
- [x] Authenticated `POST /retrieval/query` returns ranked chunks.
- [x] Local/manual source preference is covered for ranked chunk ties.
- [x] Agent prompt includes retrieval context for local Markdown/text chunks.
- [x] Push-to-talk responses and transcript events include citation references.
- [x] Android renders local Markdown/text citation references in assistant transcript rows.
- [x] Configured URL ingestion uses YAML and reports per-source failures.
- [x] PDF ingestion applies page and size limits.
- [x] Source/chunk metadata index persists locally under `RETRIEVAL_INDEX_DIR`.
- [x] Lightweight vector-style sidecar index persists locally under `RETRIEVAL_INDEX_DIR`.
- [x] Merge/rerank applies local/manual source preference.

### Phase 4a

- [ ] Web search is disabled by default.
- [ ] Tavily client respects timeout and max result config.
- [ ] Web fallback triggers only when enabled and appropriate.
- [ ] Web-used turns are labeled in transcript.
- [ ] Web citations include title, URL, snippet, provider rank, and retrieved timestamp.

### Phase 5

- [x] High-risk category tests pass.
- [x] Retrieval low-confidence response policy is active.
- [x] Retrieval debug artifacts save targeted session data.
- [x] Post-model low-confidence procedural/tool instruction guard is active.
- [x] Pre-model and post-model high-risk safety checks are active.
- [x] Debug artifact endpoints require auth.
- [x] Debug artifacts save only targeted session data.
- [x] Redaction tests prove secrets are stripped.
- [x] Timing metrics exist for each turn stage.
- [x] Required Android UI states are reachable in tests/mocks.
- [x] Scripted fixture failure cases pass with `manfriday.phase5_failure_smoke`.

### Phase 6

- [x] Phase 6 local validation runbook exists.
- [ ] Clean startup from runbook works.
- [ ] LiveKit, FastAPI, and agent worker start manually.
- [ ] Android connects to backend and LiveKit.
- [ ] GoPro preview starts from Android.
- [ ] Visual Q&A works end to end.
- [ ] Session memory supports follow-up.
- [ ] Look pinned-frame semantics are verified.
- [ ] Retrieval citation is demonstrated.
- [ ] Safety warning/constrained response is demonstrated.
- [ ] Latency report is complete.
- [ ] Known issues are documented.
- [ ] Stretch work is separated from MVP completion.

## Fixture Strategy

Required fixtures before hardware-only validation:

- Fixture JPEGs for latest frame, stale frame, pinned frame, and transcript frame references.
- Local video or recorded UDP-like stream for sampler behavior.
- Fake LiveKit settings for token issuance tests.
- Mock OpenAI-compatible server or provider doubles for STT, LLM, and TTS.
- Fixture markdown, text, PDF, and local HTTP URL sources for retrieval.
- Mock Tavily responses for optional web fallback.
- Mocked Android backend responses for setup, session, WebSocket state, frames, transcript, citations, and errors.

## Latency Targets

| Metric | Target |
| --- | --- |
| Backend health visible after URL/secret entry | <= 2 seconds |
| GoPro start-preview with valid credentials | success or clear failure within 15 seconds |
| Healthy latest frame age | normally under 2 seconds |
| Push-to-talk max recording duration | 20 seconds |
| Frame selection additional wait | <= 1 second |
| Quick Q&A response start after release | <= 5 seconds under normal conditions |
| Visual degraded after sampler/stream drop | <= 5 seconds |

## Known Issues

- Android LiveKit/WebSocket wiring builds but still needs local manual validation
  against a running LiveKit server and backend.
- Android stores backend URL and local secret in Compose state only; encrypted
  storage is still pending.
- Android mocked UI/client tests are not implemented yet.
- Real GoPro COHN control, `ffmpeg` sampler, Android authenticated JPEG display,
  model, retrieval, safety, debug, hardware, and end-to-end validation have not
  started.

## Stretch Work Parking Lot

- Near-live or live visual feed in Android.
- Watch-this mode.
- Android-side GoPro control.
- Android-side frame sampling.
- Persistent project memory.
- iPhone planning and prototype.
- Cloud backend deployment.
