from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from uuid import uuid4

from manfriday.events import EventBus, EventEnvelope
from manfriday.sessions import Session
from manfriday.voice_agent.providers import AudioInput
from manfriday.voice_agent.turn import VoiceTurnOrchestrator, VoiceTurnResult


@dataclass(frozen=True)
class PushToTalkStart:
    session_id: str
    turn_id: str
    status: str
    started_at: datetime
    max_duration_seconds: int


@dataclass(frozen=True)
class PushToTalkRelease:
    session_id: str
    turn_id: str
    status: str
    result: VoiceTurnResult | None = None


@dataclass
class ActivePushToTalkTurn:
    session_id: str
    turn_id: str
    started_at: datetime


class PushToTalkError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        http_status: HTTPStatus = HTTPStatus.CONFLICT,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


class PushToTalkCoordinator:
    def __init__(
        self,
        *,
        orchestrator: VoiceTurnOrchestrator,
        event_bus: EventBus,
        max_duration_seconds: int,
        now_fn=None,
    ) -> None:
        self._orchestrator = orchestrator
        self._event_bus = event_bus
        self._max_duration = timedelta(seconds=max_duration_seconds)
        self._max_duration_seconds = max_duration_seconds
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._active_turns: dict[str, ActivePushToTalkTurn] = {}

    async def start(self, session: Session) -> PushToTalkStart:
        existing = self._active_turns.get(session.session_id)
        if existing is not None:
            raise PushToTalkError(
                code="turn_already_active",
                message="A push-to-talk turn is already active.",
                retryable=True,
            )
        started_at = self._now()
        turn = ActivePushToTalkTurn(
            session_id=session.session_id,
            turn_id=f"turn_{uuid4().hex}",
            started_at=started_at,
        )
        self._active_turns[session.session_id] = turn
        await self._publish_state(
            session_id=session.session_id,
            turn_id=turn.turn_id,
            assistant_state="listening",
            reason="push_to_talk_started",
        )
        return PushToTalkStart(
            session_id=session.session_id,
            turn_id=turn.turn_id,
            status="listening",
            started_at=started_at,
            max_duration_seconds=self._max_duration_seconds,
        )

    async def release(
        self,
        *,
        session: Session,
        audio_ref: str | None = None,
        user_text: str | None = None,
        has_speech: bool,
    ) -> PushToTalkRelease:
        turn = self._active_turns.get(session.session_id)
        if turn is None:
            raise PushToTalkError(
                code="turn_not_active",
                message="No push-to-talk turn is active.",
                retryable=True,
            )
        elapsed = self._now() - turn.started_at
        if elapsed > self._max_duration:
            self._active_turns.pop(session.session_id, None)
            await self._publish_error(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                code="recording_duration_exceeded",
                message="Push-to-talk recording exceeded the maximum duration.",
                retryable=True,
            )
            await self._publish_state(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                assistant_state="idle",
                reason="recording_duration_exceeded",
            )
            raise PushToTalkError(
                code="recording_duration_exceeded",
                message="Push-to-talk recording exceeded the maximum duration.",
                retryable=True,
            )
        clean_user_text = user_text.strip() if user_text is not None else None
        if not has_speech or clean_user_text == "":
            self._active_turns.pop(session.session_id, None)
            await self._publish_error(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                code="no_speech_detected",
                message="Push-to-talk was released before speech was detected.",
                retryable=True,
            )
            await self._publish_state(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                assistant_state="idle",
                reason="no_speech_detected",
            )
            return PushToTalkRelease(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                status="discarded",
            )

        try:
            audio = (
                AudioInput(content=audio_ref.encode(), mime_type="audio/mock")
                if audio_ref is not None
                else None
            )
            result = await self._orchestrator.run_turn(
                session_id=session.session_id,
                audio=audio,
                user_text=clean_user_text,
                session_memory=session.memory,
                turn_id=turn.turn_id,
                synthesize_audio=clean_user_text is None,
            )
            return PushToTalkRelease(
                session_id=session.session_id,
                turn_id=turn.turn_id,
                status="completed",
                result=result,
            )
        finally:
            self._active_turns.pop(session.session_id, None)

    def active_turn(self, session_id: str) -> ActivePushToTalkTurn | None:
        return self._active_turns.get(session_id)

    async def _publish_state(
        self,
        *,
        session_id: str,
        turn_id: str,
        assistant_state: str,
        reason: str,
    ) -> None:
        await self._event_bus.publish(
            EventEnvelope(
                type="assistant.state.changed",
                session_id=session_id,
                payload={
                    "turn_id": turn_id,
                    "assistant_state": assistant_state,
                    "reason": reason,
                },
            ),
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
        await self._event_bus.publish(
            EventEnvelope(
                type="assistant.error",
                session_id=session_id,
                payload={
                    "turn_id": turn_id,
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                },
            ),
        )

    def _now(self) -> datetime:
        now = self._now_fn()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now
