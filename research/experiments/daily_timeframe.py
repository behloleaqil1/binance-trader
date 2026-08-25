"""Research script (NOT production code): the 1d TIMEFRAME axis (Run 26).

DISTILLED LEARNINGS has carried "1d for all three families" as an
explicitly flagged, untested, low-priority item since Run 12 closed the
5m-4h TF sweep -- the stated expectation was "even fewer candles per
window than 4h, likely to hit the same starvation issues trend_ema=200
already showed at 4h." This run tests that prediction directly instead of
leaving it as an assumption, closing the TF-range scope question (the last
easily-testable scope assumption -- long-only/shorting is out of scope per
the hard limits, a larger architecture change not a param tune).

Standard train/test windows per the task's own methodology (150d-60d ago
optimize, 60d-0d ago validate), same original 8-symbol universe, shipped-
default params for all 3 original strategy families (trend_momentum,
mean_reversion, grid) -- no param search, no strategy code changes. Uses
UNMODIFIED production run_candle_backtest.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import json

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest, run_grid_backtest
from app.backtest.metrics import compute_metrics
from app.risk.models import RiskConfig
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.strategies.grid import GridStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-28", "2026-06-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-27", "2026-08-26"     # 60d-0d ago
BUFFER_DAYS = 210  # trend_ema=200 needs 200 daily candles of warmup
TF = "1d"

TM_PARAMS = {"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_buy_min": 50,
             "rsi_buy_max": 70, "rsi_exit": 78, "macd_fast": 12, "macd_slow": 26,
             "macd_signal": 9, "require_macd": True}
MR_PARAMS = {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14, "rsi_oversold": 30,
             "rsi_overbought": 70, "exit_at": "middle", "trend_ema": 0}
# Same shipped-default shape as Run 8 (4h)/Run 13 (5m) for direct cross-TF comparability.
GRID_PARAMS = {"auto_range_pct": 10.0, "levels": 13, "flatten_on_stop": True,
               "quote_per_level": 150.0, "stop_outside_range": True}


def make_strategy(family: str):
    if family == "trend_momentum":
        return TrendMomentumStrategy({"timeframe": TF, **TM_PARAMS})
    if family == "mean_reversion":
        return MeanReversionStrategy({"timeframe": TF, **MR_PARAMS})
    return GridStrategy({**GRID_PARAMS})


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        print(f"  {sym}: {len(out[sym])} candles fetched (incl. buffer)")
    return out


def eval_grid_window(dfs, cfg):
    strategy = GridStrategy({**GRID_PARAMS})
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            sym_stats[sym] = {"pf": None, "trades": 0, "ret_pct": 0.0}
            continue
        result = run_grid_backtest(strategy, df, cfg)
        metrics = compute_metrics(result.equity, result.trades, EQUITY, df, 0)
        rets.append(metrics["total_return_pct"])
        all_trades.extend(result.trades)
        sw = [t for t in result.trades if t["pnl"] > 0]
        sl_ = [t for t in result.trades if t["pnl"] <= 0]
        gw, gl = sum(t["pnl"] for t in sw), -sum(t["pnl"] for t in sl_)
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
    return {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
            "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4), "per_symbol": sym_stats}


def eval_window(dfs, start, end, strategy, risk, cfg):
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
    return {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
            "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4), "per_symbol": sym_stats}


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk_default = RiskConfig()
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=7.5, slippage_bps=4.0)

    print(f"Fetching {TF} train window ({TRAIN_START}..{TRAIN_END}, +{BUFFER_DAYS}d buffer)...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print(f"Fetching {TF} test window ({TEST_START}..{TEST_END}, +{BUFFER_DAYS}d buffer)...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    # Grid doesn't use indicators/warmup -- fetch its own unbuffered windows,
    # same convention as grid_5m.py/Run 8, for a clean price-range read.
    print(f"Fetching {TF} grid train window (no buffer)...")
    grid_train_dfs = {}
    for sym in SYMBOLS:
        grid_train_dfs[sym] = await fetch_klines(f"{sym}USDT", TF, TRAIN_START, TRAIN_END)
    print(f"Fetching {TF} grid test window (no buffer)...")
    grid_test_dfs = {}
    for sym in SYMBOLS:
        grid_test_dfs[sym] = await fetch_klines(f"{sym}USDT", TF, TEST_START, TEST_END)

    results = []
    print(f"\n=== 1d timeframe sweep, shipped-default params, all 3 original families ===")
    for family in ["trend_momentum", "mean_reversion"]:
        strategy = make_strategy(family)
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, strategy, risk_default, cfg)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, strategy, risk_default, cfg)
        row = {"family": family, "tf": TF, "train": train_m, "test": test_m}
        results.append(row)
        print(f"\n{family} @ {TF}:")
        print(f"  train: pf={train_m['pf']} win%={train_m['win_pct']} n={train_m['trades']} ret%={train_m['avg_ret_pct']}")
        print(f"  test:  pf={test_m['pf']} win%={test_m['win_pct']} n={test_m['trades']} ret%={test_m['avg_ret_pct']}")
        print(f"  train per-symbol: {train_m['per_symbol']}")
        print(f"  test  per-symbol: {test_m['per_symbol']}")

    grid_train_m = eval_grid_window(grid_train_dfs, cfg)
    grid_test_m = eval_grid_window(grid_test_dfs, cfg)
    results.append({"family": "grid", "tf": TF, "train": grid_train_m, "test": grid_test_m})
    print(f"\ngrid @ {TF}:")
    print(f"  train: pf={grid_train_m['pf']} win%={grid_train_m['win_pct']} n={grid_train_m['trades']} ret%={grid_train_m['avg_ret_pct']}")
    print(f"  test:  pf={grid_test_m['pf']} win%={grid_test_m['win_pct']} n={grid_test_m['trades']} ret%={grid_test_m['avg_ret_pct']}")
    print(f"  train per-symbol: {grid_train_m['per_symbol']}")
    print(f"  test  per-symbol: {grid_test_m['per_symbol']}")

    with open("/tmp/claude-0/-home-user-binance-trader/ad02bc33-8300-5b42-ac65-5e2af5e0a222/scratchpad/run26_daily_tf.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to scratchpad/run26_daily_tf.json")


if __name__ == "__main__":
    asyncio.run(main())
