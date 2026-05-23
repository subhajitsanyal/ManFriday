from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from manfriday.api.app import create_app
from manfriday.config.settings import Settings


def test_frame_routes_require_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert client.get("/gopro/status").status_code == 401
    assert client.post("/gopro/start-preview").status_code == 401
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


def test_latest_frame_unavailable_until_preview_starts() -> None:
    client = TestClient(create_app(_settings()))

    latest = client.get("/frame/latest", headers=_headers())

    assert latest.status_code == 200
    assert latest.json() == {
        "status": "unavailable",
        "visual_status": "unavailable",
        "message": "No fresh frame is available.",
    }


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


def _settings() -> Settings:
    return Settings(MANFRIDAY_LOCAL_SECRET="test-secret")


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}
