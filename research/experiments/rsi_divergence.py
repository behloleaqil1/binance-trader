"""Research script (NOT production code): Price-vs-RSI Bullish Divergence,
the 8th strategy family and the first OSCILLATOR-DIVERGENCE construction
tested in this programme.

Per DISTILLED LEARNINGS after Run 33 (`research/RESEARCH_LOG.md`), every
signal tried so far reads one series in isolation: a moving-average
relationship (EMA cross, Supertrend band, MTF direction), a band/threshold
touch (Bollinger, RSI level, ADX level), a fixed/adaptive price channel
(Donchian, BB-squeeze), a single candle's own OHLC shape (wick reversal),
calendar time, or cross-symbol rank/spread. None of them compare the SHAPE
of two different series against each other over time. Classical technical
divergence does exactly that: price makes a lower low while RSI makes a
higher low at the matching swing -- downside momentum is fading even though
price is still falling, a textbook exhaustion signal. This is mechanically
distinct from every prior construction: it needs two confirmed swing points
and a cross-series comparison, not a single-bar/single-series condition.

Entry (long-only, spot), no lookahead:
  1. A candle at index j is a confirmed swing low once `pivot_lookback` bars
     have closed on BOTH sides of it and its low is the minimum of that
     window -- confirmation only happens at index j+pivot_lookback (we never
     know a swing low is a swing low until the right-side bars exist), so
     nothing here reads data ahead of the current row.
  2. At each confirmation, compare this pivot to the immediately preceding
     confirmed pivot (if within `max_divergence_bars` of each other):
     bullish divergence = lower price low (pivot2 < pivot1) AND higher RSI
     low (rsi_at_pivot2 > rsi_at_pivot1) AND rsi_at_pivot2 < oversold_max
     (keeps the divergence anchored in oversold territory, not mid-range
     noise).
  3. BUY on the confirmation candle where divergence fires.
Exit: RSI recovers back above `exit_rsi` (momentum exhaustion thesis
resolved), on top of the unchanged exchange-side 2%/4% SL/TP (never
loosened, never touched by this script).

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS trades)
on a genuine held-out window, AND survives the 3rd-window + per-symbol check.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import PositionView, Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.strategies.indicators import rsi
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

# today's anchor = 2026-08-29 (one day of new data since Run 33's 2026-08-28 anchor)
TRAIN_START, TRAIN_END = "2026-04-01", "2026-06-30"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-30", "2026-08-29"     # 60d-0d ago
OLDER_START, OLDER_END = "2026-01-01", "2026-04-01"   # 240d-150d ago, 3rd-window check


def find_divergence_signal(low: pd.Series, rsi_s: pd.Series, pivot_lookback: int,
                            max_divergence_bars: int, oversold_max: float) -> pd.Series:
    """Vectorized-ish (single pass) confirmed-swing-low divergence detector.
    Returns a boolean Series, True only at the bar where a bullish divergence
    is CONFIRMED (i.e. j + pivot_lookback for the second pivot j)."""
    n = len(low)
    low_v = low.to_numpy()
    signal = np.zeros(n, dtype=bool)

    is_pivot = np.zeros(n, dtype=bool)
    for j in range(pivot_lookback, n - pivot_lookback):
        window = low_v[j - pivot_lookback: j + pivot_lookback + 1]
        if low_v[j] == window.min() and np.argmin(window) == pivot_lookback:
            is_pivot[j] = True

    prev_pivot = None  # (index j, price low, rsi at j)
    for j in range(pivot_lookback, n - pivot_lookback):
        if not is_pivot[j]:
            continue
        confirm_idx = j + pivot_lookback
        rsi_j = rsi_s.iloc[j]
        if pd.isna(rsi_j):
            prev_pivot = (j, low_v[j], None)
            continue
        if prev_pivot is not None and prev_pivot[2] is not None:
            pj, p_low, p_rsi = prev_pivot
            if (j - pj) <= max_divergence_bars and low_v[j] < p_low and rsi_j > p_rsi \
                    and rsi_j < oversold_max:
                signal[confirm_idx] = True
        prev_pivot = (j, low_v[j], float(rsi_j))

    return pd.Series(signal, index=low.index)


class RsiDivergenceStrategy(Strategy):
    id = "rsi_divergence"
    name = "Price-vs-RSI Bullish Divergence"
    description = ("Buys when price makes a lower swing low while RSI makes a higher "
                    "swing low at the matching pivot (momentum exhaustion), confirmed "
                    "only once both sides of the swing have closed (no lookahead). "
                    "Exits when RSI recovers above exit_rsi, plus unchanged exchange-"
                    "side SL/TP. Long-only (spot).")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("rsi_period", "RSI period", "int", 14, min=5, max=50),
            ParamSpec("pivot_lookback", "Swing confirmation bars (each side)", "int", 3,
                      min=2, max=15),
            ParamSpec("max_divergence_bars", "Max bars between compared pivots", "int", 30,
                      min=5, max=200),
            ParamSpec("oversold_max", "Max RSI at 2nd pivot to count as divergence", "float",
                      50.0, min=20.0, max=70.0),
            ParamSpec("exit_rsi", "RSI recovery level to exit", "float", 55.0, min=40.0, max=80.0),
        ]

    def required_history(self) -> int:
        p = self.params
        return p["rsi_period"] + p["max_divergence_bars"] + 2 * p["pivot_lookback"] + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        out["rsi"] = rsi(df["close"], p["rsi_period"])
        out["bull_divergence"] = find_divergence_signal(
            df["low"], out["rsi"], p["pivot_lookback"], p["max_divergence_bars"],
            p["oversold_max"])
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        close, rsi_now = float(row["close"]), row["rsi"]
        if pd.isna(rsi_now):
            return self.hold(symbol, "indicators warming up")

        if position is None:
            if bool(row["bull_divergence"]):
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"bullish RSI divergence confirmed: price lower low, "
                              f"RSI higher low (rsi={float(rsi_now):.1f})", price=close)
            return self.hold(symbol, f"no divergence setup. rsi={float(rsi_now):.1f}",
                             price=close)

        if float(rsi_now) >= p["exit_rsi"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"rsi={float(rsi_now):.1f} recovered above exit_rsi="
                          f"{p['exit_rsi']} — exhaustion thesis resolved.", price=close)
        return self.hold(symbol, f"holding, rsi={float(rsi_now):.1f} below exit_rsi="
                         f"{p['exit_rsi']}.", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = RsiDivergenceStrategy(params)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        result = run_candle_backtest(strategy, risk, df, cfg, symbol=sym)
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

    results = []
    configs = []
    for tf, buffer_days in [("1h", 15), ("4h", 40)]:
        for pivot_lookback in (3, 5):
            for exit_rsi in (55.0, 60.0):
                configs.append((tf, buffer_days, pivot_lookback, exit_rsi))

    cache = {}
    for tf, buffer_days, pivot_lookback, exit_rsi in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "rsi_period": 14, "pivot_lookback": pivot_lookback,
                  "max_divergence_bars": 30, "oversold_max": 50.0, "exit_rsi": exit_rsi}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} rsi_divergence(pivot_lookback={pivot_lookback},exit_rsi={exit_rsi})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    survivors = [r for r in results
                 if r["train"]["pf"] is not None and r["train"]["pf"] > 1.1
                 and r["test"]["pf"] is not None and r["test"]["pf"] > 1.1
                 and r["test"]["trades"] >= 30]
    print(f"\n{len(survivors)} config(s) clear both sides of the OOS bar.")
    older_checks = []
    if survivors:
        older_cache = {}
        for r in survivors:
            tf = r["params"]["timeframe"]
            buffer_days = 15 if tf == "1h" else 40
            if tf not in older_cache:
                print(f"Fetching OLDER window for {tf}...")
                older_cache[tf] = await fetch_all(OLDER_START, OLDER_END, tf, buffer_days)
            older_dfs = older_cache[tf]
            older_m = eval_window(older_dfs, OLDER_START, OLDER_END, r["params"], risk,
                                   per_symbol=True)
            train_ps = eval_window(cache[tf][0], TRAIN_START, TRAIN_END, r["params"], risk,
                                    per_symbol=True)
            test_ps = eval_window(cache[tf][1], TEST_START, TEST_END, r["params"], risk,
                                   per_symbol=True)
            print(f"{r['label']} OLDER window: pf={older_m['pf']} win%={older_m['win_pct']} "
                  f"n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            older_checks.append({"label": r["label"], "older": older_m,
                                  "train_per_symbol": train_ps["per_symbol"],
                                  "test_per_symbol": test_ps["per_symbol"],
                                  "older_per_symbol": older_m["per_symbol"]})

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/6eac1819-78ee-5609-b30c-70624a20a73f/scratchpad/rsi_divergence_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "older_checks": older_checks}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
