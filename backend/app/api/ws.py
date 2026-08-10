"""Dashboard WebSocket: one multiplexed stream of engine events.

Message envelope: {"type": "...", "ts": iso8601, "data": {...}} where type is
one of app.core.types.EventType values (tick, candle, signal, order, trade,
position, equity, risk, status, scanner, error, alert) plus "hello".
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import ws_authorized
from app.core.events import EventBus

log = logging.getLogger("ws")
router = APIRouter()


class WSBroadcaster:
    def __init__(self, bus: EventBus):
        self._clients: set[asyncio.Queue] = set()
        bus.subscribe(self._on_event)

    async def _on_event(self, event: dict) -> None:
        for q in list(self._clients):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop oldest so the stream stays current.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)


@router.websocket("/ws/stream")
async def stream(ws: WebSocket):
    if not await ws_authorized(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    broadcaster: WSBroadcaster = ws.app.state.broadcaster
    engine = ws.app.state.engine
    q = broadcaster.register()
    try:
        await ws.send_json({"type": "hello",
                            "data": {"status": engine.status_payload(),
                                     "recent": list(engine.bus.recent)[-50:]}})
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "data": {}})
                continue
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        broadcaster.unregister(q)
