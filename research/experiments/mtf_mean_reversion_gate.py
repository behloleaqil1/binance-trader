"""Research script (NOT production code): multi-timeframe mean_reversion.

Hypothesis (Run 17, per Run 16's flagged next step (b)): the MTF
trend-direction gate mechanism proved mechanically sound but not decisively
edge-positive when applied to trend_momentum (Run 16 — 20/50 HTF pair was
the closest near-miss yet, but still closed as noise on per-symbol
inspection). This run applies the *same mechanism* to a different
hypothesis: mean_reversion's BB+RSI oversold dip-buy, gated to only fire
when a higher timeframe's trend is still intact and UP — i.e. "buy the dip
in an uptrend", explicitly skipping oversold dips that occur during a
genuine 4h downtrend (falling-knife protection from a coarser, smoother
timeframe than the already-closed same-TF trend_ema filter).

This is mechanically distinct from the existing trend_ema filter
(mean_reversion.py's own opt-in same-TF EMA, closed as "principled but
unproven, still tiny-sample" per distilled learnings): trend_ema compares
close price to a same-candle EMA computed on the *entry* timeframe itself,
whereas this gate asks whether a *coarser* timeframe (4h) is itself trending
up, using information a same-TF filter structurally cannot see (smoother,
less noise-sensitive, matches Run 16's trend_momentum MTF gate exactly).

Applied to mean_reversion @ 1h (the closest-to-edge mean_reversion baseline
per distilled learnings — 1h shipped-default params previously flagged an
OOS PF 1.9/PF 0.44 two-window inconsistency, i.e. "regime luck" — a
downtrend-avoidance gate is a plausible fix for exactly that kind of
inconsistency) with 4h as HTF, matching Run 16's TF/HTF ratio exactly for
direct methodology comparability.

Implemented as a thin subclass of production MeanReversionStrategy —
decide() defers entirely to the parent's unmodified decide() and adds
exactly one veto on BUY: block unless the 4h EMA(fast_4h) > EMA(slow_4h) on
the most recently *closed* 4h candle strictly before the 1h signal candle's
open_time (same as-of backward join as mtf_trend_momentum_gate.py, no
lookahead). No production code touched; run_candle_backtest (production,
unmodified) runs on the 1h data exactly as-is.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import SignalAction
from app.risk.models import RiskConfig
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.indicators import ema
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
HTF = "4h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-21", "2026-06-19"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-19", "2026-08-18"     # 60d-0d ago (today's anchor)
BUFFER_DAYS = 35  # extra history before window start for EMA warmup (4h ema_slow up to 100 needs ~16.7d min; padded for convergence)


class MeanReversionMTFGated(MeanReversionStrategy):
    """Adds one veto on top of the unmodified parent decide(): BUY signals are
    blocked unless the 4h trend (EMA(htf_fast) > EMA(htf_slow) on the most
    recently closed 4h candle) is already up — buy the dip only in an intact
    higher-TF uptrend, skip dips during a genuine higher-TF downtrend.
    mtf_gate: bool, None/False = off, behaves identically to the parent."""

    mtf_gate: bool = False

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.mtf_gate and sig.action == SignalAction.BUY:
            up = df.iloc[i]["htf_trend_up"]
            if pd.isna(up) or not bool(up):
                return self.hold(symbol, f"BUY vetoed: 4h trend not up "
                                  f"(htf_trend_up={up}) — oversold dip not "
                                  f"confirmed by higher-timeframe direction "
                                  f"(possible falling knife)", price=sig.price)
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
    strategy = MeanReversionMTFGated(params)
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

    base_params = {"timeframe": TF, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14,
                   "rsi_oversold": 30, "rsi_overbought": 70, "exit_at": "middle",
                   "trend_ema": 0, "htf_ema_fast": 20, "htf_ema_slow": 50}

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
    # robustness of any promising result to the exact HTF EMA choice — same
    # 3 pairs Run 16 swept for trend_momentum, for direct comparability.
    print("\nSweeping HTF EMA pairs with mtf_gate=True...")
    htf_pairs = [(10, 30), (20, 50), (50, 100)]
    sweep_rows = {}
    for hf, hs in htf_pairs:
        params = {**base_params, "mtf_gate": True, "htf_ema_fast": hf, "htf_ema_slow": hs}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        row = {"params": params, "label": f"4h EMA{hf}/{hs} gate", "train": train_m, "test": test_m}
        results.append(row)
        sweep_rows[(hf, hs)] = (train_m, test_m)
        print(f"4h EMA{hf}/{hs} gate | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # Pick the standout (highest test PF that clears both anti-noise bars, if
    # any) for a 3rd non-overlapping window + per-symbol cross-check, same
    # protocol as Run 16's MTF trend_momentum gate.
    def clears(m):
        return m["pf"] is not None and m["pf"] > 1.1 and m["trades"] >= 30

    standout = None
    for hf, hs in htf_pairs:
        train_m, test_m = sweep_rows[(hf, hs)]
        if clears(test_m):
            if standout is None or test_m["pf"] > sweep_rows[standout][1]["pf"]:
                standout = (hf, hs)
    if standout is None:
        # No config outright clears both bars; still cross-check whichever
        # test PF is highest, in case it's a near-miss worth inspecting.
        standout = max(sweep_rows, key=lambda k: (sweep_rows[k][1]["pf"] or 0))

    hf, hs = standout
    OLDER_START, OLDER_END = "2025-12-21", "2026-03-21"  # 240d-150d ago
    print(f"\nFetching a THIRD, non-overlapping window for the standout "
          f"config (4h EMA{hf}/{hs} gate) cross-check...")
    older_dfs = await fetch_all(OLDER_START, OLDER_END)
    standout_params = {**base_params, "mtf_gate": True, "htf_ema_fast": hf, "htf_ema_slow": hs}
    older_m = eval_window(older_dfs, OLDER_START, OLDER_END, standout_params, risk,
                           per_symbol=True)
    train_ps = eval_window(train_dfs, TRAIN_START, TRAIN_END, standout_params, risk,
                            per_symbol=True)
    test_ps = eval_window(test_dfs, TEST_START, TEST_END, standout_params, risk,
                           per_symbol=True)
    print(f"4h EMA{hf}/{hs} gate OLDER window ({OLDER_START}..{OLDER_END}): "
          f"pf={older_m['pf']} win%={older_m['win_pct']} n={older_m['trades']} "
          f"ret%={older_m['avg_ret_pct']}")
    print("Per-symbol (TRAIN):", train_ps["per_symbol"])
    print("Per-symbol (TEST):", test_ps["per_symbol"])
    print("Per-symbol (OLDER):", older_m["per_symbol"])

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/aa41f9e0-bce2-5c5c-8936-80b4f570fe16/scratchpad/mtf_mean_reversion_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "standout_htf_pair": list(standout),
                   "standout_older_window": older_m,
                   "standout_train_per_symbol": train_ps,
                   "standout_test_per_symbol": test_ps}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
