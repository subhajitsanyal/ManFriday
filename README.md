# Man Friday

Man Friday is a hands-free visual copilot for DIY work. The system uses a GoPro
as a workbench camera, an Android app for voice interaction, a self-hosted
LiveKit stack for realtime conversation, and a Mac backend for GoPro control,
frame sampling, retrieval, and OpenAI-compatible model calls.

## Repository Layout

```text
ManFriday/
  android/                    Android app source will live here.
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

The current focus is Phase 0: repository and development baseline. The backend
package skeleton, typed config, unauthenticated health endpoint, Android Compose
skeleton, and fixture strategy are now in place.

Existing GoPro exploration code has been moved to:

```text
../MiscExplorations/
```

The implementation priority is the Phase 0 baseline first, then auth/session and
LiveKit token control plane, followed by the GoPro/frame pipeline.

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

## Fixture Strategy

The non-hardware validation plan is documented in
`docs/engineering/FixtureStrategy.md`. Default tests must not require a GoPro,
LiveKit server, model credentials, or internet access.
