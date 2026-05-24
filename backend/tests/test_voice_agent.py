import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from manfriday.config.settings import Settings
from manfriday.events import EventBus
from manfriday.frames import FrameStore
from manfriday.voice_agent import (
    AudioInput,
    BedrockClaudeModel,
    BinaryResponse,
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    MockVisionLanguageModel,
    ModelTurnRequest,
    MultipartFile,
    OpenAISpeechToTextProvider,
    OpenAITextToSpeechProvider,
    OpenAIVisionLanguageModel,
    PushToTalkCoordinator,
    PushToTalkError,
    VoiceAgentWorker,
    VoiceTurnError,
    VoiceTurnOrchestrator,
    build_bedrock_client,
    build_openai_client,
)


def test_voice_agent_worker_describes_livekit_connection() -> None:
    worker = VoiceAgentWorker(
        Settings(
            MANFRIDAY_LOCAL_SECRET="test-secret",
            LIVEKIT_URL="ws://livekit.test:7880",
        ),
    )

    assert worker.describe_connection() == {
        "livekit_url": "ws://livekit.test:7880",
        "agent_identity": "manfriday-agent",
    }


def test_mock_turn_emits_transcript_response_events_and_updates_memory() -> None:
    result, events, memory = asyncio.run(_run_turn_with_fixture_frame())

    assert result.frame_id is not None
    assert result.visual_status == "healthy"
    assert result.audio.mime_type == "audio/mock"
    assert [event.type for event in events] == [
        "assistant.state.changed",
        "assistant.transcript.delta",
        "assistant.response.started",
        "assistant.transcript.delta",
        "assistant.response.completed",
        "assistant.state.changed",
    ]
    assert events[1].payload["role"] == "user"
    assert events[1].payload["text"] == "What am I looking at?"
    assert events[2].payload["frame_id"] == result.frame_id
    assert events[2].payload["visual_context"] == "frame"
    assert events[3].payload["role"] == "assistant"
    assert events[4].payload["tts_audio_ref"] == f"mock://tts/{result.turn_id}"
    assert memory["turns"] == [
        {
            "turn_id": result.turn_id,
            "user_text": result.user_text,
            "assistant_text": result.assistant_text,
            "frame_id": result.frame_id,
        },
    ]


def test_mock_turn_prefers_pinned_frame_over_latest_frame() -> None:
    frame_store = _frame_store()
    now = datetime.now(UTC)
    first = frame_store.seed_fixture_frame(now)
    pinned = frame_store.pin_latest(now + timedelta(seconds=1))
    frame_store.seed_fixture_frame(now + timedelta(seconds=2))

    result, _, _ = asyncio.run(_run_turn(frame_store=frame_store))

    assert pinned is not None
    assert pinned.frame_id == first.frame_id
    assert result.frame_id == pinned.frame_id


def test_mock_turn_completes_without_fresh_frame() -> None:
    frame_store = _frame_store()
    stale = frame_store.seed_fixture_frame(datetime.now(UTC) - timedelta(seconds=10))

    result, events, _ = asyncio.run(_run_turn(frame_store=frame_store))

    assert stale.frame_id is not None
    assert result.frame_id is None
    assert result.visual_status == "degraded"
    assert events[2].payload["visual_context"] == "unavailable"
    assert events[2].payload["visual_status"] == "degraded"
    assert "do not have a fresh frame" in result.assistant_text


def test_empty_stt_text_emits_retryable_error_and_stops_turn() -> None:
    frame_store = _frame_store()

    events = asyncio.run(
        _run_turn_expect_error(
            frame_store=frame_store,
            stt_provider=MockSpeechToTextProvider(text=""),
        ),
    )

    assert [event.type for event in events] == [
        "assistant.state.changed",
        "assistant.error",
    ]
    assert events[-1].payload["code"] == "empty_transcript"
    assert events[-1].payload["retryable"] is True


def test_provider_failure_emits_error_and_does_not_call_later_providers() -> None:
    frame_store = _frame_store()
    tts_provider = CountingTtsProvider()

    events = asyncio.run(
        _run_turn_expect_error(
            frame_store=frame_store,
            model_provider=FailingModelProvider(),
            tts_provider=tts_provider,
        ),
    )

    assert events[-1].type == "assistant.error"
    assert events[-1].payload["code"] == "model_failed"
    assert tts_provider.call_count == 0


