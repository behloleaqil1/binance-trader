"""In-process pub/sub bus.

Publishers: engine, order manager, portfolio. Subscribers: the dashboard
WebSocket broadcaster, the alert notifier, and the structured log. Events are
plain dicts so they serialize straight to WS clients.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.types import EventType

log = logging.getLogger("events")

Subscriber = Callable[[dict], Awaitable[None]]


class EventBus:
    def __init__(self, history: int = 200):
        self._subs: list[Subscriber] = []
        self.recent: deque[dict] = deque(maxlen=history)

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def publish(self, etype: EventType, data: dict[str, Any]) -> None:
        """Fire-and-forget; a slow/broken subscriber never blocks trading."""
        event = {"type": etype.value,
                 "ts": datetime.now(timezone.utc).isoformat(),
                 "data": data}
        self.recent.append(event)
        for fn in self._subs:
            try:
                task = asyncio.create_task(fn(event))
                task.add_done_callback(_log_subscriber_error)
            except RuntimeError:
                pass  # no running loop (unit tests) — events are best-effort


def _log_subscriber_error(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        log.warning("event subscriber failed: %r", task.exception())
