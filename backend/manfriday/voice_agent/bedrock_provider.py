from __future__ import annotations

import hashlib
import hmac
import json
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib import parse, request
from urllib.error import HTTPError

from pydantic import SecretStr

from manfriday.config.settings import Settings
from manfriday.voice_agent.providers import ModelTurnRequest, ModelTurnResponse

BEDROCK_SERVICE = "bedrock"
BEDROCK_ANTHROPIC_VERSION = "bedrock-2023-05-31"


class BedrockClient(Protocol):
    def invoke_model(self, *, model_id: str, payload: dict) -> dict: ...


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: SecretStr
    secret_access_key: SecretStr
    session_token: SecretStr | None = None


class BedrockRuntimeClient:
    def __init__(
        self,
        *,
        credentials: AwsCredentials,
        region: str,
        timeout_seconds: int = 60,
    ) -> None:
        self._credentials = credentials
        self._region = region
        self._endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"
        self._timeout_seconds = timeout_seconds

    def invoke_model(self, *, model_id: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        now = datetime.now(UTC)
        path = f"/model/{parse.quote(model_id, safe='')}/invoke"
        canonical_path = parse.quote(path, safe="/")
        headers = self._signed_headers(
            method="POST",
            canonical_path=canonical_path,
            body=body,
            now=now,
            extra_headers={
                "accept": "application/json",
                "content-type": "application/json",
            },
        )
        req = request.Request(
            f"{self._endpoint}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bedrock request failed with {exc.code}: {body_text}") from exc

    def _signed_headers(
        self,
        *,
        method: str,
        canonical_path: str,
        body: bytes,
        now: datetime,
        extra_headers: dict[str, str],
    ) -> dict[str, str]:
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        host = f"bedrock-runtime.{self._region}.amazonaws.com"
        headers = {
            **extra_headers,
            "host": host,
            "x-amz-date": amz_date,
        }
        if self._credentials.session_token is not None:
            headers["x-amz-security-token"] = self._credentials.session_token.get_secret_value()

        signed_header_names = sorted(headers)
        canonical_headers = "".join(
            f"{name}:{headers[name].strip()}\n" for name in signed_header_names
        )
        signed_headers = ";".join(signed_header_names)
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_request = "\n".join(
            [
                method,
                canonical_path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ],
        )
        credential_scope = f"{date_stamp}/{self._region}/{BEDROCK_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ],
        )
        signing_key = _signing_key(
            secret_access_key=self._credentials.secret_access_key.get_secret_value(),
            date_stamp=date_stamp,
            region=self._region,
        )
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._credentials.access_key_id.get_secret_value()}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers


class BedrockClaudeModel:
    def __init__(self, *, client: BedrockClient, model_id: str, max_tokens: int) -> None:
        self._client = client
        self._model_id = model_id
        self._max_tokens = max_tokens

    def complete_turn(self, request_model: ModelTurnRequest) -> ModelTurnResponse:
        response = self._client.invoke_model(
            model_id=self._model_id,
            payload={
                "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
                "max_tokens": self._max_tokens,
                "system": "You are Man Friday, a concise workbench copilot.",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": _model_prompt(request_model),
                            },
                        ],
                    },
                ],
            },
        )
        return ModelTurnResponse(text=_extract_bedrock_text(response))


def build_bedrock_client(settings: Settings) -> BedrockRuntimeClient:
    credentials = _resolve_aws_credentials(settings)
    return BedrockRuntimeClient(
        credentials=credentials,
        region=settings.aws_region,
    )


def _resolve_aws_credentials(settings: Settings) -> AwsCredentials:
    if settings.aws_profile:
        return _load_shared_credentials(settings.aws_profile)
    if settings.aws_access_key_id is not None and settings.aws_secret_access_key is not None:
        return AwsCredentials(
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
            session_token=settings.aws_session_token,
        )
    return _load_shared_credentials("default")


def _load_shared_credentials(profile: str) -> AwsCredentials:
    credentials_path = Path.home() / ".aws" / "credentials"
    parser = ConfigParser()
    parser.read(credentials_path)
    if not parser.has_section(profile):
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required for Bedrock, "
            f"or configure profile '{profile}' in ~/.aws/credentials.",
        )
    access_key_id = parser.get(profile, "aws_access_key_id", fallback="").strip()
    secret_access_key = parser.get(profile, "aws_secret_access_key", fallback="").strip()
    session_token = parser.get(profile, "aws_session_token", fallback="").strip()
    if not access_key_id or not secret_access_key:
        raise ValueError(
            f"AWS profile '{profile}' in ~/.aws/credentials must include "
            "aws_access_key_id and aws_secret_access_key.",
        )
    return AwsCredentials(
        access_key_id=SecretStr(access_key_id),
        secret_access_key=SecretStr(secret_access_key),
        session_token=SecretStr(session_token) if session_token else None,
    )


def _model_prompt(request_model: ModelTurnRequest) -> str:
    frame_context = (
        f"Selected frame ID: {request_model.frame_id}."
        if request_model.frame_id
        else "No fresh visual frame is available."
    )
    retrieval_context = _retrieval_prompt(request_model)
    return (
        "Answer the user's question using the visual context when available.\n\n"
        f"Visual status: {request_model.visual_status}\n"
        f"{frame_context}\n"
        f"{retrieval_context}"
        f"User question: {request_model.user_text}"
    )


def _retrieval_prompt(request_model: ModelTurnRequest) -> str:
    context = request_model.retrieval_context
    if context is None:
        return "Retrieved context: none.\n"
    lines = [
        "Retrieval safety policy:",
        f"- confidence: {context.safety_policy.confidence}",
        f"- fallback_reason: {context.safety_policy.fallback_reason}",
        f"- instruction: {context.safety_policy.instruction}",
    ]
    if not context.chunks:
        lines.append("Retrieved context: none.")
        lines.append("")
        return "\n".join(lines)
    lines.append("Retrieved context:")
    for citation, result in zip(context.citations, context.chunks, strict=True):
        section = f", section: {citation.section}" if citation.section else ""
        lines.append(
            f"[{citation.citation_id}] {citation.source_title} "
            f"({citation.source_uri}{section})\n{result.chunk.text}"
        )
    lines.append("")
    return "\n".join(lines)


def _extract_bedrock_text(response: dict) -> str:
    for content in response.get("content", []):
        if isinstance(content, dict) and content.get("type") == "text":
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    raise RuntimeError("Bedrock Claude response did not include text content.")


def _signing_key(*, secret_access_key: str, date_stamp: str, region: str) -> bytes:
    date_key = _hmac(f"AWS4{secret_access_key}".encode(), date_stamp)
    date_region_key = _hmac(date_key, region)
    date_region_service_key = _hmac(date_region_key, BEDROCK_SERVICE)
    return _hmac(date_region_service_key, "aws4_request")


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()
