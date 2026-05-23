from manfriday.config.settings import get_settings
from manfriday.voice_agent.worker import VoiceAgentWorker


def main() -> None:
    worker = VoiceAgentWorker(settings=get_settings())
    worker.start()
