"""Research script (NOT production code): the FEE/COST-LEVEL axis (Run 23).

22 prior runs varied signal (which trades), sizing (how big), and exit
mechanism (when/how they exit) -- all closed, none manufactured edge.
DISTILLED LEARNINGS explicitly flags the programme's *scope assumptions*
(fee level, the 8-symbol universe, the 1h-4h TF range, long-only) as the
next place to look, ahead of more constructions inside the closed axes.
This run opens the FEE axis directly: it asserts "fees turn near-breakeven
setups negative" (trend_momentum's best-ever train PF was 0.99, essentially
breakeven pre-cost) but that claim was never quantified. This sweeps total
round-trip trading cost (fee_bps + slippage_bps, held at the shipped 7.5/4.0
ratio) down through a realistic reduced tier (BNB fee discount, ~4.0/2.0) to
a near-zero floor (1.0/0.5) and a theoretical zero, on trend_momentum's two
best-characterized TFs (15m, 1h) plus mean_reversion@1h as a contrast (a
family whose train-side PF has never once exceeded ~0.6 regardless of any
prior lever -- if fees were the bottleneck there too, cost reduction should
still leave it exposed to the same conclusion trend_momentum gets).

No strategy code changes, no param search -- shipped-default entry params
throughout (already exhaustively characterized in decisions.jsonl). Only
`SimConfig.fee_bps`/`slippage_bps` vary. Uses UNMODIFIED production
run_candle_backtest.

Same train/test windows as Run 21/22 for direct comparability with their
recorded 7.5/4.0-bps control numbers at 1h.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import json

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.risk.models import RiskConfig
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago (Run 21/22's window)
TEST_START, TEST_END = "2026-06-18", "2026-08-18"     # 60d-0d ago (Run 21/22's window)
OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 20
SCRATCH = "/tmp/claude-0/-home-user-binance-trader/ebce9fed-4278-5292-8452-90d1e68cf882/scratchpad"

COST_TIERS = [
    {"label": "shipped (7.5/4.0)", "fee_bps": 7.5, "slip_bps": 4.0},
    {"label": "bnb_discount (4.0/2.0)", "fee_bps": 4.0, "slip_bps": 2.0},
    {"label": "near_zero (1.0/0.5)", "fee_bps": 1.0, "slip_bps": 0.5},
    {"label": "theoretical_zero (0/0)", "fee_bps": 0.0, "slip_bps": 0.0},
]

TM_PARAMS = {"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_buy_min": 50,
             "rsi_buy_max": 70, "rsi_exit": 78, "macd_fast": 12, "macd_slow": 26,
             "macd_signal": 9, "require_macd": True}
MR_PARAMS = {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14, "rsi_oversold": 30,
             "rsi_overbought": 70, "exit_at": "middle", "trend_ema": 0}


def make_strategy(family: str, tf: str):
    if family == "trend_momentum":
        return TrendMomentumStrategy({"timeframe": tf, **TM_PARAMS})
    return MeanReversionStrategy({"timeframe": tf, **MR_PARAMS})


async def fetch_all(start, end, tf):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs, start, end, strategy, risk, cfg, per_symbol=False):
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        res = run_candle_backtest(strategy, risk, df, cfg, symbol=sym)
        trades, eq = res.trades, res.equity
        window_trades = [t for t in trades if start_ms <= t["opened_at"] < end_ms]
        all_trades.extend(window_trades)
        in_win = [(ts, v) for ts, v in zip(eq.index, eq.values) if start_ms <= ts < end_ms]
        ret = (in_win[-1][1] / in_win[0][1] - 1) * 100 if len(in_win) >= 2 else 0.0
        rets.append(ret)
        sw = [t for t in window_trades if t["pnl"] > 0]
        sl_ = [t for t in window_trades if t["pnl"] <= 0]
        gw, gl = sum(t["pnl"] for t in sw), -sum(t["pnl"] for t in sl_)
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
    risk_default = RiskConfig()

    bases = [
        {"family": "trend_momentum", "tf": "15m"},
        {"family": "trend_momentum", "tf": "1h"},
        {"family": "mean_reversion", "tf": "1h"},
    ]

    tf_dfs = {}
    for tf in ["15m", "1h"]:
        print(f"Fetching {tf} windows...")
        tf_dfs[tf] = {
            "train": await fetch_all(TRAIN_START, TRAIN_END, tf),
            "test": await fetch_all(TEST_START, TEST_END, tf),
        }

    results = []
    print("\n=== Fee/cost-tier sweep (production run_candle_backtest, unmodified) ===")
    for b in bases:
        strategy = make_strategy(b["family"], b["tf"])
        for tier in COST_TIERS:
            cfg = SimConfig(initial_equity=EQUITY, fee_bps=tier["fee_bps"], slippage_bps=tier["slip_bps"])
            train_m = eval_window(tf_dfs[b["tf"]]["train"], TRAIN_START, TRAIN_END, strategy, risk_default, cfg)
            test_m = eval_window(tf_dfs[b["tf"]]["test"], TEST_START, TEST_END, strategy, risk_default, cfg)
            row = {"family": b["family"], "tf": b["tf"], "tier": tier["label"],
                   "fee_bps": tier["fee_bps"], "slip_bps": tier["slip_bps"],
                   "train": train_m, "test": test_m}
            results.append(row)
            print(f"{b['family']}@{b['tf']} {tier['label']} | TRAIN pf={train_m['pf']} "
                  f"win%={train_m['win_pct']} n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                  f"TEST pf={test_m['pf']} win%={test_m['win_pct']} n={test_m['trades']} "
                  f"ret%={test_m['avg_ret_pct']}")

    # near-miss escalation: any non-control tier clearing BOTH train and test OOS-style bars
    # (train pf>1.1 too, since this axis is about revealing latent edge, not just test luck)
    near_misses = [r for r in results if r["tier"] != "shipped (7.5/4.0)"
                   and (r["train"]["pf"] or 0) > 1.1 and (r["test"]["pf"] or 0) > 1.1
                   and r["train"]["trades"] >= 30 and r["test"]["trades"] >= 30]
    if near_misses:
        print(f"\n{len(near_misses)} config(s) cleared train+test PF>1.1 with n>=30 -- 3rd window + per-symbol...")
        older_dfs = {}
        for r in near_misses:
            tf = r["tf"]
            if tf not in older_dfs:
                older_dfs[tf] = await fetch_all(OLDER_START, OLDER_END, tf)
            strategy = make_strategy(r["family"], tf)
            cfg = SimConfig(initial_equity=EQUITY, fee_bps=r["fee_bps"], slippage_bps=r["slip_bps"])
            older_m = eval_window(older_dfs[tf], OLDER_START, OLDER_END, strategy, risk_default, cfg, per_symbol=True)
            test_ps = eval_window(tf_dfs[tf]["test"], TEST_START, TEST_END, strategy, risk_default, cfg, per_symbol=True)
            r["older"] = older_m
            r["test_per_symbol"] = test_ps["per_symbol"]
            print(f"{r['family']}@{tf} {r['tier']} OLDER window: pf={older_m['pf']} "
                  f"win%={older_m['win_pct']} n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            print(f"  Per-symbol TEST: {test_ps['per_symbol']}")
    else:
        print("\nNo config cleared train+test PF>1.1 with n>=30 -- no 3rd-window check needed.")

    with open(SCRATCH + "/fee_sensitivity_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved full results to {SCRATCH}/fee_sensitivity_results.json")


if __name__ == "__main__":
    asyncio.run(main())
