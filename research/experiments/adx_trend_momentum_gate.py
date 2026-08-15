"""Research script (NOT production code): ADX-confirmed trend_momentum.

Hypothesis: trend_momentum's known failure mode across every TF tested
(15m/1h/4h, Runs 1/3/7) is whipsaw EMA-cross entries during weak/choppy
conditions (low win rate ~10-29%, MACD confirmation already helps some but
doesn't fix it). An ADX(14) trend-strength FLOOR — only take the entry when
ADX(14) is already above a threshold, i.e. a real trend is underway, not just
a raw EMA cross — might filter out the weak-trend whipsaws that MACD alone
lets through. This is the "sibling" idea to Run 10's grid+ADX gate (which
failed cleanly); unlike grid, an ADX floor here augments an existing
directional-confirmation role (MACD) rather than fighting the strategy's core
mechanism, so it may behave differently.

Implemented as a thin subclass of the production TrendMomentumStrategy —
compute_indicators adds one ADX column, decide() defers entirely to the
parent's decide() and only adds one extra veto on BUY signals. No production
code is touched; run_candle_backtest (production, unmodified) is used as-is.
"""
import asyncio
import math
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import SignalAction
from app.risk.models import RiskConfig
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-18", "2026-06-16"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-16", "2026-08-15"     # 60d-0d ago (today's anchor)
BUFFER_DAYS = 15  # extra history before window start for EMA/ADX warmup


def wilder_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(),
                     (high - prev_close).abs(),
                     (low - prev_close).abs()], axis=1).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move[(up_move > down_move) & (up_move > 0)]
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move[(down_move > up_move) & (down_move > 0)]

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx


class TrendMomentumADXGated(TrendMomentumStrategy):
    """Adds one veto on top of the unmodified parent decide(): BUY signals are
    blocked unless ADX(14) is already at/above adx_min_for_entry (None = off,
    behaves identically to the parent). adx_min_for_entry/adx_period are NOT
    routed through param_specs()/validate_params() (which silently drops
    unknown keys) — set directly as instance attributes after construction."""

    adx_period: int = 14
    adx_min_for_entry: float | None = None

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = super().compute_indicators(df)
        out["adx"] = wilder_adx(df, self.adx_period)
        return out

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.adx_min_for_entry is not None and sig.action == SignalAction.BUY:
            a = float(df.iloc[i]["adx"])
            if math.isnan(a) or a < self.adx_min_for_entry:
                return self.hold(symbol, f"BUY vetoed: ADX {a:.1f} < floor "
                                  f"{self.adx_min_for_entry} (weak trend, cross not "
                                  f"confirmed)", price=sig.price)
        return sig


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        out[sym] = df
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = TrendMomentumADXGated(params)
    strategy.adx_period = params.get("adx_period", 14)
    strategy.adx_min_for_entry = params.get("adx_min_for_entry")
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, full_df in dfs.items():
        result = run_candle_backtest(strategy, risk, full_df, cfg, symbol=sym)
        window_trades = [t for t in result.trades if start_ms <= t["opened_at"] < end_ms]
        all_trades.extend(window_trades)
        eq = result.equity
        in_win = [(ts, v) for ts, v in zip(eq.index, eq.values) if start_ms <= ts < end_ms]
        ret = (in_win[-1][1] / in_win[0][1] - 1) * 100 if len(in_win) >= 2 else 0.0
        rets.append(ret)
        sw = [t for t in window_trades if t["pnl"] > 0]
        sl = [t for t in window_trades if t["pnl"] <= 0]
        gw = sum(t["pnl"] for t in sw)
        gl = -sum(t["pnl"] for t in sl)
        spf = gw / gl if gl > 1e-9 else (float("inf") if gw > 0 else None)
        sym_stats[sym] = {"pf": round(spf, 3) if spf not in (None, float("inf")) else spf,
                           "trades": len(window_trades), "ret_pct": round(ret, 4)}

    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (float("inf") if gross_win > 0 else 0.0)
    win_pct = len(wins) / len(all_trades) * 100 if all_trades else 0.0
    avg_ret = sum(rets) / len(rets) if rets else 0.0
    out = {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
           "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4)}
    if per_symbol:
        out["per_symbol"] = sym_stats
    return out


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()
    print("Fetching train window data (with warmup buffer)...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print("Fetching test window data...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    base_params = {"timeframe": TF, "ema_fast": 20, "ema_slow": 50, "rsi_period": 14,
                   "rsi_buy_min": 50, "rsi_buy_max": 70, "rsi_exit": 78,
                   "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                   "require_macd": True, "adx_period": 14}
    thresholds = [None, 15, 20, 25, 30]

    results = []
    for thr in thresholds:
        params = {**base_params, "adx_min_for_entry": thr}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        row = {"params": params, "adx_min_for_entry": thr, "train": train_m, "test": test_m}
        results.append(row)
        print(f"adx_floor={thr} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # ── Third, non-overlapping window + per-symbol breakdown for the
    # standout config (adx_floor=20: train PF 1.124/73 trades, test PF
    # 1.176/35 trades — clears both anti-noise bars in both windows). ──
    OLDER_START, OLDER_END = "2025-12-15", "2026-03-15"  # 240d-150d ago
    print("\nFetching a THIRD, non-overlapping window for adx_floor=20 "
          "cross-check...")
    older_dfs = await fetch_all(OLDER_START, OLDER_END)
    standout_params = {**base_params, "adx_min_for_entry": 20}
    older_m = eval_window(older_dfs, OLDER_START, OLDER_END, standout_params, risk,
                           per_symbol=True)
    train_ps = eval_window(train_dfs, TRAIN_START, TRAIN_END, standout_params, risk,
                            per_symbol=True)
    test_ps = eval_window(test_dfs, TEST_START, TEST_END, standout_params, risk,
                           per_symbol=True)
    print(f"adx_floor=20 OLDER window (2025-12-15..2026-03-15): pf={older_m['pf']} "
          f"win%={older_m['win_pct']} n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
    print("Per-symbol (TRAIN):", train_ps["per_symbol"])
    print("Per-symbol (TEST):", test_ps["per_symbol"])
    print("Per-symbol (OLDER):", older_m["per_symbol"])

    import json
    with open("/tmp/claude-0/-home-user-binance-trader/0dc5556a-b974-59e4-9703-bb6c8f3497db/scratchpad/adx_trend_momentum_results.json", "w") as f:
        json.dump({"threshold_sweep": results, "adx20_older_window": older_m,
                   "adx20_train_per_symbol": train_ps, "adx20_test_per_symbol": test_ps},
                  f, indent=2)
    print("\nSaved results.")


if __name__ == "__main__":
    asyncio.run(main())
