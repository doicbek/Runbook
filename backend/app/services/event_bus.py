import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """In-process asyncio.Queue-based pub/sub for SSE events."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, action_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
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
        payload = {"event": event_type, "data": data}
        for queue in self._subscribers.get(action_id, []):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for action {action_id}, dropping event")


# Global singleton
event_bus = EventBus()
