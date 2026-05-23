# Man Friday Risk Register

## Summary

| Risk | Impact | Likelihood | Status | Owner | Next validation step |
| --- | --- | --- | --- | --- | --- |
| GoPro stream reliability | High | High | Active | GoPro And Frame Pipeline Agent | Build fixture sampler first, then run supported GoPro preview stability check |
| LiveKit push-to-talk semantics | High | Medium | Active | Voice And Model Agent | Prototype PTT before retrieval work |
| End-to-end latency | High | Medium | Active | Voice And Model Agent with QA | Add timing metrics in Phase 3 and measure release-to-response-start |
| Android secret handling | High | Medium | Active | Android Client Agent | Implement encrypted storage before persisting backend secret |
| Retrieval complexity | Medium | High | Active | Retrieval, Safety, And Debug Agent | Ship markdown/text ingestion first, then add PDF/vector/URL incrementally |
| Safety coverage | High | Medium | Active | Retrieval, Safety, And Debug Agent | Add explicit high-risk scenario tests before E2E acceptance |

## R-001: GoPro Stream Reliability

- Current status: Active.
- Impact: High. The visual copilot fails its core purpose if preview or frame sampling is unstable.
- Likelihood: High. UDP preview and `ffmpeg` process behavior are hardware/network sensitive.
- Mitigation plan: Build sampler restart/degraded-state logic early; keep fixture-based sampler tests; validate real GoPro only after fixture behavior is stable; preserve low-latency local preview workflow for diagnosis.
- Owner: GoPro And Frame Pipeline Agent.
- Supporting owners: QA, Release, And Integration Agent.
- Next validation step: Define fixture video or recorded UDP-like stream and frame sampler test before real hardware validation.

## R-002: LiveKit Push-To-Talk Semantics

- Current status: Active.
- Impact: High. Push-to-talk is the primary user interaction and must align Android UI, LiveKit audio, and agent processing.
- Likelihood: Medium. LiveKit audio plugins may naturally favor always-on or VAD-driven flows.
- Mitigation plan: Prototype push-to-talk before retrieval work; keep assistant state events explicit; use app events to gate agent processing if LiveKit audio controls are insufficient.
- Owner: Voice And Model Agent.
- Supporting owners: Android Client Agent and QA, Release, And Integration Agent.
- Next validation step: During Phase 1/3, prove a mock turn starts on button down, stops on button up, discards no-speech turns, and enforces the 20-second limit.

## R-003: End-To-End Latency

- Current status: Active.
- Impact: High. The PRD target is response start within 5 seconds after push-to-talk release under normal conditions.
- Likelihood: Medium. STT, frame selection, retrieval, vision model, and TTS can all add delay.
- Mitigation plan: Measure each stage from Phase 3 onward; bound frame wait to 1 second; apply retrieval timeouts; stream model/TTS when available; use mock providers to separate orchestration latency from provider latency.
- Owner: Voice And Model Agent.
- Supporting owners: QA, Release, And Integration Agent.
- Next validation step: Add timing metric schema for audio capture, STT, frame selection, retrieval, model first response, TTS start, and total release-to-response-start.

## R-004: Android Secret Handling

- Current status: Active.
- Impact: High. The shared local secret protects all backend APIs and debug endpoints.
- Likelihood: Medium. Storage fallback paths can accidentally persist secrets insecurely.
- Mitigation plan: Use Android Keystore-backed encrypted storage; persist credentials only after successful auth; if encrypted storage fails, require re-entry rather than insecure storage.
- Owner: Android Client Agent.
- Supporting owners: QA, Release, And Integration Agent.
- Next validation step: Add tests for secure settings success/failure and clear/reset behavior.

## R-005: Retrieval Complexity

- Current status: Active.
- Impact: Medium. Retrieval is required for grounded answers and citations, but full hybrid ingestion can slow the MVP if built all at once.
- Likelihood: High. PDF parsing, configured URL ingestion, BM25, FAISS, embeddings, source priority, and web fallback each add failure modes.
- Mitigation plan: Implement local markdown/text ingestion first; then PDF; then BM25; then embeddings/FAISS; then configured URLs; defer optional web fallback until local/configured retrieval is stable.
- Owner: Retrieval, Safety, And Debug Agent.
- Supporting owners: Voice And Model Agent and Android Client Agent.
- Next validation step: Define source/chunk schema and fixture local docs before implementation.

## R-006: Safety Coverage

- Current status: Active.
- Impact: High. The assistant may be used around electrical, gas, structural, tools, ladders, chemicals, and heat/fire hazards.
- Likelihood: Medium. Rule-based safety can miss variants or over-constrain benign requests.
- Mitigation plan: Keep deterministic backend checks and model prompt independent; start with explicit high-risk categories; add scenario tests; run post-model response validation before TTS/transcript finalization.
- Owner: Retrieval, Safety, And Debug Agent.
- Supporting owners: Voice And Model Agent and QA, Release, And Integration Agent.
- Next validation step: Create safety scenario fixtures covering each high-risk category and expected constraint level.

## Monitoring Cadence

- Review risks at the start and exit of each phase.
- Add a new risk when a phase contract review identifies a cross-agent uncertainty that could block integration.
- Close or downgrade risks only after fixture-backed tests and, where applicable, hardware validation evidence exists.
