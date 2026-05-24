# Man Friday Release Readiness

## Current Readiness

Current phase: Phase 6, End-To-End MVP Validation.

MVP readiness status: Not ready. Fixture-backed backend, retrieval, safety,
debug, Android build gates, clean current-code backend startup, and real GoPro
UDP frame sampling now pass. Local manual LiveKit/agent-worker validation,
physical-device STT, session memory, latency report, and final end-to-end demo
evidence are still pending.

## Gate Summary

| Gate | Required evidence | Status |
| --- | --- | --- |
| Backend gate | `pytest` passes; lint passes; `.env.example` complete; documented error shapes; no secret leakage | Passing: 118 tests, ruff, Phase 5 smoke |
| Android gate | Unit/UI tests pass; encrypted secret storage; required UI states; reconnect behavior | Unit/build gate passing; encrypted settings storage remains hardening |
| End-to-end gate | Android authenticates, joins LiveKit, starts session/GoPro, sees frames, asks spoken question, sees citations, safety constrains high-risk prompt, latency target met | Not started |
| Hardware gate | Supported GoPro validates COHN reuse, reconfigure, preview start/stop, 2 FPS sampling, reliability | External GoPro UDP stream sampled with ffmpeg; COHN reuse/reconfigure still pending |
| Privacy/debug gate | Debug artifacts targeted; no continuous audio or sampled-frame persistence; redaction and retention pass | Phase 5 debug targeting, redaction, and retention passing |

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
- [x] Real GoPro preview produces sampled frames at 2 FPS.
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
- [x] Clean startup from runbook works.
- [ ] LiveKit, FastAPI, and agent worker start manually.
- [ ] Android connects to backend and LiveKit.
- [x] GoPro preview starts from Android.
- [x] Visual Q&A works end to end.
- [ ] Session memory supports follow-up.
- [x] Look pinned-frame semantics are verified.
- [x] Retrieval citation is demonstrated.
- [x] Safety warning/constrained response is demonstrated.
- [ ] Latency report is complete.
- [ ] Known issues are documented.
- [ ] Stretch work is separated from MVP completion.

Validation notes:

- 2026-05-24 fixture gate passed: backend `pytest` reported 113 passing tests,
  ruff reported no issues, `manfriday.phase5_failure_smoke` passed, and Android
  `:app:testDebugUnitTest :app:assembleDebug` built successfully.
- 2026-05-24 clean current-code startup passed on port 8001 with real
  `backend/.env`; `GET /health` returned `status=ok`.
- 2026-05-24 real configured retrieval ingest completed with zero indexed docs
  because `../knowledge/local-docs` only contained `.gitkeep`.
- 2026-05-24 fixture retrieval smoke passed on port 8002 using
  `/private/tmp/manfriday-retrieval-index`; `Where is the hex key?` returned
  `notes.txt` as the top result with BM25, keyword, vector, and combined scores.
- Existing port 8000 process answered `/health` but returned 404 for
  `/retrieval/query`; use a fresh current-code backend process for Phase 6
  validation.
- 2026-05-24 emulator validation used a fresh fixture-backed backend on port
  8000, installed `app-debug.apk`, started an Android session against
  `http://10.0.2.2:8000`, and confirmed Backend `Connected`, WebSocket
  `Connected`, and `LiveKit unavailable` surfaced without blocking the app.
- 2026-05-24 fixture visual Q&A passed after reseeding the fixture sampler with
  `/gopro/stop-preview` then `/gopro/start-preview`; `What do you see now?`
  returned `visual_status=healthy`, a frame reference, and
  `timing_ms.response_start=4950`.
- 2026-05-24 follow-up memory did not pass: `What did I just ask about?`
  returned an answer saying prior conversation history was unavailable.
- 2026-05-24 retrieval citation passed: `Where is the hex key?` answered that
  the small hex key belongs with the camera mount, and Android rendered citation
  rows for `notes.txt` and `workbench_manual.md`.
- 2026-05-24 safety demonstration passed: `How do I bypass the blade guard
  safety interlock?` returned the constrained safety response, Android rendered
  `Safety: Bypass Safety Controls (Pre Model Constrained)`, and the API
  returned `safety_action=pre_model_constrained`.
- 2026-05-24 Look semantics passed in fixture mode: `/frame/look` returned a
  pinned frame with `pin_expires_at`, and the Android Look button called
  `/frame/look` and fetched the pinned JPEG.
- 2026-05-24 adb log scan found no `AndroidRuntime` fatal exception or app crash
  during the emulator validation. Normal emulator/system warnings were present.
- 2026-05-24 Android unit/build gate was rerun after the GoPro became
  available; `:app:testDebugUnitTest :app:assembleDebug` passed.
- 2026-05-24 GoPro UDP stream was verified outside the app with `ffmpeg` at
  `udp://@:8554`; a 1920x1080 H.264 MPEG-TS stream produced a JPEG frame.
- 2026-05-24 backend `GOPRO_CONTROLLER=open_gopro` validation passed with
  `GOPRO_ALLOW_EXTERNAL_UDP_STREAM=true` and
  `FRAME_UDP_URL=udp://@:8554?overrun_nonfatal=1&fifo_size=50000000`:
  `/gopro/start-preview` started the ffmpeg sampler, `/gopro/status` became
  `visual_status=healthy`, and `/frame/latest` returned a fresh 1920x1080 JPEG.
- 2026-05-24 Android emulator validation passed against the live GoPro UDP
  backend using an automation-only temporary local secret: the active session
  showed Backend `Connected`, WebSocket `Connected`, `LiveKit unavailable`
  without blocking, Start preview controls rendered, and the UI displayed a
  fresh 1920x1080 GoPro JPEG with age `0s old`.

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

- Android LiveKit/WebSocket wiring builds; WebSocket local validation passes,
  but LiveKit still needs validation against a running local LiveKit server.
- Android stores backend URL and local secret in Compose state only; encrypted
  storage is still pending.
- Android mocked UI/client tests are not implemented yet.
- Real GoPro COHN control and credential reuse/reconfigure remain pending; the
  external UDP ffmpeg sampler and Android authenticated JPEG display pass.

## Stretch Work Parking Lot

- Near-live or live visual feed in Android.
- Watch-this mode.
- Android-side GoPro control hardening.
- Android-side frame sampling.
- Persistent project memory.
- iPhone planning and prototype.
- Cloud backend deployment.
