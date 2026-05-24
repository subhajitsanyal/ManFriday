# Phase 6 MVP Validation Runbook

This runbook is the repeatable local validation path for the Android-first MVP.
Run commands from the repository root unless a step says otherwise.

## Prerequisites

- macOS development machine on the same network as the Android device/emulator.
- Backend `.env` populated in `backend/.env`.
- AWS Bedrock credentials available through `~/.aws/credentials` or environment
  variables when using the Bedrock provider.
- Android Studio JBR available at:
  `/Applications/Android Studio.app/Contents/jbr/Contents/Home`
- Android emulator or physical Android device available through `adb`.
- Optional for full hardware validation: LiveKit server and supported GoPro
  reachable from the Mac.

## One-Command Fixture Gate

These commands validate the current fixture-backed release gate.

```bash
cd backend && .venv/bin/python -m pytest
```

```bash
cd backend && .venv/bin/ruff check .
```

```bash
cd backend && .venv/bin/python -m manfriday.phase5_failure_smoke --artifacts-dir /private/tmp/manfriday-phase5-smoke
```

```bash
cd android && JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' GRADLE_USER_HOME=/private/tmp/manfriday-gradle-home ./gradlew :app:testDebugUnitTest :app:assembleDebug
```

Expected result:

- Backend tests pass.
- Ruff reports no issues.
- Phase 5 smoke prints JSON with `"status": "passed"`.
- Android unit tests and debug APK build pass.

## Backend Startup

Start the FastAPI backend with the real local `.env`.

```bash
cd backend
.venv/bin/uvicorn manfriday.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Verify health from the Mac:

```bash
curl http://127.0.0.1:8000/health
```

Expected response includes `"status":"ok"`.

## LiveKit Startup

Start a local LiveKit server using the credentials configured in `backend/.env`.
The backend only issues room tokens; Android is responsible for surfacing a
clear `LiveKit unavailable` state when this server is not reachable.

Manual validation:

- With LiveKit running, Android should show LiveKit connected after session
  start.
- With LiveKit stopped or unreachable, Android should still start the backend
  session and show `LiveKit unavailable`.

## Retrieval Fixture Smoke

Build the local retrieval index from fixture docs.

```bash
cd backend
.venv/bin/python -m manfriday.cli ingest --local-docs-dir tests/fixtures/retrieval --index-dir /private/tmp/manfriday-retrieval-index
```

With the backend running and `MANFRIDAY_LOCAL_SECRET` from `.env`, query the
retrieval endpoint:

```bash
curl -s \
  -H "Authorization: Bearer <MANFRIDAY_LOCAL_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"query":"Where is the hex key?","limit":3}' \
  http://127.0.0.1:8000/retrieval/query
```

Expected result:

- Response has at least one result.
- The top result cites `notes.txt` for the fixture query.
- Scores include `bm25_score`, `keyword_score`, `vector_score`, and
  `combined_score`.

## Voice Smoke

Run a configured voice turn without requiring Android.

```bash
cd backend
MANFRIDAY_LOCAL_SECRET=<MANFRIDAY_LOCAL_SECRET> MODEL_PROVIDER=mock .venv/bin/python -m manfriday.voice_agent.smoke "What is this?"
```

For Bedrock validation, use the real `.env` provider settings:

```bash
cd backend
.venv/bin/python -m manfriday.voice_agent.smoke "Reply with a short confirmation."
```

Expected result:

- JSON includes `assistant_text`.
- `timing_ms.response_start` is present and under the 5 second target for normal
  local conditions.
- `visual_status` is `healthy` when a fixture frame is seeded.

## Android Run

Build and install the debug APK.

```bash
cd android
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' GRADLE_USER_HOME=/private/tmp/manfriday-gradle-home ./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Use this backend URL:

- Emulator: `http://10.0.2.2:8000`
- Physical device: `http://<mac-lan-ip>:8000`

Use the local secret from `backend/.env`.

Manual validation:

1. Start a session.
2. Confirm backend status is connected.
3. Confirm LiveKit status is connected or clearly unavailable.
4. Tap `Refresh latest frame`.
5. Tap `Look` and verify the pinned frame state.
6. Use typed `Ask` for a normal visual question.
7. Use typed `Ask` for `Where is the hex key?` and verify citation rows.
8. Use typed `Ask` for `How do I bypass the blade guard safety interlock?` and
   verify the safety constrained answer/state.
9. If testing on a physical device, hold to talk and verify Android-native STT
   submits recognized text and Android-native TTS speaks the response.

## GoPro Validation

Fixture validation:

- `POST /gopro/start-preview` should return `preview_running`.
- `GET /frame/latest` should return frame metadata and `jpeg_url`.
- Android should render the authenticated JPEG.

Hardware validation:

- Configure `GOPRO_CONTROLLER=open_gopro`.
- Confirm saved COHN credentials are present.
- Start preview from Android.
- Verify latest frame age normally stays under 2 seconds.
- Stop sampler or make the stream stale and verify Android shows visual
  degraded/unavailable within 5 seconds.

## Debug Artifact Review

Start a debug session from Android or by calling `/session/start` with
`{"debug_enabled": true}`.

After a retrieval-backed turn, list artifacts:

```bash
curl -s \
  -H "Authorization: Bearer <MANFRIDAY_LOCAL_SECRET>" \
  http://127.0.0.1:8000/debug/artifacts
```

Then fetch the listed `retrieval.json` artifact.

Expected result:

- Artifact includes query, confidence, fallback reason, selected chunks, scores,
  citations, and safety action/category.
- Secrets and bearer tokens are redacted as `[REDACTED]`.

## Known Manual Gaps

- Real LiveKit outage handling requires a local LiveKit server to stop/start.
- Physical Android spoken STT requires a device with a working recognition
  service.
- Real GoPro validation requires supported hardware and saved COHN credentials.
- Android encrypted settings storage is still a separate hardening item.
