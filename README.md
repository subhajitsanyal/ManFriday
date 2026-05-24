# Man Friday

Man Friday is a hands-free visual copilot for DIY work. The system uses a GoPro
as a workbench camera, an Android app for voice interaction, a self-hosted
LiveKit stack for realtime conversation, and a Mac backend for GoPro control,
frame sampling, retrieval, and OpenAI-compatible model calls.

## Repository Layout

```text
ManFriday/
  android/                    Android app source and Compose UI.
  backend/                    Mac backend, LiveKit agent, GoPro/frame pipeline.
  docs/
    product/                  PRD and product decisions.
    engineering/              Architecture/specs/API contracts.
    research/                 Framework notes and implementation research.
  knowledge/
    local-docs/               User-provided manuals, notes, PDFs, etc.
    online-sources/           Lists/config for trusted online resources.
```

## Current Status

The current focus is Phase 1: auth, sessions, events, and LiveKit token control
plane. The backend now has bearer-protected session APIs, in-memory session
state, fake/local LiveKit token issuance, a bounded WebSocket event bus, and a
worker entrypoint. The Android setup screen can start and end backend sessions
and display the returned LiveKit room.

Existing GoPro exploration code has been moved to:

```text
../MiscExplorations/
```

The current implementation priority is Phase 2: GoPro and frame pipeline. A
fixture-backed backend frame API and sampler boundary are in place, including
Look pinning, reconfigure confirmation scaffolding, and degraded-state handling.
The backend also has a GoPro controller boundary with fixture and Open GoPro
skeleton implementations. The Android active screen can refresh and render the
authenticated latest JPEG. The next steps are real Open GoPro connection and
preview control, UDP preview sampling, and local hardware validation.

## Backend Local Development

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn manfriday.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
```

Verify health:

```bash
curl http://localhost:8000/health
```

Run backend tests:

```bash
cd backend
pytest
```

Run the backend worker skeleton:

```bash
cd backend
manfriday-agent
```

## Android Local Development

Prerequisites:

- JDK 17.
- Android SDK with API 36.
- Android Studio or another JDK 17+ installation.

From the repository root:

```bash
cd android
./gradlew :app:assembleDebug
```

If the shell cannot find a system Java runtime but Android Studio is installed,
use its bundled JDK:

```bash
cd android
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:assembleDebug
```

The emulator default backend URL is `http://10.0.2.2:8000`. A physical Android
device should use the Mac's LAN IP address and port `8000`.

The Android app sends `Authorization: Bearer <local-secret>` to the session REST
APIs, opens `/ws?session_id=<id>` with the same bearer secret, and connects to
the returned LiveKit room/token for audio. Cleartext HTTP is enabled for the
local MVP network path.

## Frame API Smoke

With the backend running and `MANFRIDAY_LOCAL_SECRET` set:

```bash
curl -H "Authorization: Bearer <secret>" -X POST http://localhost:8000/gopro/start-preview
curl -H "Authorization: Bearer <secret>" http://localhost:8000/frame/latest
curl -H "Authorization: Bearer <secret>" -X POST http://localhost:8000/frame/look
```

The current preview path seeds a deterministic fixture frame. Real GoPro COHN
control and UDP sampling are still pending Phase 2 work.

## Fixture Strategy

The non-hardware validation plan is documented in
`docs/engineering/FixtureStrategy.md`. Default tests must not require a GoPro,
LiveKit server, model credentials, or internet access.
