"""Research script (NOT production code): multi-timeframe trend_momentum.

Hypothesis (Run 16, per Run 15's flagged next step (a)): the fast-TF (1h)
EMA-cross signal has no edge on its own (Runs 1/3/7/11/15 all closed it),
and two same-candle confirmation indicators (ADX trend-*strength*, Run 11;
relative volume/*participation*, Run 15) both failed with the identical
train-improves/test-doesn't shape. A slower-TF trend *direction* filter is
mechanically distinct from both: it doesn't touch the same candles at all,
it asks whether a coarser timeframe (4h) is itself trending in the entry's
direction at the time of the 1h cross, using information a same-TF gate
structurally cannot see.

Implemented as a thin subclass of production TrendMomentumStrategy — decide()
defers entirely to the parent's unmodified decide() and adds exactly one veto
on BUY: block unless the 4h EMA(fast_4h) > EMA(slow_4h) on the most recently
*closed* 4h candle strictly before the 1h signal candle (no lookahead — the
4h candle must have fully closed before the 1h bar's open_time). No production
code touched; run_candle_backtest (production, unmodified) runs on the 1h
data exactly as-is; the 4h series is precomputed once per symbol/window and
merged in via an "as-of" (backward) join.
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
from app.strategies.indicators import ema
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
HTF = "4h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-18", "2026-08-18"     # 60d-0d ago (today's anchor)
BUFFER_DAYS = 35  # extra history before window start for EMA warmup (4h ema_slow up to 100 needs ~16.7d min; padded for convergence)


class TrendMomentumMTFGated(TrendMomentumStrategy):
    """Adds one veto on top of the unmodified parent decide(): BUY signals are
    blocked unless the 4h trend (EMA(htf_fast) > EMA(htf_slow) on the most
    recently closed 4h candle) is already up. htf_trend_up column is merged
    onto the 1h df before compute_indicators is called (see build_htf_merged).
    mtf_gate: bool, None/False = off, behaves identically to the parent."""

    mtf_gate: bool = False

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.mtf_gate and sig.action == SignalAction.BUY:
            up = df.iloc[i]["htf_trend_up"]
            if pd.isna(up) or not bool(up):
                return self.hold(symbol, f"BUY vetoed: 4h trend not up "
                                  f"(htf_trend_up={up}) — 1h cross not confirmed "
                                  f"by higher-timeframe direction", price=sig.price)
        return sig


def build_htf_merged(ltf_df: pd.DataFrame, htf_df: pd.DataFrame,
                      htf_fast: int, htf_slow: int) -> pd.DataFrame:
    """Backward as-of join: for each 1h candle, attach the 4h trend state of
    the most recently *closed* 4h candle strictly before that 1h candle's
    open_time (close_time of a 4h candle = open_time + 4h; using open_time+4h
    <= ltf open_time enforces no lookahead)."""
    h = htf_df.copy().sort_values("open_time").reset_index(drop=True)
    h["ema_fast_htf"] = ema(h["close"], htf_fast)
    h["ema_slow_htf"] = ema(h["close"], htf_slow)
    h["trend_up_htf"] = h["ema_fast_htf"] > h["ema_slow_htf"]
    h["htf_close_time"] = h["open_time"] + 4 * 3_600_000  # 4h in ms
    l = ltf_df.copy().sort_values("open_time").reset_index(drop=True)
    merged = pd.merge_asof(l, h[["htf_close_time", "trend_up_htf"]],
                            left_on="open_time", right_on="htf_close_time",
                            direction="backward", allow_exact_matches=True)
    merged["htf_trend_up"] = merged["trend_up_htf"]
    return merged.drop(columns=["htf_close_time", "trend_up_htf"])


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        ltf = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        htf = await fetch_klines(f"{sym}USDT", HTF, buf_start, end)
        out[sym] = (ltf, htf)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = TrendMomentumMTFGated(params)
    strategy.mtf_gate = params.get("mtf_gate", False)
    htf_fast = params.get("htf_ema_fast", 20)
    htf_slow = params.get("htf_ema_slow", 50)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, (ltf_df, htf_df) in dfs.items():
        merged = build_htf_merged(ltf_df, htf_df, htf_fast, htf_slow)
        result = run_candle_backtest(strategy, risk, merged, cfg, symbol=sym)
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
    print("Fetching train window data (1h + 4h, with warmup buffer)...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print("Fetching test window data...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    base_params = {"timeframe": TF, "ema_fast": 20, "ema_slow": 50, "rsi_period": 14,
                   "rsi_buy_min": 50, "rsi_buy_max": 70, "rsi_exit": 78,
                   "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                   "require_macd": True, "htf_ema_fast": 20, "htf_ema_slow": 50}

    configs = [
        {"mtf_gate": False, "label": "baseline (no gate)"},
        {"mtf_gate": True, "label": "4h EMA20/50 trend gate"},
    ]

    results = []
    for c in configs:
        params = {**base_params, "mtf_gate": c["mtf_gate"]}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        row = {"params": params, "label": c["label"], "train": train_m, "test": test_m}
        results.append(row)
        print(f"{c['label']} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # Also sweep htf_ema pairs (a slower/faster 4h trend definition) to check
    # robustness of any promising result to the exact HTF EMA choice.
    print("\nSweeping HTF EMA pairs with mtf_gate=True...")
    htf_pairs = [(10, 30), (20, 50), (50, 100)]
    for hf, hs in htf_pairs:
        params = {**base_params, "mtf_gate": True, "htf_ema_fast": hf, "htf_ema_slow": hs}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        row = {"params": params, "label": f"4h EMA{hf}/{hs} gate", "train": train_m, "test": test_m}
        results.append(row)
        print(f"4h EMA{hf}/{hs} gate | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # ── Third, non-overlapping window + per-symbol breakdown for the
    # standout config (4h EMA20/50 gate: train PF 0.917/39 trades, test PF
    # 1.256/29 trades — clears the OOS PF bar but test trades is 1 below the
    # 30-trade floor; a near-miss worth a 3rd-window cross-check per the
    # Run 11 precedent). ──
    OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"  # 240d-150d ago
    print("\nFetching a THIRD, non-overlapping window for 4h EMA20/50 gate "
          "cross-check...")
    older_dfs = await fetch_all(OLDER_START, OLDER_END)
    standout_params = {**base_params, "mtf_gate": True, "htf_ema_fast": 20, "htf_ema_slow": 50}
    older_m = eval_window(older_dfs, OLDER_START, OLDER_END, standout_params, risk,
                           per_symbol=True)
    train_ps = eval_window(train_dfs, TRAIN_START, TRAIN_END, standout_params, risk,
                            per_symbol=True)
    test_ps = eval_window(test_dfs, TEST_START, TEST_END, standout_params, risk,
                           per_symbol=True)
    print(f"4h EMA20/50 gate OLDER window ({OLDER_START}..{OLDER_END}): "
          f"pf={older_m['pf']} win%={older_m['win_pct']} n={older_m['trades']} "
          f"ret%={older_m['avg_ret_pct']}")
    print("Per-symbol (TRAIN):", train_ps["per_symbol"])
    print("Per-symbol (TEST):", test_ps["per_symbol"])
    print("Per-symbol (OLDER):", older_m["per_symbol"])

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/37f63e82-b632-5933-9f5f-f696e0077e11/scratchpad/mtf_trend_momentum_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "ema20_50_older_window": older_m,
                   "ema20_50_train_per_symbol": train_ps,
                   "ema20_50_test_per_symbol": test_ps}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
