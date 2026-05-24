from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.config.settings import Settings


def test_frame_routes_require_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert client.get("/gopro/status").status_code == 401
    assert client.post("/gopro/start-preview").status_code == 401
    assert client.post("/gopro/reconfigure", json={}).status_code == 401
    assert client.get("/frame/latest").status_code == 401
    assert client.post("/frame/look").status_code == 401


def test_start_preview_creates_fixture_latest_frame_and_jpeg() -> None:
    client = TestClient(create_app(_settings()))

    status = client.post("/gopro/start-preview", headers=_headers())

    assert status.status_code == 200
    assert status.json()["status"] == "preview_running"
    assert status.json()["preview_running"] is True
    assert status.json()["visual_status"] == "healthy"

    latest = client.get("/frame/latest", headers=_headers())
    assert latest.status_code == 200
    body = latest.json()
    assert body["frame_id"].startswith("frame_")
    assert body["jpeg_url"] == f"/frame/{body['frame_id']}.jpg"
    assert body["width"] == 1
    assert body["height"] == 1
    assert body["is_pinned"] is False

    jpeg = client.get(body["jpeg_url"], headers=_headers())
    assert jpeg.status_code == 200
    assert jpeg.headers["content-type"] == "image/jpeg"
    assert jpeg.headers["cache-control"] == "no-store"
    assert jpeg.content.startswith(b"\xff\xd8")


def test_start_preview_is_idempotent_for_fixture_sampler() -> None:
    client = TestClient(create_app(_settings()))

    first = client.post("/gopro/start-preview", headers=_headers())
    second = client.post("/gopro/start-preview", headers=_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["last_frame_at"] == second.json()["last_frame_at"]


def test_latest_frame_unavailable_until_preview_starts() -> None:
    client = TestClient(create_app(_settings()))

    latest = client.get("/frame/latest", headers=_headers())

    assert latest.status_code == 200
    assert latest.json() == {
        "status": "unavailable",
        "visual_status": "unavailable",
        "message": "No fresh frame is available.",
    }


def test_latest_frame_reports_degraded_when_preview_running_but_frame_is_stale() -> None:
    app = create_app(_settings())
    client = TestClient(app)
    client.post("/gopro/start-preview", headers=_headers())
    latest = app.state.frame_store.latest()
    latest.captured_at = datetime.now(UTC) - timedelta(seconds=6)

    response = client.get("/frame/latest", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "visual_status": "degraded",
        "message": "No fresh frame is available.",
    }


def test_gopro_status_degrades_when_preview_running_and_frame_is_stale() -> None:
    app = create_app(_settings())
    client = TestClient(app)
    client.post("/gopro/start-preview", headers=_headers())
    latest = app.state.frame_store.latest()
    latest.captured_at = datetime.now(UTC) - timedelta(seconds=6)

    response = client.get("/gopro/status", headers=_headers())

    assert response.status_code == 200
    assert response.json()["preview_running"] is True
    assert response.json()["visual_status"] == "degraded"
    assert response.json()["last_frame_at"] is not None


def test_look_pins_latest_frame_and_can_replace_pin() -> None:
    client = TestClient(create_app(_settings()))
    client.post("/gopro/start-preview", headers=_headers())

    first = client.post("/frame/look", headers=_headers())
    second = client.post("/frame/look", headers=_headers())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["frame_id"] == second.json()["frame_id"]
    assert first.json()["pin_expires_at"] <= second.json()["pin_expires_at"]


def test_look_without_fresh_frame_returns_common_error_shape() -> None:
    app = create_app(_settings())
    client = TestClient(app)
    client.post("/gopro/start-preview", headers=_headers())
    latest = app.state.frame_store.latest()
    latest.captured_at = datetime.now(UTC) - timedelta(seconds=6)

    response = client.post("/frame/look", headers=_headers())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "frame_unavailable"
    assert response.json()["error"]["retryable"] is True


def test_unknown_frame_jpeg_returns_common_error_shape() -> None:
    client = TestClient(create_app(_settings()))

    response = client.get("/frame/missing.jpg", headers=_headers())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "frame_not_found"


def test_start_preview_emits_frame_latest_event_to_active_session_websocket() -> None:
    client = TestClient(create_app(_settings()))
    start = client.post("/session/start", headers=_headers(), json={}).json()

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=_headers(),
    ) as websocket:
        assert websocket.receive_json()["type"] == "session.status.changed"
        client.post("/gopro/start-preview", headers=_headers())
        event = websocket.receive_json()

    assert event["type"] == "frame.latest.updated"
    assert event["session_id"] == start["session_id"]
    assert event["payload"]["jpeg_url"].startswith("/frame/")