def test_openai_stt_provider_posts_audio_transcription_request() -> None:
    client = FakeOpenAIClient()
    provider = OpenAISpeechToTextProvider(client=client, model="gpt-4o-mini-transcribe")

    transcript = provider.transcribe(AudioInput(content=b"wav-data", mime_type="audio/wav"))

    assert transcript.text == "What is this part?"
    assert client.multipart_requests == [
        {
            "path": "/audio/transcriptions",
            "fields": {"model": "gpt-4o-mini-transcribe", "response_format": "json"},
            "filename": "turn-audio.wav",
            "content": b"wav-data",
            "mime_type": "audio/wav",
        },
    ]


def test_openai_model_provider_uses_responses_api_and_extracts_text() -> None:
    client = FakeOpenAIClient()
    provider = OpenAIVisionLanguageModel(client=client, model="gpt-4.1-mini")

    response = provider.complete_turn(
        ModelTurnRequest(
            turn_id="turn_test",
            session_id="sess_test",
            user_text="What is this part?",
            frame_id="frame_123",
            visual_status="healthy",
        ),
    )

    assert response.text == "That looks like a fixture response."
    assert client.json_requests[0]["path"] == "/responses"
    assert client.json_requests[0]["payload"]["model"] == "gpt-4.1-mini"
    assert "frame_123" in client.json_requests[0]["payload"]["input"]
    assert "What is this part?" in client.json_requests[0]["payload"]["input"]


def test_openai_tts_provider_posts_speech_request() -> None:
    client = FakeOpenAIClient()
    provider = OpenAITextToSpeechProvider(
        client=client,
        model="gpt-4o-mini-tts",
        voice="alloy",
    )

    audio = provider.synthesize("A concise answer.")

    assert audio.content == b"wav-response"
    assert audio.mime_type == "audio/wav"
    assert client.binary_requests == [
        {
            "path": "/audio/speech",
            "payload": {
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
                "input": "A concise answer.",
                "response_format": "wav",
            },
        },
    ]


def test_worker_builds_openai_orchestrator_from_config() -> None:
    worker = VoiceAgentWorker(
        Settings(
            MANFRIDAY_LOCAL_SECRET="test-secret",
            MODEL_API_KEY="test-openai-key",
        ),
    )

    orchestrator = worker.build_openai_turn_orchestrator(
        frame_store=_frame_store(),
        event_bus=EventBus(queue_limit=16),
    )

    assert isinstance(orchestrator, VoiceTurnOrchestrator)


def test_openai_client_requires_model_api_key() -> None:
    settings = Settings(MANFRIDAY_LOCAL_SECRET="test-secret", MODEL_API_KEY=None)

    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        build_openai_client(settings)


def test_bedrock_claude_model_invokes_anthropic_messages_payload() -> None:
    client = FakeBedrockClient()
    provider = BedrockClaudeModel(
        client=client,
        model_id="anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=512,
    )

    response = provider.complete_turn(
        ModelTurnRequest(
            turn_id="turn_test",
            session_id="sess_test",
            user_text="What is this part?",
            frame_id="frame_123",
            visual_status="healthy",
        ),
    )

    assert response.text == "That is a Bedrock fixture response."
    assert client.invocations == [
        {
            "model_id": "anthropic.claude-haiku-4-5-20251001-v1:0",
            "payload": {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "system": "You are Man Friday, a concise workbench copilot.",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Answer the user's question using the visual context when "
                                    "available.\n\nVisual status: healthy\nSelected frame ID: "
                                    "frame_123.\nUser question: What is this part?"
                                ),
                            },
                        ],
                    },
                ],
            },
        },
    ]


def test_worker_builds_bedrock_orchestrator_from_config() -> None:
    worker = VoiceAgentWorker(
        Settings(
            MANFRIDAY_LOCAL_SECRET="test-secret",
            MODEL_PROVIDER="bedrock",
            AWS_ACCESS_KEY_ID="test-access-key",
            AWS_SECRET_ACCESS_KEY="test-secret-key",
        ),
    )

    orchestrator = worker.build_bedrock_turn_orchestrator(
        frame_store=_frame_store(),
        event_bus=EventBus(queue_limit=16),
    )

    assert isinstance(orchestrator, VoiceTurnOrchestrator)


