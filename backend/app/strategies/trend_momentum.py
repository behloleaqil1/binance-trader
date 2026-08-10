"""Trend/momentum strategy: EMA crossover entry, filtered by RSI, confirmed by MACD."""
from __future__ import annotations

import math

import pandas as pd

from app.core.types import PositionView, Signal, SignalAction
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.strategies.indicators import ema, macd, rsi


class TrendMomentumStrategy(Strategy):
    id = "trend_momentum"
    name = "Trend / Momentum"
    description = ("Buys when the fast EMA crosses above the slow EMA with RSI in a "
                   "healthy band and MACD histogram positive. Exits on cross-down, "
                   "RSI blow-off, or MACD rollover. Long-only (spot).")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("ema_fast", "Fast EMA", "int", 20, min=2, max=200),
            ParamSpec("ema_slow", "Slow EMA", "int", 50, min=5, max=400),
            ParamSpec("rsi_period", "RSI period", "int", 14, min=2, max=50),
            ParamSpec("rsi_buy_min", "RSI min for entry", "float", 50, min=0, max=100,
                      help="Entry requires RSI above this (momentum present)"),
            ParamSpec("rsi_buy_max", "RSI max for entry", "float", 70, min=0, max=100,
                      help="Entry blocked above this (already overbought)"),
            ParamSpec("rsi_exit", "RSI exit level", "float", 78, min=50, max=100),
            ParamSpec("macd_fast", "MACD fast", "int", 12, min=2, max=100),
            ParamSpec("macd_slow", "MACD slow", "int", 26, min=5, max=200),
            ParamSpec("macd_signal", "MACD signal", "int", 9, min=2, max=50),
            ParamSpec("require_macd", "Require MACD confirmation", "bool", True),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["ema_slow"], p["macd_slow"] + p["macd_signal"], p["rsi_period"]) + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        out["ema_fast"] = ema(df["close"], p["ema_fast"])
        out["ema_slow"] = ema(df["close"], p["ema_slow"])
        out["rsi"] = rsi(df["close"], p["rsi_period"])
        _, _, out["macd_hist"] = macd(df["close"], p["macd_fast"], p["macd_slow"],
                                      p["macd_signal"])
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row, prev = df.iloc[i], df.iloc[i - 1]
        close = float(row["close"])
        ef, es, r, hist = (float(row["ema_fast"]), float(row["ema_slow"]),
                           float(row["rsi"]), float(row["macd_hist"]))
        if any(math.isnan(v) for v in (ef, es, r, hist,
                                       float(prev["ema_fast"]), float(prev["ema_slow"]))):
            return self.hold(symbol, "indicators warming up")

        crossed_up = float(prev["ema_fast"]) <= float(prev["ema_slow"]) and ef > es
        crossed_down = float(prev["ema_fast"]) >= float(prev["ema_slow"]) and ef < es
        state = (f"close={close:.6g} EMA{p['ema_fast']}={ef:.6g} "
                 f"EMA{p['ema_slow']}={es:.6g} RSI={r:.1f} MACDhist={hist:.4g}")

        if position is None:
            if crossed_up:
                if not (p["rsi_buy_min"] <= r <= p["rsi_buy_max"]):
                    return self.hold(symbol, f"EMA crossed up but RSI {r:.1f} outside "
                                     f"[{p['rsi_buy_min']}, {p['rsi_buy_max']}] — no entry. {state}",
                                     price=close)
                if p["require_macd"] and hist <= 0:
                    return self.hold(symbol, f"EMA crossed up but MACD hist {hist:.4g} ≤ 0 "
                                     f"— no confirmation. {state}", price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"EMA{p['ema_fast']} crossed above EMA{p['ema_slow']}, "
                              f"RSI {r:.1f} in band, MACD hist {hist:.4g} > 0. {state}",
                              price=close)
            return self.hold(symbol, f"no crossover ({'up' if ef > es else 'down'}trend "
                             f"continues). {state}", price=close)

        # Managing an open position (exchange-side SL/TP also active).
        if crossed_down:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"EMA{p['ema_fast']} crossed below EMA{p['ema_slow']} — trend "
                          f"exit. {state}", price=close)
        if r >= p["rsi_exit"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"RSI {r:.1f} ≥ exit level {p['rsi_exit']} — momentum blow-off "
                          f"exit. {state}", price=close)
        if p["require_macd"] and hist < 0 and ef < es:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"MACD hist negative with fast EMA below slow — trend faded. "
                          f"{state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)
