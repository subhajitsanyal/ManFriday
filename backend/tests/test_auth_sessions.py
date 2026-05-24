from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from manfriday.api.app import create_app
from manfriday.config.settings import Settings
from manfriday.sessions.store import SessionStore

RETRIEVAL_FIXTURES = Path(__file__).parent / "fixtures" / "retrieval"


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


def test_push_to_talk_routes_require_bearer_auth() -> None:
    client = TestClient(create_app(_settings()))

    assert (
        client.post("/assistant/push-to-talk/start", json={"session_id": "sess_1"}).status_code
        == 401
    )
    assert (
        client.post("/assistant/push-to-talk/release", json={"session_id": "sess_1"}).status_code
        == 401
    )


def test_push_to_talk_start_and_release_emit_transcript_events() -> None:
    client = TestClient(create_app(_settings()))
    headers = _headers()
    start = client.post("/session/start", headers=headers, json={}).json()
    client.post("/gopro/start-preview", headers=headers)

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=headers,
    ) as websocket:
        assert websocket.receive_json()["type"] == "session.status.changed"
        started = client.post(
            "/assistant/push-to-talk/start",
            headers=headers,
            json={"session_id": start["session_id"]},
        )
        listening = websocket.receive_json()
        released = client.post(
            "/assistant/push-to-talk/release",
            headers=headers,
            json={
                "session_id": start["session_id"],
                "user_text": "What is on the workbench?",
            },
        )
        turn_events = [websocket.receive_json() for _ in range(6)]

    assert started.status_code == 200
    assert started.json()["status"] == "listening"
    assert started.json()["max_duration_seconds"] == 20
    assert listening["type"] == "assistant.state.changed"
    assert listening["payload"]["assistant_state"] == "listening"
    assert released.status_code == 200
    assert released.json()["status"] == "completed"
    assert released.json()["turn_id"] == started.json()["turn_id"]
    assert released.json()["user_text"] == "What is on the workbench?"
    assert released.json()["timing_ms"]["response_start"] >= 0
    assert [event["type"] for event in turn_events] == [
        "assistant.state.changed",
        "assistant.transcript.delta",
        "assistant.response.started",
        "assistant.transcript.delta",
        "assistant.response.completed",
        "assistant.state.changed",
    ]
    assert turn_events[1]["payload"]["role"] == "user"
    assert turn_events[1]["payload"]["text"] == "What is on the workbench?"
    assert turn_events[2]["payload"]["timing_ms"]["response_start"] >= 0
    assert turn_events[3]["payload"]["role"] == "assistant"


def test_push_to_talk_release_response_and_transcript_include_retrieval_citations() -> None:
    client = TestClient(create_app(_settings(RETRIEVAL_LOCAL_DOCS_DIR=RETRIEVAL_FIXTURES)))
    headers = _headers()
    start = client.post("/session/start", headers=headers, json={}).json()

    with client.websocket_connect(
        f"/ws?session_id={start['session_id']}",
        headers=headers,
    ) as websocket:
        assert websocket.receive_json()["type"] == "session.status.changed"
        client.post(
            "/assistant/push-to-talk/start",
            headers=headers,
            json={"session_id": start["session_id"]},
        )
        assert websocket.receive_json()["payload"]["assistant_state"] == "listening"
        released = client.post(
            "/assistant/push-to-talk/release",
            headers=headers,
            json={
                "session_id": start["session_id"],
                "user_text": "Where is the hex key?",
            },
        )
        turn_events = [websocket.receive_json() for _ in range(6)]

    assert released.status_code == 200
    citation = released.json()["citations"][0]
    assert citation["source_uri"] == "notes.txt"
    assert citation["source_title"] == "notes"
    assistant_transcript = next(
        event
        for event in turn_events
        if event["type"] == "assistant.transcript.delta"
        and event["payload"]["role"] == "assistant"
    )
    assert assistant_transcript["payload"]["citations"][0]["source_uri"] == "notes.txt"


def test_push_to_talk_release_without_speech_discards_turn() -> None:
    client = TestClient(create_app(_settings()))
    headers = _headers()
    start = client.post("/session/start", headers=headers, json={}).json()
    client.post(
        "/assistant/push-to-talk/start",
        headers=headers,
        json={"session_id": start["session_id"]},
    )

    released = client.post(
        "/assistant/push-to-talk/release",
        headers=headers,
        json={"session_id": start["session_id"], "has_speech": False},
    )

    assert released.status_code == 200
    assert released.json()["status"] == "discarded"
    assert released.json()["user_text"] is None
    assert client.app.state.session_store.get(start["session_id"]).memory == {}


def _settings(**overrides) -> Settings:
    values = {
        "MANFRIDAY_LOCAL_SECRET": "test-secret",
        "MODEL_PROVIDER": "mock",
        "LIVEKIT_URL": "ws://livekit.test:7880",
        "LIVEKIT_API_KEY": "devkey",
        "LIVEKIT_API_SECRET": "devsecret",
    }
    values.update(overrides)
    return Settings(
        **values,
    )


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-secret"}
