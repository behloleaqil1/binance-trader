"""Research script (NOT production code): Parabolic SAR Stop-and-Reverse,
the 13th mechanically distinct strategy family tested.

Per DISTILLED LEARNINGS after Run 117: 12 strategy families are closed
(trend_momentum, mean_reversion, grid, Donchian breakout, Supertrend,
Capitulation Wick Reversal, BB-width squeeze breakout, Price-vs-RSI
divergence, Ichimoku Cloud, VWAP Band Reversion, Keltner Channel Breakout,
Stochastic RSI Crossover). Parabolic SAR is mechanically distinct from all
of them:
  - vs Supertrend: Supertrend's band is `EMA +/- ATR*multiplier` -- a FIXED
    multiplier on a rolling ATR, flat until the EMA itself moves. PSAR's
    stop (the "SAR" dot) accelerates every bar it stays on the same side:
    an acceleration factor (AF) starts at `af_start`, increments by
    `af_step` on every new extreme price, capped at `af_max`. The dot is
    pulled toward price at a growing rate -- there is no AF/acceleration
    concept anywhere else in the programme.
  - vs Donchian: Donchian's channel is the raw N-bar high/low, recomputed
    fresh every bar with no memory of how long the current trend has run.
    PSAR's dot has full path memory (it only ever moves toward price,
    never jumps backward, and resets its extreme-price tracking only on a
    flip) -- a genuinely stateful trailing construction, not a rolling
    window.
  - vs Keltner/VWAP-band/Bollinger/Ichimoku: none of those are
    stop-and-reverse constructions; they are static or EMA-anchored bands
    evaluated fresh each bar. PSAR has exactly one "position" at a time by
    construction (every bar is either long-biased or short-biased, flip on
    touch) -- closer in spirit to a pure trend-following trailing stop
    than to any band.
  - vs trend_momentum/mean_reversion/grid/Stochastic RSI/RSI-divergence:
    none of those touch high/low price extremes directly; PSAR is built
    entirely from rolling extreme points (EP) of high/low, not close-only
    or RSI-derived values.

Entry: BUY when the SAR flips from short-bias (dot above price) to
long-bias (dot below price) -- i.e. price crosses above the prior dot.
Exit: SELL when SAR flips back to short-bias (dot crosses above price).
Long-only (engine has no shorting for this registry strategy): short-bias
periods are simply "flat", we do not short on a bearish flip. Exchange-side
2%/4% SL/TP unchanged throughout.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS trades)
on a genuine held-out window, AND survives a 3rd-window check.
"""
import asyncio
import json
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import PositionView, Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-06-30", "2026-09-29"   # 150d-60d ago
TEST_START, TEST_END = "2026-09-29", "2026-11-28"     # 60d-0d ago (today's anchor)


def parabolic_sar(high: pd.Series, low: pd.Series, af_start: float,
                   af_step: float, af_max: float) -> tuple[pd.Series, pd.Series]:
    """Classic Wilder PSAR. Returns (sar, long_bias) where long_bias[i] is
    True iff the dot sits below price (bullish bias) at bar i. Computed
    causally left-to-right; sar[i]/long_bias[i] only ever depend on bars
    <= i (no lookahead)."""
    n = len(high)
    sar = np.full(n, np.nan)
    long_bias = np.zeros(n, dtype=bool)
    if n < 2:
        return pd.Series(sar, index=high.index), pd.Series(long_bias, index=high.index)

    h = high.values
    l = low.values

    is_long = True
    af = af_start
    ep = h[0]
    cur_sar = l[0]
    sar[0] = cur_sar
    long_bias[0] = is_long

    for i in range(1, n):
        prev_sar = cur_sar
        next_sar = prev_sar + af * (ep - prev_sar)
        if is_long:
            next_sar = min(next_sar, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < next_sar:
                is_long = False
                next_sar = ep
                ep = l[i]
                af = af_start
            else:
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + af_step, af_max)
        else:
            next_sar = max(next_sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > next_sar:
                is_long = True
                next_sar = ep
                ep = h[i]
                af = af_start
            else:
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + af_step, af_max)
        cur_sar = next_sar
        sar[i] = cur_sar
        long_bias[i] = is_long

    return pd.Series(sar, index=high.index), pd.Series(long_bias, index=high.index)


class ParabolicSarStrategy(Strategy):
    id = "parabolic_sar"
    name = "Parabolic SAR Stop-and-Reverse"
    description = ("Wilder's Parabolic SAR. BUY when the dot flips below "
                    "price (bullish bias), SELL when it flips back above "
                    "price (bearish bias), plus unchanged exchange-side "
                    "SL/TP. Long-only.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("af_start", "AF start", "float", 0.02, min=0.001, max=0.2),
            ParamSpec("af_step", "AF step", "float", 0.02, min=0.001, max=0.2),
            ParamSpec("af_max", "AF max", "float", 0.2, min=0.05, max=1.0),
        ]

    def required_history(self) -> int:
        return 30

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        sar, long_bias = parabolic_sar(out["high"], out["low"],
                                        p["af_start"], p["af_step"], p["af_max"])
        out["sar"] = sar
        out["sar_long_bias"] = long_bias
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        if i < 2:
            return self.hold(symbol, "not enough candles")
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close = float(row["close"])
        bias, prev_bias = row["sar_long_bias"], prev["sar_long_bias"]
        if pd.isna(row["sar"]) or pd.isna(prev["sar"]):
            return self.hold(symbol, "sar warming up", price=close)
        state = f"close={close:.6g} sar={row['sar']:.6g} long_bias={bias}"

        flip_to_long = bool(bias) and not bool(prev_bias)
        flip_to_short = (not bool(bias)) and bool(prev_bias)

        if position is None:
            if flip_to_long:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"sar flipped bullish. {state}", price=close)
            return self.hold(symbol, f"no flip. {state}", price=close)

        if flip_to_short:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"sar flipped bearish. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = ParabolicSarStrategy(params)
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
    for tf, buffer_days in (("15m", 10), ("1h", 30), ("4h", 90)):
        for af_start in (0.01, 0.02):
            for af_step in (0.01, 0.02):
                for af_max in (0.1, 0.2):
                    configs.append((tf, buffer_days, af_start, af_step, af_max))

    cache = {}
    for tf, buffer_days, af_start, af_step, af_max in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "af_start": af_start, "af_step": af_step, "af_max": af_max}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} psar(af_start={af_start},af_step={af_step},af_max={af_max})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/27c86ea0-f0c9-51ba-acf0-b103a79e882b/scratchpad/parabolic_sar_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
