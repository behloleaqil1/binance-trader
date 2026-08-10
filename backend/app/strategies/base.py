"""Strategy framework.

Contract that makes backtests honest: a strategy implements
  • compute_indicators(df)  — add indicator columns to a candle DataFrame
  • decide(df, i, position) — emit a Signal looking only at rows ≤ i
Live trading calls both on the latest data; the backtester computes indicators
once over the whole history and replays decide() row by row. Same code, no
lookahead (decide must never read past row i).

Every parameter is described by a ParamSpec so the dashboard can render a
settings form without hardcoding anything per strategy.
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd

from app.core.types import PositionView, Signal, SignalAction


@dataclass(slots=True)
class ParamSpec:
    name: str
    label: str
    type: str  # "int" | "float" | "bool" | "select" | "time"
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[str] = field(default_factory=list)
    help: str = ""

    def coerce(self, value: Any) -> Any:
        if self.type == "int":
            v = int(value)
        elif self.type == "float":
            v = float(value)
        elif self.type == "bool":
            v = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes")
        else:
            v = str(value)
            if self.choices and v not in self.choices:
                raise ValueError(f"{self.name}: {v!r} not in {self.choices}")
        if self.type in ("int", "float"):
            if self.min is not None and v < self.min:
                raise ValueError(f"{self.name}: {v} < min {self.min}")
            if self.max is not None and v > self.max:
                raise ValueError(f"{self.name}: {v} > max {self.max}")
        return v

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "type": self.type,
                "default": self.default, "min": self.min, "max": self.max,
                "step": self.step, "choices": self.choices, "help": self.help}


TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]


class Strategy(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    # "candle": evaluated on candle close. "grid": order-ladder reconciliation.
    # "schedule": time-driven (DCA).
    kind: ClassVar[str] = "candle"

    def __init__(self, params: dict | None = None):
        self.params = self.validate_params(params or {})

    # ── params ──────────────────────────────────────────────────────────────
    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        raise NotImplementedError

    @classmethod
    def default_params(cls) -> dict:
        return {p.name: p.default for p in cls.param_specs()}

    @classmethod
    def validate_params(cls, params: dict) -> dict:
        """Unknown keys are dropped; known keys coerced/range-checked."""
        specs = {p.name: p for p in cls.param_specs()}
        out = {}
        for name, spec in specs.items():
            out[name] = spec.coerce(params[name]) if name in params else spec.default
        return out

    @property
    def timeframe(self) -> str:
        return self.params.get("timeframe", "1h")

    def required_history(self) -> int:
        """Minimum candles before decide() may be trusted."""
        return 60

    # ── candle strategies ───────────────────────────────────────────────────
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        raise NotImplementedError

    def evaluate(self, symbol: str, candles: pd.DataFrame,
                 position: PositionView | None) -> Signal:
        """Live-path entry point: indicators over recent history, decide on last row."""
        if len(candles) < self.required_history():
            return Signal(SignalAction.HOLD, symbol, self.id,
                          f"warming up: {len(candles)}/{self.required_history()} candles")
        df = self.compute_indicators(candles)
        return self.decide(symbol, df, len(df) - 1, position)

    def hold(self, symbol: str, reason: str, price: float | None = None) -> Signal:
        return Signal(SignalAction.HOLD, symbol, self.id, reason, price=price)
