import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from manfriday.config.settings import Settings


def _urlsafe_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class LiveKitConnection:
    url: str
    room: str
    token: str


class LiveKitTokenIssuer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def issue_android_token(
        self,
        *,
        session_id: str,
        room_name: str,
        now: datetime | None = None,
    ) -> LiveKitConnection:
        issued_at = int((now or datetime.now(UTC)).timestamp())
        expires_at = issued_at + self._settings.livekit_token_ttl_seconds
        identity = f"android_{session_id}"
        payload = {
            "iss": self._settings.livekit_api_key,
            "sub": identity,
            "name": "Man Friday Android",
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "video": {
                "room": room_name,
                "roomJoin": True,
                "canPublish": True,
                "canSubscribe": True,
            },
        }
        token = self._sign(payload)
        return LiveKitConnection(url=self._settings.livekit_url, room=room_name, token=token)

    def _sign(self, payload: dict) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        signing_input = f"{_urlsafe_json(header)}.{_urlsafe_json(payload)}"
        signature = hmac.new(
            self._settings.livekit_api_secret.get_secret_value().encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        return f"{signing_input}.{encoded_signature}"
