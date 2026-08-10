"""Technical indicators implemented on pandas Series.

These are the only indicator implementations in the project — live trading and
backtesting both call them, so simulated behavior can't drift from real
behavior. Conventions follow the common charting-platform definitions
(Wilder RSI, EMA with adjust=False, population std for Bollinger).
"""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=1).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Flat markets (no gains, no losses) read as neutral 50."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    out = pd.Series(50.0, index=close.index)
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    only_gain = (avg_loss == 0) & ~both_zero
    normal = avg_loss > 0
    rs = avg_gain[normal] / avg_loss[normal]
    out[normal] = 100.0 - 100.0 / (1.0 + rs)
    out[only_gain] = 100.0
    out[avg_gain.isna() | avg_loss.isna()] = float("nan")
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=1).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0
              ) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    return mid, mid + num_std * std, mid - num_std * std
