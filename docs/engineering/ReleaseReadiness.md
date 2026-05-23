# Man Friday Release Readiness

## Current Readiness

Current phase: Phase 0, Repository And Development Baseline.

MVP readiness status: Not ready. Phase 0 backend skeleton, Android skeleton,
fixture strategy, and baseline backend and Android validation are in place.

## Gate Summary

| Gate | Required evidence | Status |
| --- | --- | --- |
| Backend gate | `pytest` passes; lint passes; `.env.example` complete; documented error shapes; no secret leakage | Phase 0 baseline passing |
| Android gate | Unit/UI tests pass; encrypted secret storage; required UI states; reconnect behavior | Phase 0 skeleton build passing |
| End-to-end gate | Android authenticates, joins LiveKit, starts session/GoPro, sees frames, asks spoken question, sees citations, safety constrains high-risk prompt, latency target met | Not started |
| Hardware gate | Supported GoPro validates COHN reuse, reconfigure, preview start/stop, 2 FPS sampling, reliability | Not started |
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

- [ ] REST bearer auth rejects missing, malformed, and wrong secrets.
- [ ] WebSocket auth rejects missing, malformed, and wrong secrets.
- [ ] `POST /session/start` returns session ID, LiveKit URL, room, token, expiry, and debug flag.
- [ ] `POST /session/end` clears live memory hooks and returns ended status.
- [ ] `GET /session/status` supports reconnect snapshot.
- [ ] LiveKit token issuance works with fake/local settings.
- [ ] Android starts session and joins returned LiveKit room.
- [ ] Android reconnect recovers state.

### Phase 2

- [ ] GoPro status and error models are implemented.
- [ ] Start/stop preview endpoints are idempotent.
- [ ] Reconfigure requires `confirm_clear_credentials: true`.
- [ ] Fixture frame sampler tests pass.
- [ ] Real GoPro preview produces sampled frames at 2 FPS.
- [ ] `/frame/latest` and `/frame/{frame_id}.jpg` work.
- [ ] `POST /frame/look` pins for 60 seconds.
- [ ] Android displays latest frame and frame age.
- [ ] Visual degraded state appears within 5 seconds of sampler failure.

### Phase 3

- [ ] STT, LLM, and TTS provider interfaces are defined.
- [ ] Mock provider orchestration tests pass.
- [ ] OpenAI-backed provider path works through config.
- [ ] Push-to-talk enforces button down/up and 20-second max recording duration.
- [ ] Release-before-speech discards turn.
- [ ] Transcript shows user text, assistant text, and frame reference.
- [ ] No-fresh-frame turn reports visual context unavailable.
- [ ] Response starts within 5 seconds under normal conditions.

### Phase 4

- [ ] Source/chunk metadata schema is implemented.
- [ ] Markdown/text ingestion passes fixture tests.
- [ ] PDF ingestion applies page and size limits.
- [ ] Configured URL ingestion uses YAML and reports per-source failures.
- [ ] BM25 index works.
- [ ] FAISS vector index persists locally.
- [ ] Merge/rerank applies local/manual source preference.
- [ ] Agent prompt includes retrieval context.
- [ ] Android renders citations.

### Phase 4a

- [ ] Web search is disabled by default.
- [ ] Tavily client respects timeout and max result config.
- [ ] Web fallback triggers only when enabled and appropriate.
- [ ] Web-used turns are labeled in transcript.
- [ ] Web citations include title, URL, snippet, provider rank, and retrieved timestamp.

### Phase 5

- [ ] High-risk category tests pass.
- [ ] Pre-model and post-model safety checks are active.
- [ ] Debug mode endpoint requires auth.
- [ ] Debug artifacts save only targeted session data.
- [ ] Redaction tests prove secrets are stripped.
- [ ] Timing metrics exist for each turn stage.
- [ ] Required Android UI states are reachable.
- [ ] Scripted failure cases pass.

### Phase 6

- [ ] Clean startup from docs works.
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

- Implementation has not started.
- No local startup commands exist yet.
- No backend, Android, fixture, hardware, or end-to-end validation evidence exists yet.

## Stretch Work Parking Lot

- Near-live or live visual feed in Android.
- Watch-this mode.
- Android-side GoPro control.
- Android-side frame sampling.
- Persistent project memory.
- iPhone planning and prototype.
- Cloud backend deployment.
