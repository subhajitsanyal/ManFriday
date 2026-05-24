import argparse
import asyncio
import json

from manfriday.config.settings import Settings
from manfriday.events import EventBus
from manfriday.frames import FrameStore
from manfriday.voice_agent.worker import VoiceAgentWorker


async def _run(question: str, *, seed_frame: bool) -> dict:
    settings = Settings()
    event_bus = EventBus(queue_limit=settings.websocket_queue_limit)
    frame_store = FrameStore(
        look_ttl_seconds=settings.frame_look_ttl_seconds,
        stale_after_seconds=settings.frame_stale_after_seconds,
    )
    if seed_frame:
        frame_store.seed_fixture_frame()
    orchestrator = VoiceAgentWorker(settings=settings).build_turn_orchestrator(
        frame_store=frame_store,
        event_bus=event_bus,
    )
    result = await orchestrator.run_turn(
        session_id="smoke_session",
        user_text=question,
        synthesize_audio=False,
    )
    return {
        "provider": settings.model_provider,
        "model": settings.model_name,
        "turn_id": result.turn_id,
        "user_text": result.user_text,
        "assistant_text": result.assistant_text,
        "frame_id": result.frame_id,
        "visual_status": result.visual_status,
        "timing_ms": result.timing_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one configured Man Friday voice turn.")
    parser.add_argument(
        "question",
        nargs="?",
        default="Reply with exactly: manfriday smoke ok",
    )
    parser.add_argument(
        "--no-frame",
        action="store_true",
        help="Do not seed a fixture frame before the turn.",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.question, seed_frame=not args.no_frame)), indent=2))


if __name__ == "__main__":
    main()
