from manfriday.phase5_failure_smoke import (
    FailureSmokeCheck,
    run_phase5_failure_smoke,
    summarize_checks,
)


def test_phase5_failure_smoke_passes_fixture_checks(tmp_path) -> None:
    result = run_phase5_failure_smoke(tmp_path)

    assert result["status"] == "passed"
    names = {check["name"] for check in result["checks"]}
    assert {
        "backend_health",
        "session_reconnect_snapshot",
        "websocket_disconnect_reconnect",
        "livekit_unavailable_surface",
        "stale_frame_degraded",
        "gopro_unavailable",
        "model_timeout",
        "retrieval_low_confidence",
        "debug_artifact_redaction",
    } <= names
    assert all(check["status"] == "passed" for check in result["checks"])


def test_summarize_checks_reports_failed_when_any_check_fails() -> None:
    assert summarize_checks(
        [
            FailureSmokeCheck("ok", "passed", "done"),
            FailureSmokeCheck("bad", "failed", "not done"),
        ],
    ) == "failed"
