# Backend Control Plane Agent

## Mission

Build the FastAPI control plane that all other Man Friday components depend on. This agent owns backend startup, configuration, shared-secret authentication, session lifecycle, LiveKit token issuance, typed events, WebSocket fanout, and the public REST contract described in the PRD and engineering spec.

The goal is to make the backend predictable, testable, and safe to run locally on the user's Mac before hardware, model, or Android complexity is layered on top.

## Primary Responsibilities

- Create and maintain the `backend/manfriday` Python package skeleton.
- Implement typed configuration loading with `pydantic-settings`.
- Validate required `.env` values at startup and keep `.env.example` complete.
- Implement `GET /health` as the only unauthenticated endpoint.
- Implement bearer-token auth using `Authorization: Bearer <MANFRIDAY_LOCAL_SECRET>`.
- Ensure auth failures never log user-provided secrets.
- Implement in-memory MVP sessions:
  - start
  - resume where appropriate
  - status
  - explicit end
  - idle expiration
  - activity updates
- Implement LiveKit room naming and token issuance after successful auth.
- Implement the typed event bus and WebSocket fanout.
- Provide current status snapshots to WebSocket clients after reconnect.
- Enforce bounded WebSocket client queues and drop slow clients cleanly.
- Standardize API error responses with the documented common error shape.

## Owned Repository Areas

- `backend/manfriday/config/`
- `backend/manfriday/auth/`
- `backend/manfriday/api/`
- `backend/manfriday/sessions/`
- `backend/manfriday/events/`
- `backend/manfriday/livekit/`
- `backend/tests/` for owned unit and integration tests
- `backend/.env.example`
- local backend startup documentation

## Required Interfaces

REST endpoints:

- `GET /health`
- `POST /session/start`
- `POST /session/end`
- `GET /session/status`

WebSocket endpoint:

- `GET /ws?session_id=<session_id>`

Core event envelope:

```json
{
  "event_id": "evt_...",
  "type": "session.status.changed",
  "session_id": "sess_...",
  "timestamp": "2026-05-23T20:15:01.123Z",
  "payload": {}
}
```

## Key Collaboration Points

- Provide authenticated service dependencies for the GoPro/frame agent, retrieval/safety agent, and debug endpoints.
- Provide LiveKit room and token details to the Android client agent.
- Provide event publishing APIs for all backend modules.
- Provide session state and memory hooks to the voice/model agent.
- Coordinate API schemas with the Android client agent before endpoint behavior changes.

## Implementation Phases

Phase 0:

- Backend package skeleton.
- Config model.
- `.env.example`.
- `GET /health`.
- First config and health tests.

Phase 1:

- Auth dependency/middleware.
- Session store.
- Session APIs.
- LiveKit token service.
- WebSocket event bus.
- Agent worker skeleton integration point.

Later phases:

- Add status fields required by GoPro, frame, voice, retrieval, safety, and debug modules.
- Keep cross-module failure states visible to Android through snapshots and events.

## Test Responsibilities

- Config parsing and required variable validation.
- Health endpoint behavior.
- Shared-secret auth success and failure.
- Session start/end/status and idle expiration.
- LiveKit token issuance with fake LiveKit settings.
- WebSocket auth, reconnect, snapshot, fanout, and slow-client handling.
- Common error serialization.

## Acceptance Criteria

- Backend starts locally with documented commands.
- `pytest` passes for owned tests.
- All protected REST and WebSocket routes reject missing, malformed, or wrong bearer tokens.
- Session expiration emits `session.expired` and clears live session memory hooks.
- Android can start a session and receive LiveKit connection details.
- No secret values appear in logs, errors, events, or debug artifacts.

## Non-Goals

- Do not implement GoPro control, frame sampling, retrieval ranking, model calls, or Android UI.
- Do not introduce internet-exposed auth or multi-user auth for MVP.
- Do not persist sessions beyond in-memory MVP state unless a later requirement changes the architecture.
