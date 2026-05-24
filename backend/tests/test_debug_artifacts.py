import json

from manfriday.config.settings import Settings
from manfriday.debug_artifacts import (
    REDACTED,
    load_debug_artifact,
    redact_debug_payload,
    write_debug_artifact,
)


def test_redact_debug_payload_removes_settings_headers_prompts_and_metadata() -> None:
    settings = Settings(
        MANFRIDAY_LOCAL_SECRET="local-secret",
        LIVEKIT_API_KEY="livekit-key",
        LIVEKIT_API_SECRET="livekit-secret",
        MODEL_API_KEY="sk-modelsecret123456",
        AWS_ACCESS_KEY_ID="AKIAABCDEFGHIJKLMNOP",
        AWS_SECRET_ACCESS_KEY="aws-secret",
        AWS_SESSION_TOKEN="aws-session-token",
        TAVILY_API_KEY="tavily-secret",
    )
    payload = {
        "headers": {"Authorization": "Bearer local-secret"},
        "prompt": "Use sk-modelsecret123456 and AKIAABCDEFGHIJKLMNOP",
        "selected_chunks": [
            {
                "source_uri": "manual-sk-modelsecret123456.txt",
                "source_title": "livekit-secret manual",
            },
        ],
        "aws_secret_access_key": "aws-secret",
        "nested": ["tavily-secret", "aws-session-token", "livekit-key"],
    }

    redacted = redact_debug_payload(payload, settings=settings)
    serialized = json.dumps(redacted)

    for secret in (
        "local-secret",
        "sk-modelsecret123456",
        "AKIAABCDEFGHIJKLMNOP",
        "aws-secret",
        "aws-session-token",
        "tavily-secret",
        "livekit-key",
        "livekit-secret",
    ):
        assert secret not in serialized
    assert REDACTED in serialized


def test_write_and_load_debug_artifact_redacts_before_persisting(tmp_path) -> None:
    settings = Settings(
        MANFRIDAY_LOCAL_SECRET="local-secret",
        MODEL_API_KEY="sk-modelsecret123456",
    )

    path = write_debug_artifact(
        root=tmp_path,
        session_id="sess_test",
        turn_id="turn_test",
        artifact="retrieval.json",
        payload={
            "query": "Where is the hex key? Bearer local-secret",
            "source_uri": "manual-sk-modelsecret123456.txt",
        },
        settings=settings,
    )
    raw = path.read_text(encoding="utf-8")
    loaded = load_debug_artifact(
        tmp_path,
        session_id="sess_test",
        turn_id="turn_test",
        artifact="retrieval.json",
    )

    assert "local-secret" not in raw
    assert "sk-modelsecret123456" not in raw
    assert loaded is not None
    assert loaded["query"] == f"Where is the hex key? {REDACTED}"
    assert loaded["source_uri"] == f"manual-{REDACTED}.txt"
