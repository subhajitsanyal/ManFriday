from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from manfriday.api.app import create_app
from manfriday.config.settings import Settings
from manfriday.sessions.store import SessionStore


def test_session_routes_require_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    missing = client.post("/session/start", json={})
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"
    assert client.post(
        "/session/start",
        headers={"Authorization": "Token test-secret"},
        json={},
    ).status_code == 401
    assert client.post(
        "/session/start",
        headers={"Authorization": "Bearer wrong"},
        json={},
    ).status_code == 401


def test_start_status_and_end_session() -> None:
    client = TestClient(create_app(_settings()))
    headers = _headers()

    start = client.post(
        "/session/start",
        headers=headers,
        json={"app_instance_id": "android-1"},
    )

    assert start.status_code == 200
    body = start.json()
    assert body["session_id"].startswith("sess_")
    assert body["livekit"]["url"] == "ws://livekit.test:7880"
    assert body["livekit"]["room"] == f"manfriday_{body['session_id']}"
    assert body["livekit"]["token"].count(".") == 2

    status = client.get(
        "/session/status",
        headers=headers,
        params={"session_id": body["session_id"]},
    )

    assert status.status_code == 200
    assert status.json()["status"] == "active"
    assert status.json()["assistant_state"] == "idle"

    resumed = client.post(
        "/session/start",
        headers=headers,
        json={"app_instance_id": "android-1"},
    )
    assert resumed.json()["session_id"] == body["session_id"]

    ended = client.post(
        "/session/end",
        headers=headers,
        json={"session_id": body["session_id"]},
    )
    assert ended.status_code == 200
    assert ended.json() == {"session_id": body["session_id"], "status": "ended"}


def test_session_store_expires_idle_sessions() -> None:
    now = datetime(2026, 5, 23, 22, 0, tzinfo=UTC)
    store = SessionStore(
        idle_timeout_seconds=60,
        default_debug_enabled=False,
        now_fn=lambda: now,
    )
    session = store.start_session(app_instance_id="android-1", debug_enabled=None)

    now = now + timedelta(seconds=61)
    expired = store.expire_idle_sessions()

    assert [item.session_id for item in expired] == [session.session_id]
    assert store.get(session.session_id).status == "expired"


def test_websocket_rejects_missing_malformed_and_wrong_auth() -> None:
    client = TestClient(create_app(_settings()))
    headers = _headers()
    start = client.post("/session/start", headers=headers, json={}).json()

    for rejected_headers in (
        {},
        {"Authorization": "Token test-secret"},
        {"Authorization": "Bearer wrong"},
    ):
        try:
            with client.websocket_connect(
                f"/ws?session_id={start['session_id']}",
                headers=rejected_headers,
            ):
                raise AssertionError("websocket should not connect without auth")
        except WebSocketDisconnect as exc:
            assert exc.code == 1008


def test_websocket_sends_reconnect_snapshot() -> None:
    client = TestClient(create_app(_settings()))
    headers = _headers()
    start = client.post("/session/start", headers=headers, json={}).json()

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=headers,
    ) as websocket:
        event = websocket.receive_json()

    assert event["type"] == "session.status.changed"
    assert event["session_id"] == start["session_id"]
    assert event["payload"]["status"] == "active"
    assert event["payload"]["assistant_state"] == "idle"


def _settings() -> Settings:
    return Settings(
        MANFRIDAY_LOCAL_SECRET="test-secret",
        LIVEKIT_URL="ws://livekit.test:7880",
        LIVEKIT_API_KEY="devkey",
        LIVEKIT_API_SECRET="devsecret",
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}
