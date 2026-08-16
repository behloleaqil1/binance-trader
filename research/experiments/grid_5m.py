"""Research script (NOT production code): grid @ 5m.

Last untested TF for grid -- the family is already closed with train/test
rigor at 1h (Run 2, 8 combos, best train PF 1.51 -> OOS PF 0.66) and 4h
(Run 8, 8 combos + shipped-default reference, train PF 0.31-0.69 all <1).
Both prior ADX-gate attempts on top of this family (Run 10, ceiling gate)
and on trend_momentum (Run 11, floor gate) closed as noise/no-improvement,
so this run does NOT re-attempt ADX gating -- pure baseline grid sweep at
the one remaining sweepable TF, using unmodified production
`run_grid_backtest`.

Rationale for trying 5m despite the family's poor record: grid's range
math operates on price levels, not candle count, so tighter TF changes the
*sampling* of price action within a fixed % range (finer high/low capture
-> more precise fills) without necessarily changing overall price
excursion over the window. This is a different mechanism than
trend_momentum/mean_reversion's TF sensitivity (where finer TF mainly
means more signal-noise and more daily-loss-halt triggers), so grid's 5m
result is not assumed to follow the "faster TF = worse" pattern seen for
the other two families -- worth an honest look rather than skipping on
priors.

Config shape mirrors Run 2/8 exactly (range ∈ {6%, 10%}, levels=13,
flatten_on_stop=True, quote_per_level=150) for direct cross-TF
comparability. flatten_on_stop=True only -- Run 8 already documented that
flatten_on_stop=False's trade-level PF is a meaningless accounting
artifact (100% win rate by construction), so that arm is not repeated.
"""
import asyncio
import json
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_grid_backtest
from app.backtest.metrics import compute_metrics
from app.strategies.grid import GridStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "5m"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

# Same anchor convention as every prior run: train = 150d-60d ago, test = 60d-0d ago.
TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-17"
TEST_START, TEST_END = "2026-06-17", "2026-08-16"

CONFIGS = [
    {"auto_range_pct": 10.0, "levels": 13, "flatten_on_stop": True,
     "quote_per_level": 150.0, "stop_outside_range": True},
    {"auto_range_pct": 6.0, "levels": 13, "flatten_on_stop": True,
     "quote_per_level": 150.0, "stop_outside_range": True},
]


async def fetch_all(start, end):
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, start, end)
        out[sym] = df
        print(f"  fetched {sym}: {len(df)} candles")
    return out


def eval_window(dfs: dict, config: dict, per_symbol=False):
    strategy = GridStrategy({**config})
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        result = run_grid_backtest(strategy, df, cfg)
        metrics = compute_metrics(result.equity, result.trades, EQUITY, df, 0)
        rets.append(metrics["total_return_pct"])
        all_trades.extend(result.trades)
        sw = [t for t in result.trades if t["pnl"] > 0]
        sl = [t for t in result.trades if t["pnl"] <= 0]
        gw = sum(t["pnl"] for t in sw)
        gl = -sum(t["pnl"] for t in sl)
        spf = gw / gl if gl > 1e-9 else (float("inf") if gw > 0 else None)
        sym_stats[sym] = {"pf": round(spf, 3) if spf not in (None, float("inf")) else spf,
                           "trades": len(result.trades), "ret_pct": round(metrics["total_return_pct"], 4)}

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
    print("Fetching train window data...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print("Fetching test window data...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    results = []
    for config in CONFIGS:
        train_m = eval_window(train_dfs, config)
        test_m = eval_window(test_dfs, config, per_symbol=True)
        row = {"config": config, "train": train_m, "test": test_m}
        results.append(row)
        print(f"range={config['auto_range_pct']} lvl={config['levels']} "
              f"| TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/9060ecbf-f6ef-5923-9034-df492019fbdc/scratchpad/grid_5m_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
