"""Backtest performance metrics.

All figures describe SIMULATED historical performance and imply nothing about
future results — the dashboard labels them accordingly.
"""
from __future__ import annotations

import math

import pandas as pd


def compute_metrics(equity: pd.Series, trades: list[dict], initial_equity: float,
                    df: pd.DataFrame, warmup: int) -> dict:
    """equity: value per candle, indexed by open_time (ms)."""
    final_equity = float(equity.iloc[-1]) if len(equity) else initial_equity
    total_return_pct = (final_equity / initial_equity - 1) * 100

    running_max = equity.cummax()
    dd = (running_max - equity) / running_max * 100
    max_drawdown_pct = float(dd.max()) if len(dd) else 0.0

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0
    if gross_loss > 1e-12:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = math.inf if gross_win > 0 else 0.0

    # Sharpe from daily equity returns, annualized √365 (crypto trades 24/7).
    sharpe = 0.0
    if len(equity) > 2:
        daily = (equity.set_axis(pd.to_datetime(equity.index, unit="ms", utc=True))
                 .resample("1D").last().dropna())
        rets = daily.pct_change().dropna()
        if len(rets) >= 2 and float(rets.std()) > 1e-12:
            sharpe = float(rets.mean() / rets.std() * math.sqrt(365))

    # Honest baseline: buying at the first tradable candle and holding.
    start_close = float(df["close"].iloc[min(warmup, len(df) - 1)])
    buy_hold_pct = (float(df["close"].iloc[-1]) / start_close - 1) * 100

    return {
        "initial_equity": round(initial_equity, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 3),
        "buy_hold_return_pct": round(buy_hold_pct, 3),
        "max_drawdown_pct": round(max_drawdown_pct, 3),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": (round(profit_factor, 3)
                          if math.isfinite(profit_factor) else None),
        "sharpe_ratio": round(sharpe, 3),
        "n_trades": len(trades),
        "avg_trade_pnl": round(sum(t["pnl"] for t in trades) / len(trades), 4)
                         if trades else 0.0,
        "fees_paid": round(sum(t.get("fees", 0.0) for t in trades), 4),
        "disclaimer": "Simulated historical performance; not indicative of future results.",
    }


def downsample_curve(equity: pd.Series, max_points: int = 1500) -> list[list[float]]:
    if len(equity) == 0:
        return []
    if len(equity) <= max_points:
        items = equity.items()
    else:
        step = len(equity) / max_points
        idx = [int(i * step) for i in range(max_points)] + [len(equity) - 1]
        items = ((int(equity.index[i]), float(equity.iloc[i])) for i in sorted(set(idx)))
    return [[int(ts), round(float(v), 4)] for ts, v in items]
