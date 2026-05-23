# Android Client Agent

## Mission

Build the Android-first thin client for Man Friday. This agent owns setup, encrypted local settings, backend REST/WebSocket integration, LiveKit audio connection, push-to-talk UX, latest-frame display, transcript/citations, status surfaces, and user-visible failure states.

The Android app should stay thin: it controls the session and audio experience while product state, GoPro control, retrieval, safety, and model calls remain on the Mac backend.

## Primary Responsibilities

- Create and maintain the Android project skeleton.
- Use Kotlin and Jetpack Compose for the MVP app.
- Implement the Setup/settings screen.
- Implement the Active Copilot screen.
- Store backend URL and local secret only after successful auth.
- Store the local secret using Android Keystore-backed encrypted storage.
- If encrypted storage fails, require the user to re-enter the secret instead of storing it insecurely.
- Implement REST client calls to the backend API.
- Implement authenticated WebSocket connection and reconnect behavior.
- Implement LiveKit Android SDK audio connection using backend-issued room tokens.
- Keep LiveKit scoped to audio transport only.
- Implement push-to-talk button semantics:
  - button down starts listening
  - button up stops listening/submits
  - max recording duration is 20 seconds
  - release before speech is detected discards the turn
- Render latest sampled frame, age, pinned state, and visual status.
- Render transcript entries with:
  - user speech text
  - assistant speech text
  - frame thumbnail/reference
  - citations/sources
  - safety warnings
  - errors
- Surface required UI states clearly:
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

## Owned Repository Areas

- `android/app/`
- `android/app/src/main/.../ui/setup/`
- `android/app/src/main/.../ui/copilot/`
- `android/app/src/main/.../data/`
- `android/app/src/main/.../domain/`
- `android/app/src/main/.../model/`
- Android unit and UI tests

## Required Interfaces

App layers:

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

Backend APIs consumed:

- `GET /health`
- `POST /session/start`
- `POST /session/end`
- `GET /session/status`
- `GET /gopro/status`
- `POST /gopro/start-preview`
- `POST /gopro/stop-preview`
- `POST /gopro/reconfigure`
- `POST /gopro/reconfigure/cancel`
- `POST /frame/look`
- `GET /frame/latest`
- `GET /frame/{frame_id}.jpg`
- `POST /retrieval/ingest`
- `POST /debug/mode`
- `GET /ws?session_id=<session_id>`

## Key Collaboration Points

- Coordinate API schemas and state snapshots with the backend control plane agent.
- Coordinate frame display, age, stale handling, and Look behavior with the GoPro/frame pipeline agent.
- Coordinate push-to-talk state, LiveKit behavior, and transcript events with the voice/model agent.
- Coordinate citation and safety rendering with the retrieval/safety agent.
- Coordinate acceptance testing with the QA/release integration agent.

## Implementation Phases

Phase 0:

- Android Compose app shell.
- Navigation between Setup and Active Copilot screens.

Phase 1:

- Backend health/auth check.
- Secure storage.
- Session start/end/status.
- WebSocket connect/reconnect.
- LiveKit connection using issued token.

Phase 2:

- GoPro controls.
- Latest-frame metadata and image display.
- Visual status and Look button.

Phase 3:

- Push-to-talk control.
- Listening/thinking/speaking UI.
- Transcript rendering.

Phase 4 and later:

- Citation rendering.
- Web-search-used indication.
- Safety warning rendering.
- Debug toggle and error states.

## Test Responsibilities

- Setup screen with mocked backend health and auth responses.
- Secure settings success and failure behavior.
- Session start/end and reconnect state transitions.
- WebSocket event reduction into UI state.
- Latest frame rendering from mocked image responses.
- Push-to-talk state transitions and 20-second limit.
- Transcript, citation, frame reference, safety warning, and error rendering.

## Acceptance Criteria

- Android authenticates to the Mac backend with the shared local secret.
- Android joins a local LiveKit room using the backend-issued token.
- The app can start and end a session explicitly.
- The app can start/stop GoPro preview from backend controls.
- Latest frame and age render normally while stream is healthy.
- The app can recover from backend/WebSocket reconnect.
- The user can ask a spoken question with hold-to-talk and see/hear the response.
- Secrets are never stored outside encrypted storage.

## Non-Goals

- Do not store OpenAI, Tavily, LiveKit API secrets, or model credentials on Android.
- Do not implement Android camera capture for MVP.
- Do not implement direct Android GoPro control for MVP.
- Do not add iPhone support.
