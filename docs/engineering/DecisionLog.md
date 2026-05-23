# Man Friday Decision Log

Decision records use this format:

- Date.
- Decision.
- Options considered.
- Rationale.
- Owner.
- Consequences.
- Revisit trigger.

## D-001: MVP Platform Boundary

- Date: 2026-05-23.
- Decision: Build Android-first with a Mac-hosted backend and self-hosted LiveKit. Defer iOS, cloud backend, and phone-side GoPro control.
- Options considered: Android-first local MVP; phone-only app; cloud-hosted backend; iOS parallel implementation.
- Rationale: The PRD targets hands-free DIY support on the user's current hardware, and local Mac hosting keeps GoPro control, frame sampling, secrets, and model/provider configuration backend-owned.
- Owner: Technical Program Manager.
- Consequences: Android remains thin; backend owns GoPro, retrieval, safety, model provider, and debug behavior. Release validation requires local Mac startup and Android device flow.
- Revisit trigger: MVP accepted and stretch planning begins.

## D-002: LiveKit Boundary

- Date: 2026-05-23.
- Decision: LiveKit carries audio only. REST and WebSocket carry product state.
- Options considered: LiveKit for audio only; LiveKit data channels for product state; REST polling only.
- Rationale: Keeping product state outside LiveKit simplifies reconnect behavior, API testability, Android state reduction, and backend ownership of auth/session/frame/retrieval/safety contracts.
- Owner: Technical Program Manager.
- Consequences: Backend must implement reliable REST/WebSocket contracts and snapshots. Android must maintain both LiveKit audio connection and backend state connection.
- Revisit trigger: LiveKit data-channel use becomes necessary for push-to-talk or latency after Phase 3 prototype.

## D-003: MVP GoPro Support Scope

- Date: 2026-05-23.
- Decision: Official MVP support is limited to camera serial suffix `2312` using `open-gopro==0.22.0`, COHN credentials, and UDP preview stream.
- Options considered: Support only validated GoPro path; attempt broader Open GoPro compatibility in MVP.
- Rationale: Hardware reliability is a key risk, and the PRD explicitly narrows MVP support to the validated path.
- Owner: Technical Program Manager.
- Consequences: Hardware validation checklist targets one camera path. Broader compatibility is documented as post-MVP stretch work.
- Revisit trigger: MVP demo succeeds repeatedly and additional camera models are available for validation.

## Open Decisions

| ID | Decision needed | Options under consideration | Owner | Needed by | Status |
| --- | --- | --- | --- | --- | --- |
| OD-001 | Final OpenAI STT model ID | Current OpenAI transcription model options | Voice And Model Agent | Phase 3 | Open |
| OD-002 | Final vision-capable LLM model ID | Current OpenAI vision-capable model options | Voice And Model Agent | Phase 3 | Open |
| OD-003 | Final OpenAI TTS model and voice | Current OpenAI speech model/voice options | Voice And Model Agent | Phase 3 | Open |
| OD-004 | Android networking stack | Retrofit + OkHttp WebSocket; Ktor HTTP + WebSocket | Android Client Agent | Phase 1 | Open |
| OD-005 | Exact LiveKit push-to-talk implementation | LiveKit client controls; app events gating agent processing; VAD with explicit state gate | Voice And Model Agent with Android Client Agent | Phase 3 prototype | Open |
| OD-006 | Source/chunk metadata persistence | SQLite; JSON files | Retrieval, Safety, And Debug Agent | Phase 4 | Open |
| OD-007 | Docker Compose timing | Add after manual startup works; add before Phase 5 hardening | QA, Release, And Integration Agent | Phase 6 | Open |
| OD-008 | Android WebSocket auth mechanism | Bearer header; short-lived backend-issued WebSocket token if headers fail | Backend Control Plane Agent with Android Client Agent | Phase 1 | Open |

## Decision Intake Queue

- Confirm backend dependency manager before package skeleton lands.
- Confirm Android minimum SDK and package namespace before app skeleton lands.
- Confirm local development document location.
- Confirm fixture artifact paths for JPEGs, video/UDP-like stream, mock model server, and Android mocked responses.
