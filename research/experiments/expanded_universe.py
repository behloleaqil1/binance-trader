"""Research script (NOT production code): the SYMBOL-UNIVERSE axis (Run 25).

24 prior runs closed the signal, sizing, exit-mechanism, and fee-level axes on
the fixed 8-symbol majors universe (BTC, ETH, SOL, BNB, XRP, LINK, DOGE, ADA).
DISTILLED LEARNINGS explicitly flags the 8-symbol universe itself as a
remaining, untested scope assumption for the *per-symbol* strategy families
(previously only tested for the cross-symbol constructions, where it was
flagged as out of reach). This run tests whether the "no edge" verdict for
trend_momentum and mean_reversion at 1h is a property of these specific 8
majors, or holds on a disjoint set of 8 other well-established, liquid
USDT pairs.

New universe (zero overlap with the original 8): AVAX, DOT, LTC, ATOM, NEAR,
UNI, TRX, ETC -- all long-listed, liquid Binance USDT pairs, chosen to avoid
any of the extreme-illiquidity/short-history confounds a brand-new listing
would introduce.

No strategy code changes, no param search -- shipped-default entry params
(byte-for-byte identical to Run 23's TM_PARAMS/MR_PARAMS) throughout. Only
the symbol list varies. Uses UNMODIFIED production run_candle_backtest.
Same train/test/older windows as Run 21-24 for direct comparability.
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

ORIGINAL_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
NEW_SYMBOLS = ["AVAX", "DOT", "LTC", "ATOM", "NEAR", "UNI", "TRX", "ETC"]
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago (Run 21-24's window)
TEST_START, TEST_END = "2026-06-18", "2026-08-18"     # 60d-0d ago (Run 21-24's window)
OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 20
SCRATCH = "/tmp/claude-0/-home-user-binance-trader/1d9f83b6-4ef5-52b6-b401-59fd4598a8cf/scratchpad"

FEE_BPS, SLIP_BPS = 7.5, 4.0  # shipped default, unchanged

TM_PARAMS = {"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_buy_min": 50,
             "rsi_buy_max": 70, "rsi_exit": 78, "macd_fast": 12, "macd_slow": 26,
             "macd_signal": 9, "require_macd": True}
MR_PARAMS = {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14, "rsi_oversold": 30,
             "rsi_overbought": 70, "exit_at": "middle", "trend_ema": 0}


def make_strategy(family: str, tf: str):
    if family == "trend_momentum":
        return TrendMomentumStrategy({"timeframe": tf, **TM_PARAMS})
    return MeanReversionStrategy({"timeframe": tf, **MR_PARAMS})


async def fetch_all(symbols, start, end, tf):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in symbols:
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
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)

    bases = [
        {"family": "trend_momentum", "tf": "1h"},
        {"family": "trend_momentum", "tf": "4h"},
        {"family": "mean_reversion", "tf": "1h"},
    ]

    tf_dfs = {}
    for tf in ["1h", "4h"]:
        print(f"Fetching {tf} windows for NEW universe {NEW_SYMBOLS}...")
        tf_dfs[tf] = {
            "train": await fetch_all(NEW_SYMBOLS, TRAIN_START, TRAIN_END, tf),
            "test": await fetch_all(NEW_SYMBOLS, TEST_START, TEST_END, tf),
        }

    results = []
    print("\n=== Expanded-universe sweep (production run_candle_backtest, unmodified) ===")
    for b in bases:
        strategy = make_strategy(b["family"], b["tf"])
        train_m = eval_window(tf_dfs[b["tf"]]["train"], TRAIN_START, TRAIN_END, strategy, risk_default, cfg)
        test_m = eval_window(tf_dfs[b["tf"]]["test"], TEST_START, TEST_END, strategy, risk_default, cfg)
        row = {"family": b["family"], "tf": b["tf"], "universe": "new8",
               "train": train_m, "test": test_m}
        results.append(row)
        print(f"{b['family']}@{b['tf']} new8 | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} n={test_m['trades']} "
              f"ret%={test_m['avg_ret_pct']}")

    near_misses = [r for r in results
                   if (r["train"]["pf"] or 0) > 1.1 and (r["test"]["pf"] or 0) > 1.1
                   and r["train"]["trades"] >= 30 and r["test"]["trades"] >= 30]
    if near_misses:
        print(f"\n{len(near_misses)} config(s) cleared train+test PF>1.1 with n>=30 -- 3rd window + per-symbol...")
        older_dfs = {}
        for r in near_misses:
            tf = r["tf"]
            if tf not in older_dfs:
                older_dfs[tf] = await fetch_all(NEW_SYMBOLS, OLDER_START, OLDER_END, tf)
            strategy = make_strategy(r["family"], tf)
            older_m = eval_window(older_dfs[tf], OLDER_START, OLDER_END, strategy, risk_default, cfg, per_symbol=True)
            test_ps = eval_window(tf_dfs[tf]["test"], TEST_START, TEST_END, strategy, risk_default, cfg, per_symbol=True)
            r["older"] = older_m
            r["test_per_symbol"] = test_ps["per_symbol"]
            print(f"{r['family']}@{tf} OLDER window: pf={older_m['pf']} win%={older_m['win_pct']} "
                  f"n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            print(f"  Per-symbol TEST: {test_ps['per_symbol']}")
    else:
        print("\nNo config cleared train+test PF>1.1 with n>=30 -- no 3rd-window check needed.")

    with open(SCRATCH + "/expanded_universe_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved full results to {SCRATCH}/expanded_universe_results.json")


if __name__ == "__main__":
    asyncio.run(main())
