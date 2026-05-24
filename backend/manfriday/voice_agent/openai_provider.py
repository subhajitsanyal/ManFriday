from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib import request
from urllib.error import HTTPError

from pydantic import SecretStr

from manfriday.config.settings import Settings
from manfriday.voice_agent.providers import (
    AudioInput,
    ModelTurnRequest,
    ModelTurnResponse,
    SynthesizedAudio,
    Transcript,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIClient(Protocol):
    def post_json(self, path: str, payload: dict) -> dict: ...

    def post_multipart(self, path: str, fields: dict[str, str], file: MultipartFile) -> dict: ...

    def post_binary_json(self, path: str, payload: dict) -> BinaryResponse: ...


@dataclass(frozen=True)
class MultipartFile:
    field_name: str
    filename: str
    content: bytes
    mime_type: str


@dataclass(frozen=True)
class BinaryResponse:
    content: bytes
    mime_type: str


class OpenAIHTTPClient:
    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout_seconds: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        response = self._request(
            path=path,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return json.loads(response.content.decode("utf-8"))

    def post_multipart(self, path: str, fields: dict[str, str], file: MultipartFile) -> dict:
        boundary = f"----manfriday-{uuid.uuid4().hex}"
        data = _encode_multipart(boundary=boundary, fields=fields, file=file)
        response = self._request(
            path=path,
            data=data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
        )
        return json.loads(response.content.decode("utf-8"))

    def post_binary_json(self, path: str, payload: dict) -> BinaryResponse:
        data = json.dumps(payload).encode("utf-8")
        return self._request(
            path=path,
            data=data,
            headers={"Content-Type": "application/json"},
        )

    def _request(self, *, path: str, data: bytes, headers: dict[str, str]) -> BinaryResponse:
        url = f"{self._base_url}/{path.lstrip('/')}"
        request_headers = {
            **headers,
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
        }
        req = request.Request(url, data=data, headers=request_headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                return BinaryResponse(
                    content=response.read(),
                    mime_type=response.headers.get_content_type(),
                )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI request failed with {exc.code}: {body}") from exc


class OpenAISpeechToTextProvider:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self._client = client
        self._model = model

    def transcribe(self, audio: AudioInput) -> Transcript:
        response = self._client.post_multipart(
            "/audio/transcriptions",
            fields={"model": self._model, "response_format": "json"},
            file=MultipartFile(
                field_name="file",
                filename=f"turn-audio.{_extension_for_mime_type(audio.mime_type)}",
                content=audio.content,
                mime_type=audio.mime_type,
            ),
        )
        text = response.get("text")
        if not isinstance(text, str):
            raise RuntimeError("OpenAI transcription response did not include text.")
        return Transcript(text=text)


class OpenAIVisionLanguageModel:
    def __init__(self, *, client: OpenAIClient, model: str) -> None:
        self._client = client
        self._model = model

    def complete_turn(self, request_model: ModelTurnRequest) -> ModelTurnResponse:
        response = self._client.post_json(
            "/responses",
            {
                "model": self._model,
                "input": _model_prompt(request_model),
            },
        )
        return ModelTurnResponse(text=_extract_response_text(response))


class OpenAITextToSpeechProvider:
    def __init__(self, *, client: OpenAIClient, model: str, voice: str) -> None:
        self._client = client
        self._model = model
        self._voice = voice

    def synthesize(self, text: str) -> SynthesizedAudio:
        response = self._client.post_binary_json(
            "/audio/speech",
            {
                "model": self._model,
                "voice": self._voice,
                "input": text,
                "response_format": "wav",
            },
        )
        return SynthesizedAudio(content=response.content, mime_type=response.mime_type)


def build_openai_client(settings: Settings) -> OpenAIHTTPClient:
    if settings.model_api_key is None:
        raise ValueError("MODEL_API_KEY is required when using OpenAI-backed providers.")
    return OpenAIHTTPClient(
        api_key=settings.model_api_key,
        base_url=settings.model_base_url or DEFAULT_OPENAI_BASE_URL,
    )


def _encode_multipart(*, boundary: str, fields: dict[str, str], file: MultipartFile) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ],
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file.field_name}"; '
                f'filename="{file.filename}"\r\n'
            ).encode(),
            f"Content-Type: {file.mime_type}\r\n\r\n".encode(),
            file.content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ],
    )
    return b"".join(chunks)


def _extension_for_mime_type(mime_type: str) -> str:
    if mime_type == "audio/wav":
        return "wav"
    extension = mimetypes.guess_extension(mime_type)
    return extension.lstrip(".") if extension else "bin"


def _model_prompt(request_model: ModelTurnRequest) -> str:
    frame_context = (
        f"Selected frame ID: {request_model.frame_id}."
        if request_model.frame_id
        else "No fresh visual frame is available."
    )
    return (
        "You are Man Friday, a concise workbench copilot. "
        "Answer the user's question using the visual context when available.\n\n"
        f"Visual status: {request_model.visual_status}\n"
        f"{frame_context}\n"
        f"User question: {request_model.user_text}"
    )


def _extract_response_text(response: dict) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    raise RuntimeError("OpenAI response did not include output text.")
