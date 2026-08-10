"""Shared test fixtures: symbol rules, risk config, account snapshots, candles."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from app.core.symbol_rules import SymbolRules
from app.core.types import AccountState, BotStatus, PositionView
from app.risk.models import RiskConfig


@pytest.fixture
def rules() -> SymbolRules:
    return SymbolRules(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
                       tick_size=Decimal("0.01"), step_size=Decimal("0.001"),
                       min_qty=Decimal("0.001"), min_notional=Decimal("5"))


@pytest.fixture
def risk_cfg() -> RiskConfig:
    return RiskConfig()  # project defaults: 2% size, 2% SL, 4% TP, 3% daily, 10% DD


def make_account(equity=10_000.0, day_start=None, peak=None,
                 status=BotStatus.RUNNING, positions=(), open_buys=None) -> AccountState:
    return AccountState(equity=equity,
                        day_start_equity=day_start if day_start is not None else equity,
                        peak_equity=peak if peak is not None else equity,
                        status=status, open_positions=list(positions),
                        open_buy_notional=dict(open_buys or {}))


def make_position(pid=1, symbol="BTCUSDT", strategy="trend_momentum", qty=0.01,
                  entry=100.0, mark=100.0) -> PositionView:
    return PositionView(pid, symbol, strategy, qty, entry, mark)


def make_df(closes, opens=None, highs=None, lows=None, start_ts=1_700_000_000_000,
            step_ms=3_600_000) -> pd.DataFrame:
    """Candle frame from close prices; open defaults to the previous close."""
    closes = [float(c) for c in closes]
    if opens is None:
        opens = [closes[0]] + closes[:-1]
    if highs is None:
        highs = [max(o, c) * 1.0005 for o, c in zip(opens, closes)]
    if lows is None:
        lows = [min(o, c) * 0.9995 for o, c in zip(opens, closes)]
    n = len(closes)
    return pd.DataFrame({
        "open_time": [start_ts + i * step_ms for i in range(n)],
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1.0] * n})
