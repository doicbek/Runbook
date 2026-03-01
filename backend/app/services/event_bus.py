import asyncio
import logging
from collections import defaultdict, deque
from typing import Any

logger = logging.getLogger(__name__)


QUEUE_MAX_SIZE = 500
QUEUE_HIGH_WATERMARK = 400


class EventBus:
    """In-process asyncio.Queue-based pub/sub for SSE events."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._event_counters: dict[str, int] = defaultdict(int)
        self._event_history: dict[str, deque] = {}

    def subscribe(self, action_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._subscribers[action_id].append(queue)
        return queue

    def unsubscribe(self, action_id: str, queue: asyncio.Queue):
        if action_id in self._subscribers:
            try:
                self._subscribers[action_id].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[action_id]:
                del self._subscribers[action_id]

    async def publish(self, action_id: str, event_type: str, data: dict[str, Any]):
        self._event_counters[action_id] += 1
        event_id = self._event_counters[action_id]

        payload = {"id": event_id, "event": event_type, "data": data}

        # Store in ring buffer
        if action_id not in self._event_history:
            self._event_history[action_id] = deque(maxlen=100)
        self._event_history[action_id].append(payload)

        for queue in self._subscribers.get(action_id, []):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Evict oldest event to make room
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(payload)
                logger.warning(
                    f"Queue full for action {action_id}, evicted oldest event"
                )
            if queue.qsize() > QUEUE_HIGH_WATERMARK:
                logger.warning(
                    f"Queue depth {queue.qsize()}/{QUEUE_MAX_SIZE} for action {action_id} "
                    f"exceeds 80%% capacity"
                )

    def replay_from(self, action_id: str, last_event_id: int) -> list[dict[str, Any]]:
        """Return events with id > last_event_id from the ring buffer."""
        history = self._event_history.get(action_id)
        if not history:
            return []
        return [event for event in history if event["id"] > last_event_id]

    def queue_depth(self, action_id: str) -> dict[str, int]:
        """Return current depth per subscriber queue for the given action."""
        queues = self._subscribers.get(action_id, [])
        return {f"subscriber_{i}": q.qsize() for i, q in enumerate(queues)}

    def clear_history(self, action_id: str):
        """Clear ring buffer and counter for an action."""
        self._event_history.pop(action_id, None)
        self._event_counters.pop(action_id, None)


# Global singleton
event_bus = EventBus()