def test_bedrock_client_requires_aws_credentials() -> None:
    settings = Settings(
        MANFRIDAY_LOCAL_SECRET="test-secret",
        MODEL_PROVIDER="bedrock",
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
    )

    with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
        build_bedrock_client(settings)


def test_push_to_talk_start_and_release_runs_mock_turn() -> None:
    result, events, session = asyncio.run(_run_push_to_talk_release(has_speech=True))

    assert result.status == "completed"
    assert result.turn_id == events[0].payload["turn_id"]
    assert [event.type for event in events] == [
        "assistant.state.changed",
        "assistant.state.changed",
        "assistant.transcript.delta",
        "assistant.response.started",
        "assistant.transcript.delta",
        "assistant.response.completed",
        "assistant.state.changed",
    ]
    assert events[0].payload["assistant_state"] == "listening"
    assert events[1].payload["assistant_state"] == "thinking"
    assert events[-1].payload["assistant_state"] == "idle"
    assert session.memory["turns"][0]["turn_id"] == result.turn_id


def test_push_to_talk_release_with_android_text_skips_backend_stt_and_tts() -> None:
    result, events, session = asyncio.run(
        _run_push_to_talk_release(
            has_speech=True,
            user_text="What is on the workbench?",
            stt_provider=_FailingSpeechToTextProvider(),
            tts_provider=_FailingTextToSpeechProvider(),
        ),
    )

    assert result.status == "completed"
    assert result.result is not None
    assert result.result.user_text == "What is on the workbench?"
    assert result.result.audio.mime_type == "audio/android-tts"
    assert result.result.audio.content == b""
    assert session.memory["turns"][0]["user_text"] == "What is on the workbench?"
    completed = next(event for event in events if event.type == "assistant.response.completed")
    assert completed.payload["tts_audio_ref"] is None
    assert completed.payload["timing_ms"]["stt"] == 0
    assert completed.payload["timing_ms"]["tts"] == 0


def test_push_to_talk_release_without_speech_discards_turn() -> None:
    result, events, session = asyncio.run(_run_push_to_talk_release(has_speech=False))

    assert result.status == "discarded"
    assert "turns" not in session.memory
    assert [event.type for event in events] == [
        "assistant.state.changed",
        "assistant.error",
        "assistant.state.changed",
    ]
    assert events[1].payload["code"] == "no_speech_detected"
    assert events[-1].payload["assistant_state"] == "idle"


def test_push_to_talk_rejects_release_after_max_duration() -> None:
    now = datetime.now(UTC)

    with pytest.raises(PushToTalkError) as exc_info:
        asyncio.run(
            _run_push_to_talk_release(
                has_speech=True,
                max_duration_seconds=20,
                now_values=[now, now + timedelta(seconds=21)],
            ),
        )

    assert exc_info.value.code == "recording_duration_exceeded"


async def _run_turn_with_fixture_frame():
    frame_store = _frame_store()
    frame_store.seed_fixture_frame()
    return await _run_turn(frame_store=frame_store)


async def _run_turn(
    *,
    frame_store: FrameStore,
    stt_provider=None,
    model_provider=None,
    tts_provider=None,
):
    session_id = "sess_test"
    memory: dict = {}
    event_bus = EventBus(queue_limit=16)
    queue = event_bus.subscribe(session_id)
    orchestrator = VoiceTurnOrchestrator(
        stt_provider=stt_provider or MockSpeechToTextProvider(),
        model_provider=model_provider or MockVisionLanguageModel(),
        tts_provider=tts_provider or MockTextToSpeechProvider(),
        frame_store=frame_store,
        event_bus=event_bus,
    )
    result = await orchestrator.run_turn(
        session_id=session_id,
        audio=AudioInput(content=b"audio"),
        session_memory=memory,
    )
    return result, _drain_events(queue), memory


