import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from manfriday.config.settings import Settings

REDACTED = "[REDACTED]"
SECRET_KEYWORDS = (
    "authorization",
    "bearer",
    "token",
    "secret",
    "api_key",
    "apikey",
    "password",
    "credential",
    "access_key",
    "session_key",
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
)


@dataclass(frozen=True)
class DebugArtifactSummary:
    session_id: str
    turn_id: str
    artifact: str
    path: str


def write_debug_artifact(
    *,
    root: Path,
    session_id: str,
    turn_id: str,
    artifact: str,
    payload: dict,
    settings: Settings | None = None,
) -> Path:
    artifact_dir = root / session_id / turn_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / artifact
    path.write_text(
        json.dumps(redact_debug_payload(payload, settings=settings), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def list_debug_artifacts(root: Path) -> tuple[DebugArtifactSummary, ...]:
    if not root.exists():
        return ()
    artifacts: list[DebugArtifactSummary] = []
    for path in sorted(root.glob("*/*/*.json")):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        parts = relative.parts
        if len(parts) != 3:
            continue
        artifacts.append(
            DebugArtifactSummary(
                session_id=parts[0],
                turn_id=parts[1],
                artifact=parts[2],
                path=str(relative),
            ),
        )
    return tuple(artifacts)


def load_debug_artifact(root: Path, *, session_id: str, turn_id: str, artifact: str) -> dict | None:
    path = _safe_artifact_path(root, session_id=session_id, turn_id=turn_id, artifact=artifact)
    if path is None or not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def redact_debug_payload(payload: Any, *, settings: Settings | None = None) -> Any:
    known_secret_values = _known_secret_values(settings)
    return _redact_value(payload, known_secret_values=known_secret_values)


def _redact_value(value: Any, *, known_secret_values: tuple[str, ...], key: str = "") -> Any:
    if isinstance(value, SecretStr):
        return REDACTED
    if _is_secret_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(
                item_value,
                known_secret_values=known_secret_values,
                key=str(item_key),
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _redact_value(item, known_secret_values=known_secret_values)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_text(value, known_secret_values=known_secret_values)
    return value


def _redact_text(text: str, *, known_secret_values: tuple[str, ...]) -> str:
    result = text
    for pattern in SECRET_VALUE_PATTERNS:
        result = pattern.sub(REDACTED, result)
    for secret in known_secret_values:
        if secret:
            result = result.replace(secret, REDACTED)
    return result


def _known_secret_values(settings: Settings | None) -> tuple[str, ...]:
    if settings is None:
        return ()
    values: list[str] = []
    for name in (
        "local_secret",
        "livekit_api_secret",
        "model_api_key",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "tavily_api_key",
    ):
        item = getattr(settings, name, None)
        if isinstance(item, SecretStr):
            values.append(item.get_secret_value())
    if settings.livekit_api_key:
        values.append(settings.livekit_api_key)
    return tuple(value for value in values if value)


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def _safe_artifact_path(
    root: Path,
    *,
    session_id: str,
    turn_id: str,
    artifact: str,
) -> Path | None:
    if "/" in artifact or "\\" in artifact or not artifact.endswith(".json"):
        return None
    path = root / session_id / turn_id / artifact
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return path
