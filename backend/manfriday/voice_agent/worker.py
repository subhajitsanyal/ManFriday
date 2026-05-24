from dataclasses import dataclass

from manfriday.config.settings import Settings
from manfriday.events import EventBus
from manfriday.frames import FrameStore
from manfriday.voice_agent.bedrock_provider import BedrockClaudeModel, build_bedrock_client
from manfriday.voice_agent.openai_provider import (
    OpenAISpeechToTextProvider,
    OpenAITextToSpeechProvider,
    OpenAIVisionLanguageModel,
    build_openai_client,
)
from manfriday.voice_agent.providers import (
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    MockVisionLanguageModel,
)
from manfriday.voice_agent.turn import VoiceTurnOrchestrator


@dataclass
class VoiceAgentWorker:
    settings: Settings

    def start(self) -> None:
        # The real LiveKit Agents loop lands in Phase 3. Phase 1 gives manual
        # dev mode a separate worker entrypoint and validates room config.
        self.describe_connection()

    def describe_connection(self) -> dict[str, str]:
        return {
            "livekit_url": self.settings.livekit_url,
            "agent_identity": "manfriday-agent",
        }

    def build_mock_turn_orchestrator(
        self,
        *,
        frame_store: FrameStore,
        event_bus: EventBus,
    ) -> VoiceTurnOrchestrator:
        return VoiceTurnOrchestrator(
            stt_provider=MockSpeechToTextProvider(),
            model_provider=MockVisionLanguageModel(),
            tts_provider=MockTextToSpeechProvider(),
            frame_store=frame_store,
            event_bus=event_bus,
        )

    def build_openai_turn_orchestrator(
        self,
        *,
        frame_store: FrameStore,
        event_bus: EventBus,
    ) -> VoiceTurnOrchestrator:
        client = build_openai_client(self.settings)
        return VoiceTurnOrchestrator(
            stt_provider=OpenAISpeechToTextProvider(
                client=client,
                model=self.settings.stt_model,
            ),
            model_provider=OpenAIVisionLanguageModel(
                client=client,
                model=self.settings.model_name,
            ),
            tts_provider=OpenAITextToSpeechProvider(
                client=client,
                model=self.settings.tts_model,
                voice=self.settings.tts_voice,
            ),
            frame_store=frame_store,
            event_bus=event_bus,
        )

    def build_bedrock_turn_orchestrator(
        self,
        *,
        frame_store: FrameStore,
        event_bus: EventBus,
    ) -> VoiceTurnOrchestrator:
        client = build_bedrock_client(self.settings)
        return VoiceTurnOrchestrator(
            stt_provider=MockSpeechToTextProvider(),
            model_provider=BedrockClaudeModel(
                client=client,
                model_id=self.settings.model_name,
                max_tokens=self.settings.bedrock_max_tokens,
            ),
            tts_provider=MockTextToSpeechProvider(),
            frame_store=frame_store,
            event_bus=event_bus,
        )