def test_reconfigure_requires_explicit_clear_credentials_confirmation() -> None:
    client = TestClient(create_app(_settings()))

    response = client.post(
        "/gopro/reconfigure",
        headers=_headers(),
        json={"confirm_clear_credentials": False},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "confirmation_required"


def test_reconfigure_clears_credentials_stops_preview_and_emits_event(tmp_path) -> None:
    credentials_path = tmp_path / "cohn.json"
    credentials_path.write_text('{"camera":"fixture"}')
    settings = _settings(GOPRO_COHN_CREDENTIALS_PATH=credentials_path)
    client = TestClient(create_app(settings))
    start = client.post("/session/start", headers=_headers(), json={}).json()
    client.post("/gopro/start-preview", headers=_headers())

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=_headers(),
    ) as websocket:
        assert websocket.receive_json()["type"] == "session.status.changed"
        response = client.post(
            "/gopro/reconfigure",
            headers=_headers(),
            json={"confirm_clear_credentials": True},
        )
        event = websocket.receive_json()

    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert response.json()["job_id"].startswith("gopro_reconfigure_")
    assert credentials_path.exists() is False
    assert event["type"] == "gopro.reconfigure.started"
    assert event["payload"]["status"] == "started"

    status = client.get("/gopro/status", headers=_headers())
    assert status.json()["preview_running"] is False
    assert status.json()["status"] == "preview_stopped"


def test_cancel_reconfigure_emits_cancelled_status() -> None:
    client = TestClient(create_app(_settings()))
    start = client.post("/session/start", headers=_headers(), json={}).json()
    client.post(
        "/gopro/reconfigure",
        headers=_headers(),
        json={"confirm_clear_credentials": True},
    )

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=_headers(),
    ) as websocket:
        assert websocket.receive_json()["type"] == "session.status.changed"
        response = client.post("/gopro/reconfigure/cancel", headers=_headers())
        event = websocket.receive_json()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert event["type"] == "gopro.reconfigure.cancelled"


def test_fixture_sampler_failure_degrades_gopro_status() -> None:
    app = create_app(_settings())
    client = TestClient(app)
    client.post("/gopro/start-preview", headers=_headers())

    app.state.gopro_service.sampler().mark_failed("fixture sampler stopped")
    response = client.get("/gopro/status", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["visual_status"] == "degraded"
    assert response.json()["message"] == "fixture sampler stopped"


def test_open_gopro_controller_reports_missing_credentials(tmp_path) -> None:
    settings = _settings(
        GOPRO_CONTROLLER="open_gopro",
        GOPRO_COHN_CREDENTIALS_PATH=tmp_path / "missing-cohn.json",
    )
    client = TestClient(create_app(settings))

    status = client.get("/gopro/status", headers=_headers())
    start = client.post("/gopro/start-preview", headers=_headers())

    assert status.status_code == 200
    assert status.json()["status"] == "credentials_missing"
    assert status.json()["visual_status"] == "unavailable"
    assert start.status_code == 200
    assert start.json()["status"] == "reconfigure_required"
    assert start.json()["preview_running"] is False


def test_open_gopro_external_udp_stream_can_start_without_credentials(tmp_path) -> None:
    settings = _settings(
        GOPRO_CONTROLLER="open_gopro",
        GOPRO_COHN_CREDENTIALS_PATH=tmp_path / "missing-cohn.json",
        GOPRO_ALLOW_EXTERNAL_UDP_STREAM=True,
        FRAME_UDP_URL="udp://@:8554",
    )
    app = create_app(settings)

    status = app.state.gopro_controller.status()
    start = app.state.gopro_controller.start_preview()

    assert status.status.value == "connected"
    assert status.message == "External GoPro UDP stream is configured."
    assert start.status.value == "preview_running"
    assert start.message == "Using externally managed GoPro UDP stream."
    assert app.state.gopro_service.sampler().__class__.__name__ == "FfmpegFrameSampler"


def test_open_gopro_controller_detects_saved_credentials(tmp_path) -> None:
    credentials_path = tmp_path / "cohn.json"
    credentials_path.write_text('{"camera":"fixture"}')
    settings = _settings(
        GOPRO_CONTROLLER="open_gopro",
        GOPRO_COHN_CREDENTIALS_PATH=credentials_path,
    )
    client = TestClient(create_app(settings))

    status = client.get("/gopro/status", headers=_headers())

    assert status.status_code == 200
    assert status.json()["status"] == "connected"
    assert status.json()["preview_running"] is False
    assert (
        status.json()["message"]
        == "Saved GoPro COHN credentials found. Hardware connection is pending."
    )


def _settings(**overrides) -> Settings:
    return Settings(MANFRIDAY_LOCAL_SECRET="test-secret", MODEL_PROVIDER="mock", **overrides)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}
