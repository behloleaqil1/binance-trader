"""Registry of pluggable strategies. Adding a strategy = subclass + one entry here."""
from __future__ import annotations

from app.strategies.base import Strategy
from app.strategies.dca import DCAStrategy
from app.strategies.grid import GridStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy

STRATEGY_CLASSES: dict[str, type[Strategy]] = {
    cls.id: cls for cls in (
        TrendMomentumStrategy,
        MeanReversionStrategy,
        GridStrategy,
        DCAStrategy,
    )
}


def build(strategy_id: str, params: dict | None = None) -> Strategy:
    if strategy_id not in STRATEGY_CLASSES:
        raise KeyError(f"unknown strategy: {strategy_id!r}")
    return STRATEGY_CLASSES[strategy_id](params)
