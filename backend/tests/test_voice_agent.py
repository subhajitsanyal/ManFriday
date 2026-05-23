from manfriday.config.settings import Settings
from manfriday.voice_agent import VoiceAgentWorker


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
