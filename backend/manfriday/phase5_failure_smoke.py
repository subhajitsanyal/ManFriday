import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.config.settings import Settings
from manfriday.events import EventBus
from manfriday.frames import FrameStore
from manfriday.retrieval import RetrievalContextBuilder
from manfriday.voice_agent import (
    AudioInput,
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    ModelTurnRequest,
    VoiceTurnError,
    VoiceTurnOrchestrator,
)

LOCAL_SECRET = "phase5-secret"


@dataclass(frozen=True)
class FailureSmokeCheck:
    name: str
    status: str
    details: str


def run_phase5_failure_smoke(artifacts_dir: Path | None = None) -> dict:
    if artifacts_dir is not None:
        return _run_phase5_failure_smoke(artifacts_dir)
    with TemporaryDirectory(prefix="manfriday-phase5-") as temp_dir:
        return _run_phase5_failure_smoke(Path(temp_dir))


def summarize_checks(checks: list[FailureSmokeCheck]) -> str:
    return "passed" if all(check.status == "passed" for check in checks) else "failed"


def _run_phase5_failure_smoke(artifacts_dir: Path) -> dict:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    checks = [
        _check_backend_health(),
        _check_session_reconnect_snapshot(),
        _check_websocket_disconnect_reconnect(),
        _check_livekit_unavailable_surface(),
        _check_stale_frame_degraded(),
        _check_gopro_unavailable(artifacts_dir),
        _check_model_timeout_path(),
        _check_retrieval_low_confidence(artifacts_dir),
        _check_debug_artifact_redaction(artifacts_dir),
    ]
    return {
        "status": summarize_checks(checks),
        "artifact_dir": str(artifacts_dir),
        "checks": [asdict(check) for check in checks],
    }


def _check_backend_health() -> FailureSmokeCheck:
    client = TestClient(create_app(_settings()))
    response = client.get("/health")
    _require(response.status_code == 200, f"health returned {response.status_code}")
    _require(response.json()["status"] == "ok", "health status was not ok")
    return FailureSmokeCheck("backend_health", "passed", "GET /health returned ok.")


def _check_session_reconnect_snapshot() -> FailureSmokeCheck:
    client = TestClient(create_app(_settings()))
    start = client.post("/session/start", headers=_headers(), json={}).json()
    response = client.get(
        "/session/status",
        headers=_headers(),
        params={"session_id": start["session_id"]},
    )
    _require(response.status_code == 200, f"status returned {response.status_code}")
    _require(response.json()["status"] == "active", "session was not active")
    return FailureSmokeCheck(
        "session_reconnect_snapshot",
        "passed",
        "GET /session/status returns an active reconnect snapshot.",
    )


def _check_websocket_disconnect_reconnect() -> FailureSmokeCheck:
    client = TestClient(create_app(_settings()))
    start = client.post("/session/start", headers=_headers(), json={}).json()
    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=_headers(),
    ) as websocket:
        _require(websocket.receive_json()["type"] == "session.status.changed", "missing snapshot")
    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=_headers(),
    ) as websocket:
        event = websocket.receive_json()
    _require(event["payload"]["status"] == "active", "reconnect did not return active status")
    return FailureSmokeCheck(
        "websocket_disconnect_reconnect",
        "passed",
        "Disconnected WebSocket can reconnect and receive a session snapshot.",
    )


def _check_livekit_unavailable_surface() -> FailureSmokeCheck:
    client = TestClient(
        create_app(_settings(LIVEKIT_URL="ws://unavailable-livekit.test:7880")),
    )
    response = client.post("/session/start", headers=_headers(), json={})
    _require(response.status_code == 200, f"session start returned {response.status_code}")
    _require(
        response.json()["livekit"]["url"] == "ws://unavailable-livekit.test:7880",
        "session response did not surface configured LiveKit URL",
    )
    return FailureSmokeCheck(
        "livekit_unavailable_surface",
        "passed",
        "Session start surfaces the configured LiveKit URL for Android unavailable-state handling.",
    )


def _check_stale_frame_degraded() -> FailureSmokeCheck:
    app = create_app(_settings())
    client = TestClient(app)
    client.post("/gopro/start-preview", headers=_headers())
    latest = app.state.frame_store.latest()
    latest.captured_at = datetime.now(UTC) - timedelta(seconds=60)
    response = client.get("/frame/latest", headers=_headers())
    _require(response.status_code == 200, f"latest frame returned {response.status_code}")
    _require(response.json()["visual_status"] == "degraded", "visual status was not degraded")
    return FailureSmokeCheck(
        "stale_frame_degraded",
        "passed",
        "Stale fixture frame reports visual_status=degraded.",
    )


