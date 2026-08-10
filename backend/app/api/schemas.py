"""Request bodies for the REST API (responses are plain JSON dicts)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EmergencyStopBody(BaseModel):
    flatten: bool = False


class StrategyUpdateBody(BaseModel):
    enabled: bool | None = None
    params: dict | None = None
    symbols: list[str] | None = None
    use_scanner: bool | None = None


class BacktestCreateBody(BaseModel):
    strategy_id: str
    symbol: str
    start: str                      # ISO date, e.g. 2025-01-01
    end: str
    timeframe: str | None = None    # defaults to the strategy's timeframe param
    params: dict = Field(default_factory=dict)
    risk: dict = Field(default_factory=dict)   # overrides on stored risk config
    initial_equity: float = Field(10_000, gt=0)
    fee_bps: float = Field(10, ge=0, le=100)
    slippage_bps: float = Field(5, ge=0, le=100)
    label: str = ""
