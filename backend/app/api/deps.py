"""Shared FastAPI dependencies: engine access and session authentication."""
from __future__ import annotations

from fastapi import Request, WebSocket

from app.auth import require_session, validate_session
from app.core.engine import TradingEngine

# Every /api router (except /api/auth/login and /api/health) depends on this.
require_auth = require_session


def get_engine(request: Request) -> TradingEngine:
    return request.app.state.engine


async def ws_authorized(ws: WebSocket) -> bool:
    return await validate_session(ws.query_params.get("token", "")) is not None
