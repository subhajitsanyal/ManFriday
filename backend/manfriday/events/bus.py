import asyncio
from contextlib import suppress

from manfriday.events.models import EventEnvelope


class EventBus:
    def __init__(self, queue_limit: int) -> None:
        self._queue_limit = queue_limit
        self._subscribers: dict[str, set[asyncio.Queue[EventEnvelope]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=self._queue_limit)
        self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[EventEnvelope]) -> None:
        subscribers = self._subscribers.get(session_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(session_id, None)

    async def publish(self, event: EventEnvelope) -> None:
        for queue in list(self._subscribers.get(event.session_id, set())):
            with suppress(asyncio.QueueFull):
                queue.put_nowait(event)
