import pytest
from pydantic import ValidationError

from manfriday.config.settings import Settings


def test_settings_load_required_local_secret() -> None:
    settings = Settings(MANFRIDAY_LOCAL_SECRET="test-secret")

    assert settings.local_secret.get_secret_value() == "test-secret"
    assert settings.livekit_url == "ws://localhost:7880"
    assert settings.gopro_serial_suffix == "2312"
    assert settings.frame_sample_fps == 2
    assert settings.session_idle_timeout_seconds == 7200
    assert settings.livekit_token_ttl_seconds == 3600
    assert settings.websocket_queue_limit == 32


def test_settings_require_local_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
