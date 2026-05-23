# GoPro And Frame Pipeline Agent

## Mission

Build the visual input path for Man Friday. This agent owns GoPro control, COHN credential reuse and reconfiguration, UDP preview startup, `ffmpeg` frame sampling, latest-frame cache, Look/pinned-frame semantics, visual degradation detection, and frame APIs.

The product depends on this agent to turn the supported GoPro into a reliable, low-latency stream of analysis-ready JPEG frames without sending continuous raw video to the model.

## Primary Responsibilities

- Implement the `GoProService` wrapper around the validated MVP path:
  - camera serial suffix `2312`
  - `open-gopro==0.22.0`
  - COHN credentials
  - UDP preview stream
- Store and reuse COHN credentials locally on the Mac.
- Never silently delete or replace saved credentials.
- Implement explicit reconfigure confirmation and cancellation behavior.
- Implement idempotent GoPro start-preview and stop-preview behavior.
- Decode the GoPro UDP preview stream using an `ffmpeg` subprocess.
- Sample frames at the configured target of 2 FPS.
- Produce JPEGs at approximately quality 80.
- Keep latest frame, pinned frame, and active transcript frames in memory by default.
- Detect and publish degraded visual states:
  - `ffmpeg` process exit
  - no sampled frame for more than 5 seconds
  - GoPro unreachable
  - credentials missing or reconfigure required
- Implement question-time frame selection:
  - use active pinned Look frame first
  - else use latest frame if age is `<= 2s`
  - else wait up to `1s`
  - else proceed without visual input
- Implement debug-mode handoff for frames used for analysis.

## Owned Repository Areas

- `backend/manfriday/gopro/`
- `backend/manfriday/frames/`
- `backend/tests/fixtures/` for fixture JPEGs and video/UDP-like samples
- frame-related backend API routes
- hardware validation scripts or checklists for the supported GoPro

## Required Interfaces

GoPro service interface:

```text
GoProService
  get_status() -> GoProStatus
  start_preview() -> GoProStatus
  stop_preview() -> GoProStatus
  reconfigure(confirm_clear_credentials: bool) -> ReconfigureJob
  cancel_reconfigure() -> ReconfigureStatus
```

REST endpoints:

- `GET /gopro/status`
- `POST /gopro/start-preview`
- `POST /gopro/stop-preview`
- `POST /gopro/reconfigure`
- `POST /gopro/reconfigure/cancel`
- `POST /frame/look`
- `GET /frame/latest`
- `GET /frame/{frame_id}.jpg`

Events:

- `gopro.status.changed`
- `frame.latest.updated`
- `frame.pinned`
- `gopro.reconfigure.started`
- `gopro.reconfigure.progress`
- `gopro.reconfigure.completed`
- `gopro.reconfigure.failed`
- `gopro.reconfigure.cancelled`

## Key Collaboration Points

- Use backend auth, session, event, and error helpers from the backend control plane agent.
- Provide exact frame IDs and metadata to the voice/model agent for model requests and transcripts.
- Provide latest frame metadata and JPEG URLs to the Android client agent.
- Provide debug frame artifacts to the retrieval/safety/debug owner only when debug mode is enabled.
- Coordinate hardware validation expectations with the QA/release integration agent.

## Implementation Phases

Phase 2 is this agent's main delivery phase:

- Define GoPro status and error models.
- Implement COHN credential DB path/config loading.
- Implement idempotent start/stop preview endpoint behavior.
- Build sampler against local fixture input first.
- Build sampler against real GoPro UDP preview stream.
- Add latest-frame cache and stale/degraded detection.
- Implement frame metadata/JPEG APIs.
- Implement Look pinning with 60-second TTL.
- Push `frame.latest.updated` over WebSocket at max 2 FPS while an active client is connected.

## Test Responsibilities

- GoPro status state transitions using fakes.
- Reconfigure confirmation behavior.
- Start/stop idempotency.
- Frame API with fixture JPEGs.
- Frame selector logic for pinned, fresh, stale, wait, and unavailable cases.
- Look TTL replacement and expiry.
- Sampler behavior with local fixture video or recorded UDP-like stream.
- Degraded visual state after sampler failure or stale frames.

## Acceptance Criteria

- Backend samples real GoPro frames at 2 FPS.
- Android can display the latest frame and age normally under 2 seconds.
- Look pins a frame for 60 seconds and follow-up turns use that frame.
- The frame used for analysis is the exact `frame_id` shown in transcript metadata.
- Visual degraded state appears within 5 seconds of sampler failure.
- Frame tests pass without physical GoPro hardware.

## Non-Goals

- Do not implement Android-side GoPro control for MVP.
- Do not stream continuous raw video to the model.
- Do not persist raw frames unless debug mode explicitly requires targeted analysis frames.