def _check_gopro_unavailable(artifacts_dir: Path) -> FailureSmokeCheck:
    client = TestClient(
        create_app(
            _settings(
                GOPRO_CONTROLLER="open_gopro",
                GOPRO_COHN_CREDENTIALS_PATH=artifacts_dir / "missing-cohn.json",
            ),
        ),
    )
    status = client.get("/gopro/status", headers=_headers())
    start = client.post("/gopro/start-preview", headers=_headers())
    _require(status.json()["visual_status"] == "unavailable", "GoPro was not unavailable")
    _require(start.json()["status"] == "reconfigure_required", "GoPro did not require reconfigure")
    return FailureSmokeCheck(
        "gopro_unavailable",
        "passed",
        "Open GoPro fixture without credentials reports unavailable/reconfigure-required.",
    )


def _check_model_timeout_path() -> FailureSmokeCheck:
    async def run_turn() -> list:
        event_bus = EventBus(queue_limit=16)
        queue = event_bus.subscribe("sess_timeout")
        orchestrator = VoiceTurnOrchestrator(
            stt_provider=MockSpeechToTextProvider(),
            model_provider=_TimeoutModelProvider(),
            tts_provider=MockTextToSpeechProvider(),
            frame_store=FrameStore(look_ttl_seconds=60, stale_after_seconds=5),
            event_bus=event_bus,
        )
        try:
            await orchestrator.run_turn(
                session_id="sess_timeout",
                audio=AudioInput(content=b"audio"),
            )
        except VoiceTurnError:
            pass
        return [queue.get_nowait() for _ in range(queue.qsize())]

    events = asyncio.run(run_turn())
    _require(events[-1].type == "assistant.error", "last event was not assistant.error")
    _require(events[-1].payload["code"] == "model_failed", "model timeout was not model_failed")
    _require(events[-1].payload["retryable"] is True, "model timeout was not retryable")
    return FailureSmokeCheck(
        "model_timeout",
        "passed",
        "Model timeout path emits retryable model_failed.",
    )


def _check_retrieval_low_confidence(artifacts_dir: Path) -> FailureSmokeCheck:
    docs = artifacts_dir / "retrieval-docs"
    docs.mkdir(exist_ok=True)
    (docs / "manual.txt").write_text("The hex key is in the calibration drawer.", encoding="utf-8")
    context = RetrievalContextBuilder(local_docs_dir=docs).build(
        "How should I reticulate the quantum sprocket?",
    )
    _require(
        context.safety_policy.confidence == "low_confidence",
        "retrieval was not low confidence",
    )
    return FailureSmokeCheck(
        "retrieval_low_confidence",
        "passed",
        f"Retrieval fallback reason: {context.safety_policy.fallback_reason}.",
    )


def _check_debug_artifact_redaction(artifacts_dir: Path) -> FailureSmokeCheck:
    secret = "sk-phase5secret123456"
    docs = artifacts_dir / "secret-docs"
    debug_dir = artifacts_dir / "debug-artifacts"
    docs.mkdir(exist_ok=True)
    (docs / f"{secret}.txt").write_text("hex key is in drawer", encoding="utf-8")
    client = TestClient(
        create_app(
            _settings(
                RETRIEVAL_LOCAL_DOCS_DIR=docs,
                DEBUG_ARTIFACTS_DIR=debug_dir,
                MODEL_API_KEY=secret,
            ),
        ),
    )
    start = client.post(
        "/session/start",
        headers=_headers(),
        json={"debug_enabled": True},
    ).json()
    client.post(
        "/assistant/push-to-talk/start",
        headers=_headers(),
        json={"session_id": start["session_id"]},
    )
    release = client.post(
        "/assistant/push-to-talk/release",
        headers=_headers(),
        json={
            "session_id": start["session_id"],
            "user_text": f"Where is the hex key? Bearer {LOCAL_SECRET}",
        },
    )
    artifact = client.get(
        f"/debug/artifacts/{start['session_id']}/{release.json()['turn_id']}/retrieval.json",
        headers=_headers(),
    )
    serialized = json.dumps(artifact.json())
    _require(secret not in serialized, "model secret leaked into debug artifact")
    _require(LOCAL_SECRET not in serialized, "local secret leaked into debug artifact")
    _require("[REDACTED]" in serialized, "debug artifact did not contain redaction marker")
    return FailureSmokeCheck(
        "debug_artifact_redaction",
        "passed",
        "Debug artifact lookup redacts prompt and source metadata secrets.",
    )


class _TimeoutModelProvider:
    def complete_turn(self, request: ModelTurnRequest):
        raise TimeoutError("phase5 smoke timeout")


def _settings(**overrides) -> Settings:
    values = {
        "MANFRIDAY_LOCAL_SECRET": LOCAL_SECRET,
        "MODEL_PROVIDER": "mock",
        "LIVEKIT_URL": "ws://livekit.test:7880",
        "LIVEKIT_API_KEY": "devkey",
        "LIVEKIT_API_SECRET": "devsecret",
    }
    values.update(overrides)
    return Settings(**values)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {LOCAL_SECRET}"}


def _require(condition: bool, details: str) -> None:
    if not condition:
        raise AssertionError(details)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 5 scripted failure smoke checks.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directory for temporary smoke artifacts. Defaults to a temporary directory.",
    )
    args = parser.parse_args()
    result = run_phase5_failure_smoke(args.artifacts_dir)
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
