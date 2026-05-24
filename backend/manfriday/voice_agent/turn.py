import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from manfriday.config.settings import Settings
from manfriday.debug_artifacts import write_debug_artifact
from manfriday.events import EventBus, EventEnvelope
from manfriday.frames import FrameStore
from manfriday.frames.models import FrameMetadata
from manfriday.retrieval import Citation, RetrievalContext
from manfriday.voice_agent.providers import (
    AudioInput,
    ModelTurnRequest,
    ModelTurnResponse,
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
    safety_action: str = "none"
    safety_category: str = "none"


@dataclass(frozen=True)
class SafetyAssessment:
    category: str = "none"
    action: str = "none"
    reason: str = "none"
    response_text: str | None = None

    @property
    def blocks_model(self) -> bool:
        return self.response_text is not None


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
        debug_artifacts_dir: Path | None = None,
        debug_settings: Settings | None = None,
    ) -> None:
        self._stt_provider = stt_provider
        self._model_provider = model_provider
        self._tts_provider = tts_provider
        self._frame_store = frame_store
        self._event_bus = event_bus
        self._retrieval_context_provider = retrieval_context_provider
        self._debug_artifacts_dir = debug_artifacts_dir
        self._debug_settings = debug_settings

    async def run_turn(
        self,
        *,
        session_id: str,
        audio: AudioInput | None = None,
        user_text: str | None = None,
        session_memory: dict | None = None,
        turn_id: str | None = None,
        synthesize_audio: bool = True,
        debug_enabled: bool = False,
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
        retrieval_debug = _retrieval_debug_payload(retrieval_context)
        safety = _classify_user_prompt(transcript.text)

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
        if safety.blocks_model:
            response = ModelTurnResponse(text=safety.response_text or "")
            timings["model"] = 0
            timings["response_start"] = self._elapsed_ms(started_at)
        else:
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
                response_text, safety = _apply_post_model_safety(
                    response.text,
                    retrieval_context,
                    safety,
                )
                response = ModelTurnResponse(text=response_text)
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

        assistant_payload = {
            "turn_id": turn_id,
            "role": "assistant",
            "text": response.text,
            "is_final": True,
            "frame_id": frame_id,
            "visual_context": visual_context,
            "visual_status": visual_status,
            "citations": citation_payload,
            "safety_action": safety.action,
            "safety_category": safety.category,
        }
        if debug_enabled:
            assistant_payload["retrieval_debug"] = retrieval_debug
        await self._publish(
            "assistant.transcript.delta",
            session_id=session_id,
            payload=assistant_payload,
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
                "safety_action": safety.action,
                "safety_category": safety.category,
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
            memory_turn = {
                "turn_id": turn_id,
                "user_text": transcript.text,
                "assistant_text": response.text,
                "frame_id": frame_id,
                "citations": citation_payload,
            }
            if safety.action != "none":
                memory_turn["safety_action"] = safety.action
                memory_turn["safety_category"] = safety.category
            if debug_enabled:
                memory_turn["retrieval_debug"] = retrieval_debug
            session_memory.setdefault("turns", []).append(memory_turn)
        if debug_enabled:
            self._write_retrieval_debug_artifact(
                session_id=session_id,
                turn_id=turn_id,
                payload={
                    **retrieval_debug,
                    "safety_action": safety.action,
                    "safety_category": safety.category,
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
            safety_action=safety.action,
            safety_category=safety.category,
        )

    def _select_frame(self) -> FrameMetadata | None:
        return self._frame_store.pinned() or self._frame_store.latest_if_healthy()

    def _build_retrieval_context(self, query: str) -> RetrievalContext | None:
        if self._retrieval_context_provider is None:
            return None
        return self._retrieval_context_provider.build(query)

    def _write_retrieval_debug_artifact(
        self,
        *,
        session_id: str,
        turn_id: str,
        payload: dict,
    ) -> None:
        if self._debug_artifacts_dir is None:
            return
        write_debug_artifact(
            root=self._debug_artifacts_dir,
            session_id=session_id,
            turn_id=turn_id,
            artifact="retrieval.json",
            payload=payload,
            settings=self._debug_settings,
        )

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


def _retrieval_debug_payload(context: RetrievalContext | None) -> dict:
    if context is None:
        return {
            "query": None,
            "confidence": "not_configured",
            "fallback_reason": "retrieval_disabled",
            "selected_chunks": [],
            "citations": [],
        }
    return {
        "query": context.query,
        "confidence": context.safety_policy.confidence,
        "fallback_reason": context.safety_policy.fallback_reason,
        "selected_chunks": [
            {
                "chunk_id": result.chunk.chunk_id,
                "source_id": result.source.source_id,
                "source_title": result.source.title,
                "source_uri": result.source.uri,
                "section": result.chunk.section,
                "score": result.score,
                "bm25_score": result.bm25_score,
                "keyword_score": result.keyword_score,
                "vector_score": result.vector_score,
                "combined_score": result.combined_score,
            }
            for result in context.chunks
        ],
        "citations": [_citation_payload(citation) for citation in context.citations],
    }


def _apply_post_model_safety(
    text: str,
    context: RetrievalContext | None,
    pre_model_safety: SafetyAssessment,
) -> tuple[str, SafetyAssessment]:
    low_confidence_result = _apply_low_confidence_guard(text, context)
    if low_confidence_result.action != "none":
        return low_confidence_result.response_text or text, low_confidence_result

    output_safety = _classify_model_output(text)
    if output_safety.action != "none":
        return output_safety.response_text or text, output_safety
    return text, pre_model_safety


def _looks_like_procedural_tool_instruction(text: str) -> bool:
    imperative = re.compile(
        r"\b(press|hold|turn|cut|drill|wire|remove|install|set|configure|"
        r"tighten|loosen|disable|bypass|short|overload|ignite|dose|inject|invest)\b",
        re.IGNORECASE,
    )
    return bool(imperative.search(text))


def _apply_low_confidence_guard(
    text: str,
    context: RetrievalContext | None,
) -> SafetyAssessment:
    if context is None or context.safety_policy.confidence != "low_confidence":
        return SafetyAssessment()
    if not _looks_like_procedural_tool_instruction(text):
        return SafetyAssessment()
    return SafetyAssessment(
        category="retrieval_low_confidence",
        action="replaced_low_confidence_tool_instruction",
        reason="procedural_output_without_retrieval_support",
        response_text=(
            "I do not have enough trusted retrieval context to answer that safely. "
            "Please add or open the relevant manual/source, then ask again with the "
            "specific model, part, or procedure."
        ),
    )


def _classify_user_prompt(text: str) -> SafetyAssessment:
    normalized = text.lower()
    category = _risk_category(normalized)
    if category == "none":
        return SafetyAssessment()
    if category == "bypass_safety_controls" or _asks_for_instructions(normalized):
        return SafetyAssessment(
            category=category,
            action="pre_model_constrained",
            reason="high_risk_instruction_request",
            response_text=_safe_alternative_response(category),
        )
    return SafetyAssessment(category=category, action="flagged_for_model", reason="high_risk_topic")


def _classify_model_output(text: str) -> SafetyAssessment:
    normalized = text.lower()
    category = _risk_category(normalized)
    if category == "none" or not _looks_like_procedural_tool_instruction(normalized):
        return SafetyAssessment()
    return SafetyAssessment(
        category=category,
        action="post_model_replaced_unsafe_instruction",
        reason="unsafe_procedural_model_output",
        response_text=_safe_alternative_response(category),
    )


def _risk_category(text: str) -> str:
    checks = (
        (
            "bypass_safety_controls",
            r"\b(bypass|disable|remove|override|defeat)\b.*\b("
            r"safety|guard|interlock|lockout|fuse|breaker|limit)\b",
        ),
        (
            "electrical_fire_battery_risk",
            r"\b(lithium|battery|lipo|fire|mains|120v|240v|electrical|wire|short|"
            r"solder|charger|overload|ignite)\b",
        ),
        (
            "medical_legal_financial_advice",
            r"\b(medical|diagnos|medicine|dose|legal|lawsuit|contract|tax|invest|"
            r"stock|loan|insurance|financial)\b",
        ),
        (
            "dangerous_tool_operation",
            r"\b(table saw|circular saw|miter saw|angle grinder|drill press|laser cutter|"
            r"chainsaw|router|welding|welder|blade|cutting path|torque|calibration depth)\b",
        ),
    )
    for category, pattern in checks:
        if re.search(pattern, text, re.IGNORECASE):
            return category
    return "none"


def _asks_for_instructions(text: str) -> bool:
    return bool(
        re.search(
            r"\b(how|steps?|walk me through|tell me how|should i|what should i|"
            r"instructions?|procedure|configure|calibrate|install|remove|repair|fix)\b",
            text,
            re.IGNORECASE,
        ),
    )


def _safe_alternative_response(category: str) -> str:
    match category:
        case "dangerous_tool_operation":
            return (
                "I cannot provide step-by-step instructions for a high-risk tool operation. "
                "Use the manufacturer manual, keep guards and interlocks in place, wear the "
                "required PPE, and get help from a qualified operator before proceeding."
            )
        case "electrical_fire_battery_risk":
            return (
                "I cannot provide procedural instructions for electrical, fire, or battery "
                "risk. Stop if there is heat, swelling, smoke, exposed wiring, or uncertainty; "
                "use the manufacturer guidance and a qualified technician."
            )
        case "medical_legal_financial_advice":
            return (
                "I cannot give professional medical, legal, or financial advice. I can help "
                "organize questions and context, but you should consult a qualified professional "
                "for a decision."
            )
        case "bypass_safety_controls":
            return (
                "I cannot help bypass, remove, or disable safety controls. Keep safety systems "
                "enabled and use the documented procedure or a qualified technician."
            )
        case _:
            return (
                "I cannot provide instructions for that high-risk request. Use trusted source "
                "documentation or a qualified expert before proceeding."
            )
