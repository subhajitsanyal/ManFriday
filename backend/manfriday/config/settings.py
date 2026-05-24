from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(default="local", alias="MANFRIDAY_ENV")
    host: str = Field(default="0.0.0.0", alias="MANFRIDAY_HOST")
    port: int = Field(default=8000, alias="MANFRIDAY_PORT")
    local_secret: SecretStr = Field(alias="MANFRIDAY_LOCAL_SECRET")

    livekit_url: str = Field(default="ws://localhost:7880", alias="LIVEKIT_URL")
    livekit_api_key: str = Field(default="devkey", alias="LIVEKIT_API_KEY")
    livekit_api_secret: SecretStr = Field(default=SecretStr("secret"), alias="LIVEKIT_API_SECRET")
    livekit_token_ttl_seconds: int = Field(default=3600, alias="LIVEKIT_TOKEN_TTL_SECONDS")

    model_provider: Literal["mock", "openai", "bedrock"] = Field(
        default="bedrock",
        alias="MODEL_PROVIDER",
    )
    model_base_url: str | None = Field(default=None, alias="MODEL_BASE_URL")
    model_api_key: SecretStr | None = Field(default=None, alias="MODEL_API_KEY")
    model_name: str = Field(
        default="anthropic.claude-sonnet-4-5-20250929-v1:0",
        alias="MODEL_NAME",
    )
    bedrock_max_tokens: int = Field(default=1024, alias="BEDROCK_MAX_TOKENS")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_access_key_id: SecretStr | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: SecretStr | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: SecretStr | None = Field(default=None, alias="AWS_SESSION_TOKEN")

    stt_provider: str = Field(default="openai", alias="STT_PROVIDER")
    stt_model: str = Field(default="gpt-4o-mini-transcribe", alias="STT_MODEL")
    tts_provider: str = Field(default="openai", alias="TTS_PROVIDER")
    tts_model: str = Field(default="gpt-4o-mini-tts", alias="TTS_MODEL")
    tts_voice: str = Field(default="alloy", alias="TTS_VOICE")

    gopro_serial_suffix: str = Field(default="2312", alias="GOPRO_SERIAL_SUFFIX")
    gopro_open_gopro_version: str = Field(default="0.22.0", alias="GOPRO_OPEN_GOPRO_VERSION")
    gopro_controller: Literal["fixture", "open_gopro"] = Field(
        default="fixture",
        alias="GOPRO_CONTROLLER",
    )
    gopro_cohn_credentials_path: Path = Field(
        default=Path(".state/gopro/cohn.json"),
        alias="GOPRO_COHN_CREDENTIALS_PATH",
    )

    frame_sample_fps: int = Field(default=2, alias="FRAME_SAMPLE_FPS")
    frame_jpeg_quality: int = Field(default=80, alias="FRAME_JPEG_QUALITY")
    frame_stale_after_seconds: int = Field(default=5, alias="FRAME_STALE_AFTER_SECONDS")
    frame_look_ttl_seconds: int = Field(default=60, alias="FRAME_LOOK_TTL_SECONDS")

    retrieval_local_docs_dir: Path = Field(
        default=Path("../knowledge/local-docs"),
        alias="RETRIEVAL_LOCAL_DOCS_DIR",
    )
    retrieval_online_sources_path: Path = Field(
        default=Path("../knowledge/online-sources/sources.yaml"),
        alias="RETRIEVAL_ONLINE_SOURCES_PATH",
    )
    retrieval_index_dir: Path = Field(default=Path(".state/retrieval"), alias="RETRIEVAL_INDEX_DIR")
    web_search_enabled: bool = Field(default=False, alias="WEB_SEARCH_ENABLED")
    tavily_api_key: SecretStr | None = Field(default=None, alias="TAVILY_API_KEY")

    session_idle_timeout_seconds: int = Field(default=7200, alias="SESSION_IDLE_TIMEOUT_SECONDS")
    websocket_queue_limit: int = Field(default=32, alias="WEBSOCKET_QUEUE_LIMIT")
    push_to_talk_max_duration_seconds: int = Field(
        default=20,
        alias="PUSH_TO_TALK_MAX_DURATION_SECONDS",
    )
    debug_enabled: bool = Field(default=False, alias="DEBUG_ENABLED")
    debug_artifacts_dir: Path = Field(default=Path("debug_artifacts"), alias="DEBUG_ARTIFACTS_DIR")
    debug_max_sessions: int = Field(default=10, alias="DEBUG_MAX_SESSIONS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
