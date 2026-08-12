"""FastAPI application entry point.

Run (from backend/):  uvicorn app.main:app --port 8000
The React dashboard talks to /api/* and /ws/stream.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import auth, settings_store
from app.api import (routes_backtest, routes_bot, routes_data, routes_settings,
                     routes_strategies, ws)
from app.api.deps import require_auth
from app.alerts.notifier import Notifier
from app.config import get_settings
from app.core.engine import TradingEngine
from app.core.events import EventBus
from app.db import database
from app.logging_setup import setup_logging

log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    await auth.ensure_auth_seed(settings)
    await settings_store.apply_overrides(settings)  # UI-saved settings win over .env

    bus = EventBus()
    engine = TradingEngine(settings, bus)
    engine.bus = bus
    app.state.engine = engine
    app.state.broadcaster = ws.WSBroadcaster(bus)
    app.state.notifier = Notifier(settings, bus)

    await engine.reload_configs()
    mode = "TESTNET" if settings.testnet else "⚠️  LIVE TRADING"
    log.info("─" * 60)
    log.info("Binance trader backend up — %s | keys: %s | auto_start: %s",
             mode, settings.masked_key(), settings.auto_start)
    log.info("─" * 60)
    # Auto-start the engine in the BACKGROUND so uvicorn reaches `yield` and
    # begins serving immediately. engine.start() does a slow bootstrap (clock
    # sync, gateway init, scanner scan, ~21 market-stream websockets) that can
    # take 20-60s; running it inline blocked the socket bind, so /api/health
    # (and every endpoint) was unreachable until warmup finished — which false-
    # failed the deploy health-check and hid the API during every restart.
    start_task: asyncio.Task | None = None
    if settings.auto_start and settings.has_keys:
        async def _bg_start() -> None:
            try:
                await engine.start()
            except Exception as e:  # noqa: BLE001 — surface in status, don't crash boot
                log.error("auto-start failed: %s", e)
        start_task = asyncio.create_task(_bg_start())
    try:
        yield
    finally:
        if start_task is not None and not start_task.done():
            start_task.cancel()
        await engine.shutdown()
        await database.dispose()


app = FastAPI(title="Binance Algorithmic Trading Bot", version="1.0.0",
              lifespan=lifespan)

_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:8080", "http://127.0.0.1:8080"]
# Extra origins for a hosted dashboard (e.g. https://bot.example.com), comma-
# separated in CORS_ORIGINS. Bearer-token auth (localStorage), so no cookies.
_extra = [o.strip() for o in (get_settings().cors_origins or "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra,
    allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api")  # /login is open; rest self-guarded
for r in (routes_bot.router, routes_data.router, routes_strategies.router,
          routes_backtest.router, routes_settings.router):
    app.include_router(r, prefix="/api", dependencies=[Depends(require_auth)])
app.include_router(ws.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
