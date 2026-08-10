"""Mean-reversion strategy: Bollinger Band + RSI oversold entries, revert-to-mean exits."""
from __future__ import annotations

import math

import pandas as pd

from app.core.types import PositionView, Signal, SignalAction
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.strategies.indicators import bollinger, ema, rsi


class MeanReversionStrategy(Strategy):
    id = "mean_reversion"
    name = "Mean Reversion"
    description = ("Buys when price closes below the lower Bollinger Band with RSI "
                   "oversold; exits when price reverts to the middle (or upper) band "
                   "or RSI turns overbought. Long-only — overbought conditions "
                   "without a position are just logged, spot cannot short.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "15m", choices=TIMEFRAMES),
            ParamSpec("bb_period", "Bollinger period", "int", 20, min=5, max=100),
            ParamSpec("bb_std", "Bollinger std devs", "float", 2.0, min=0.5, max=4.0, step=0.1),
            ParamSpec("rsi_period", "RSI period", "int", 14, min=2, max=50),
            ParamSpec("rsi_oversold", "RSI oversold", "float", 30, min=1, max=50),
            ParamSpec("rsi_overbought", "RSI overbought", "float", 70, min=50, max=99),
            ParamSpec("exit_at", "Exit target", "select", "middle", choices=["middle", "upper"],
                      help="Sell when price reverts to the middle band or stretches to the upper"),
            ParamSpec("trend_ema", "Trend filter EMA", "int", 0, min=0, max=400,
                      help="0 = off. If set, only buy dips when price is ABOVE this EMA "
                           "(skip falling-knife dips in downtrends)."),
        ]

    def required_history(self) -> int:
        return max(self.params["bb_period"], self.params["rsi_period"],
                   self.params.get("trend_ema", 0)) + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        out["bb_mid"], out["bb_upper"], out["bb_lower"] = bollinger(
            df["close"], p["bb_period"], p["bb_std"])
        out["rsi"] = rsi(df["close"], p["rsi_period"])
        if p.get("trend_ema", 0):
            out["trend_ema"] = ema(df["close"], p["trend_ema"])
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        close, mid, upper, lower, r = (float(row["close"]), float(row["bb_mid"]),
                                       float(row["bb_upper"]), float(row["bb_lower"]),
                                       float(row["rsi"]))
        if any(math.isnan(v) for v in (mid, upper, lower, r)):
            return self.hold(symbol, "indicators warming up")
        state = (f"close={close:.6g} BB[{lower:.6g} / {mid:.6g} / {upper:.6g}] "
                 f"RSI={r:.1f}")

        if position is None:
            if close < lower and r < p["rsi_oversold"]:
                # Trend filter: skip dips while price is below the trend EMA — those
                # are downtrends where "oversold" keeps getting more oversold.
                if p.get("trend_ema", 0):
                    tema = float(row["trend_ema"]) if "trend_ema" in row else float("nan")
                    if math.isnan(tema) or close < tema:
                        return self.hold(symbol, f"oversold dip skipped — price {close:.6g} "
                                         f"below trend EMA {tema:.6g} (downtrend). {state}",
                                         price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"close below lower band with RSI {r:.1f} < "
                              f"{p['rsi_oversold']} — oversold reversion entry. {state}",
                              price=close)
            if close < lower:
                return self.hold(symbol, f"below lower band but RSI {r:.1f} not oversold "
                                 f"(<{p['rsi_oversold']} required). {state}", price=close)
            if close > upper and r > p["rsi_overbought"]:
                return self.hold(symbol, "overbought — a short entry would trigger here, "
                                 f"but spot trading is long-only. {state}", price=close)
            return self.hold(symbol, f"inside bands, no setup. {state}", price=close)

        exit_level = mid if p["exit_at"] == "middle" else upper
        if close >= exit_level:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"price reverted to {p['exit_at']} band "
                          f"({exit_level:.6g}) — take reversion profit. {state}", price=close)
        if r > p["rsi_overbought"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"RSI {r:.1f} > {p['rsi_overbought']} — overbought exit. {state}",
                          price=close)
        return self.hold(symbol, f"holding, waiting for reversion to {exit_level:.6g}. "
                         f"{state}", price=close)