async def _run_turn_expect_error(
    *,
    frame_store: FrameStore,
    stt_provider=None,
    model_provider=None,
    tts_provider=None,
):
    session_id = "sess_test"
    event_bus = EventBus(queue_limit=16)
    queue = event_bus.subscribe(session_id)
    orchestrator = VoiceTurnOrchestrator(
        stt_provider=stt_provider or MockSpeechToTextProvider(),
        model_provider=model_provider or MockVisionLanguageModel(),
        tts_provider=tts_provider or MockTextToSpeechProvider(),
        frame_store=frame_store,
        event_bus=event_bus,
    )
    with pytest.raises(VoiceTurnError):
        await orchestrator.run_turn(
            session_id=session_id,
            audio=AudioInput(content=b"audio"),
            session_memory={},
        )
    return _drain_events(queue)


async def _run_push_to_talk_release(
    *,
    has_speech: bool,
    user_text: str | None = None,
    stt_provider=None,
    tts_provider=None,
    max_duration_seconds: int = 20,
    now_values: list[datetime] | None = None,
):
    session_id = "sess_test"
    frame_store = _frame_store()
    frame_store.seed_fixture_frame()
    event_bus = EventBus(queue_limit=16)
    queue = event_bus.subscribe(session_id)
    orchestrator = VoiceTurnOrchestrator(
        stt_provider=stt_provider or MockSpeechToTextProvider(),
        model_provider=MockVisionLanguageModel(),
        tts_provider=tts_provider or MockTextToSpeechProvider(),
        frame_store=frame_store,
        event_bus=event_bus,
    )
    now_iter = iter(now_values) if now_values is not None else None
    coordinator = PushToTalkCoordinator(
        orchestrator=orchestrator,
        event_bus=event_bus,
        max_duration_seconds=max_duration_seconds,
        now_fn=(lambda: next(now_iter)) if now_iter is not None else None,
    )
    session = _session(session_id)
    await coordinator.start(session)
    result = await coordinator.release(
        session=session,
        audio_ref="mock://audio/test",
        user_text=user_text,
        has_speech=has_speech,
    )
    return result, _drain_events(queue), session


class _FailingSpeechToTextProvider:
    def transcribe(self, audio: AudioInput):
        raise AssertionError("Backend STT should not run for Android text turns.")


class _FailingTextToSpeechProvider:
    def synthesize(self, text: str):
        raise AssertionError("Backend TTS should not run for Android text turns.")


def _drain_events(queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


def _frame_store() -> FrameStore:
    return FrameStore(look_ttl_seconds=60, stale_after_seconds=5)


def _session(session_id: str):
    from manfriday.sessions import Session

    now = datetime.now(UTC)
    return Session(
        session_id=session_id,
        livekit_room_name=f"manfriday_{session_id}",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=1),
    )


class FailingModelProvider:
    def complete_turn(self, request):
        raise RuntimeError("mock model failed")


class CountingTtsProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def synthesize(self, text: str):
        self.call_count += 1
        return MockTextToSpeechProvider().synthesize(text)


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.json_requests = []
        self.multipart_requests = []
        self.binary_requests = []

    def post_json(self, path: str, payload: dict) -> dict:
        self.json_requests.append({"path": path, "payload": payload})
        return {"output_text": "That looks like a fixture response."}

    def post_multipart(self, path: str, fields: dict[str, str], file: MultipartFile) -> dict:
        self.multipart_requests.append(
            {
                "path": path,
                "fields": fields,
                "filename": file.filename,
                "content": file.content,
                "mime_type": file.mime_type,
            },
        )
        return {"text": "What is this part?"}

    def post_binary_json(self, path: str, payload: dict) -> BinaryResponse:
        self.binary_requests.append({"path": path, "payload": payload})
        return BinaryResponse(content=b"wav-response", mime_type="audio/wav")


class FakeBedrockClient:
    def __init__(self) -> None:
        self.invocations = []

    def invoke_model(self, *, model_id: str, payload: dict) -> dict:
        self.invocations.append({"model_id": model_id, "payload": payload})
        return {
            "content": [
                {
                    "type": "text",
                    "text": "That is a Bedrock fixture response.",
                },
            ],
        }
