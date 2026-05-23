from dataclasses import dataclass

from manfriday.config.settings import Settings


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
