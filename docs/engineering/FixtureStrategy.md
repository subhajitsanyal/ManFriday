# Man Friday Fixture Strategy

## Purpose

Hardware and provider dependencies must not block local validation. Fixtures
provide deterministic inputs for frame, LiveKit, model, retrieval, and Android
tests until the real integrations are available.

## Fixture Categories

### Backend health and config

- Settings tests construct `Settings` directly with test secrets.
- `.env` is not required for unit tests unless the test explicitly validates
  process startup.
- Secret values are asserted through `SecretStr` accessors and must not be
  logged or snapshotted.

### Frame pipeline

- Store JPEG fixtures under `backend/tests/fixtures/frames/`.
- Use at least:
  - `workbench_fresh.jpg`
  - `workbench_stale.jpg`
  - `look_pinned.jpg`
- Frame metadata fixtures must include `frame_id`, `captured_at`, dimensions,
  source, and pin expiry.
- Real GoPro tests stay manual or opt-in until CI has hardware access.

### LiveKit

- Token issuance tests should use deterministic fake API keys and secrets.
- Room join tests use a fake LiveKit client boundary first.
- End-to-end LiveKit server validation is a local integration gate, not a unit
  test requirement.

### Voice and model

- STT fixtures map short audio or text inputs to deterministic transcripts.
- LLM fixtures return deterministic assistant text plus timing metadata.
- TTS fixtures return placeholder audio bytes or a fake stream handle.
- Provider tests must run without OpenAI credentials by default.

### Retrieval

- Local retrieval fixtures live under `backend/tests/fixtures/retrieval/`.
- Include a small markdown source, a text source, and one unsupported file.
- Configured URL retrieval uses a local test server fixture before any internet
  access is introduced.
- Expected citations should assert source ID, title, URL/path, and chunk ID.

### Android

- UI state tests should use fake repositories for backend health, session start,
  LiveKit connection state, frame metadata, and transcript events.
- Instrumented tests should not require a real backend until Phase 1 integration.
- Manual emulator validation can target `http://10.0.2.2:8000`.

## Phase 0 Evidence

- Backend: `pytest` passes from `backend/`.
- Android: `./gradlew :app:assembleDebug` passes from `android/` once a JDK,
  Android SDK, and Gradle wrapper are available.
- Documentation: `README.md` lists startup and validation commands.

## Opt-In Integration Gates

Use explicit environment variables for tests that touch external systems:

- `MANFRIDAY_RUN_LIVEKIT_INTEGRATION=1`
- `MANFRIDAY_RUN_GOPRO_INTEGRATION=1`
- `MANFRIDAY_RUN_MODEL_INTEGRATION=1`
- `MANFRIDAY_RUN_RETRIEVAL_NETWORK=1`

Default test commands must skip these paths.
