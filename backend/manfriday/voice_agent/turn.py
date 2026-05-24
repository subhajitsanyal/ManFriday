from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from manfriday.events import EventBus, EventEnvelope
from manfriday.frames import FrameStore
from manfriday.frames.models import FrameMetadata
from manfriday.retrieval import Citation, RetrievalContext
from manfriday.voice_agent.providers import (
    AudioInput,
    ModelTurnRequest,
    SpeechToTextProvider,
    SynthesizedAudio,
    TextToSpeechProvider,
    Transcript,
    VisionLanguageModel,
)


@dataclass(frozen=True)
class VoiceTurnResult:
    turn_id: str
    user_text: str
    assistant_text: str
    frame_id: str | None
    visual_status: str
    audio: SynthesizedAudio
    timing_ms: dict[str, int]
    citations: tuple[Citation, ...] = ()


class RetrievalContextProvider(Protocol):
    def build(self, query: str) -> RetrievalContext: ...


class VoiceTurnError(RuntimeError):
    pass


class VoiceTurnOrchestrator:
    def __init__(
        self,
        *,
        stt_provider: SpeechToTextProvider,
        model_provider: VisionLanguageModel,
        tts_provider: TextToSpeechProvider,
        frame_store: FrameStore,
        event_bus: EventBus,
        retrieval_context_provider: RetrievalContextProvider | None = None,
    ) -> None:
        self._stt_provider = stt_provider
        self._model_provider = model_provider
        self._tts_provider = tts_provider
        self._frame_store = frame_store
        self._event_bus = event_bus
        self._retrieval_context_provider = retrieval_context_provider

    async def run_turn(
        self,
        *,
        session_id: str,
        audio: AudioInput | None = None,
        user_text: str | None = None,
        session_memory: dict | None = None,
        turn_id: str | None = None,
        synthesize_audio: bool = True,
    ) -> VoiceTurnResult:
        turn_id = turn_id or f"turn_{uuid4().hex}"
        started_at = perf_counter()
        timings: dict[str, int] = {}

        await self._publish_state(
            session_id=session_id,
            turn_id=turn_id,
            assistant_state="thinking",
            reason="turn_started",
        )
        if user_text is not None:
            transcript = Transcript(text=user_text)
            timings["stt"] = 0
        else:
            if audio is None:
                raise VoiceTurnError("Audio input is required when user text is absent.")
            try:
                transcript_start = perf_counter()
                transcript = self._stt_provider.transcribe(audio)
                timings["stt"] = self._elapsed_ms(transcript_start)
            except Exception as exc:
                await self._publish_error(
                    session_id=session_id,
                    turn_id=turn_id,
                    code="stt_failed",
                    message=str(exc),
                    retryable=True,
                )
                raise VoiceTurnError("STT failed.") from exc

        if not transcript.text.strip():
            await self._publish_error(
                session_id=session_id,
                turn_id=turn_id,
                code="empty_transcript",
                message="No speech was detected.",
                retryable=True,
            )
            raise VoiceTurnError("No speech was detected.")

        frame_start = perf_counter()
        frame = self._select_frame()
        timings["frame_select"] = self._elapsed_ms(frame_start)
        frame_id = frame.frame_id if frame else None
        visual_context = "frame" if frame else "unavailable"
        visual_status = "healthy" if frame else "degraded"
        retrieval_context = self._build_retrieval_context(transcript.text)
        citations = retrieval_context.citations if retrieval_context is not None else ()
        citation_payload = [_citation_payload(citation) for citation in citations]

        await self._publish(
            "assistant.transcript.delta",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "role": "user",
                "text": transcript.text,
                "is_final": True,
                "frame_id": frame_id,
                "visual_context": visual_context,
                "visual_status": visual_status,
            },
        )
        try:
            model_start = perf_counter()
            response = self._model_provider.complete_turn(
                ModelTurnRequest(
                    turn_id=turn_id,
                    session_id=session_id,
                    user_text=transcript.text,
                    frame_id=frame_id,
                    visual_status=visual_status,
                    retrieval_context=retrieval_context,
                ),
            )
            timings["model"] = self._elapsed_ms(model_start)
            timings["response_start"] = self._elapsed_ms(started_at)
        except Exception as exc:
            await self._publish_error(
                session_id=session_id,
                turn_id=turn_id,
                code="model_failed",
                message=str(exc),
                retryable=True,
            )
            raise VoiceTurnError("Model turn failed.") from exc

        await self._publish(
            "assistant.response.started",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "frame_id": frame_id,
                "visual_context": visual_context,
                "visual_status": visual_status,
                "timing_ms": {
                    "response_start": timings["response_start"],
                },
            },
        )

        if synthesize_audio:
            try:
                tts_start = perf_counter()
                speech = self._tts_provider.synthesize(response.text)
                timings["tts"] = self._elapsed_ms(tts_start)
                tts_audio_ref = f"mock://tts/{turn_id}"
            except Exception as exc:
                await self._publish_error(
                    session_id=session_id,
                    turn_id=turn_id,
                    code="tts_failed",
                    message=str(exc),
                    retryable=True,
                )
                raise VoiceTurnError("TTS failed.") from exc
        else:
            speech = SynthesizedAudio(content=b"", mime_type="audio/android-tts")
            timings["tts"] = 0
            tts_audio_ref = None

        await self._publish(
            "assistant.transcript.delta",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "role": "assistant",
                "text": response.text,
                "is_final": True,
                "frame_id": frame_id,
                "visual_context": visual_context,
                "visual_status": visual_status,
                "citations": citation_payload,
            },
        )
        timings["total"] = self._elapsed_ms(started_at)
        await self._publish(
            "assistant.response.completed",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "frame_id": frame_id,
                "visual_context": visual_context,
                "visual_status": visual_status,
                "citations": citation_payload,
                "audio_mime_type": speech.mime_type,
                "tts_audio_ref": tts_audio_ref,
                "timing_ms": timings,
            },
        )
        await self._publish_state(
            session_id=session_id,
            turn_id=turn_id,
            assistant_state="idle",
            reason="turn_completed",
        )
        if session_memory is not None:
            session_memory.setdefault("turns", []).append(
                {
                    "turn_id": turn_id,
                    "user_text": transcript.text,
                    "assistant_text": response.text,
                    "frame_id": frame_id,
                    "citations": citation_payload,
                },
            )
        return VoiceTurnResult(
            turn_id=turn_id,
            user_text=transcript.text,
            assistant_text=response.text,
            frame_id=frame_id,
            visual_status=visual_status,
            audio=speech,
            timing_ms=timings,
            citations=citations,
        )

    def _select_frame(self) -> FrameMetadata | None:
        return self._frame_store.pinned() or self._frame_store.latest_if_healthy()

    def _build_retrieval_context(self, query: str) -> RetrievalContext | None:
        if self._retrieval_context_provider is None:
            return None
        return self._retrieval_context_provider.build(query)

    async def _publish(self, event_type: str, *, session_id: str, payload: dict) -> None:
        await self._event_bus.publish(
            EventEnvelope(
                type=event_type,
                session_id=session_id,
                payload=payload,
            ),
        )

    async def _publish_state(
        self,
        *,
        session_id: str,
        turn_id: str,
        assistant_state: str,
        reason: str,
    ) -> None:
        await self._publish(
            "assistant.state.changed",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "assistant_state": assistant_state,
                "reason": reason,
            },
        )

    async def _publish_error(
        self,
        *,
        session_id: str,
        turn_id: str,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        await self._publish(
            "assistant.error",
            session_id=session_id,
            payload={
                "turn_id": turn_id,
                "code": code,
                "message": message,
                "retryable": retryable,
            },
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))


def _citation_payload(citation: Citation) -> dict:
    return {
        "citation_id": citation.citation_id,
        "source_id": citation.source_id,
        "chunk_id": citation.chunk_id,
        "source_title": citation.source_title,
        "source_uri": citation.source_uri,
        "source_type": citation.source_type,
        "section": citation.section,
        "score": citation.score,
    }
