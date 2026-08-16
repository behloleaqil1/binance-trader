"""Research script (NOT production code): trend_momentum @ 5m grid search.

Last untested TF for trend_momentum -- the family is already closed with
train/test rigor at 4h (Run 1), 1h (Run 3), 15m (Run 7), all no-edge. 5m
was skipped until now because the whipsaw failure mode (low win rate,
choppy EMA crosses) documented at every TF tested so far is expected to
get *worse* on faster candles, not better -- but "expected to be worse"
isn't the same as "tested", and mean_reversion's 5m pass (Run 9) was the
cleanest, most decisive failure of that family precisely because it filled
in the last gap. Same reasoning applies here: complete the sweep.

Grid shape mirrors Run 7's 15m grid exactly (12 combos: 3 EMA pairs x 2
rsi_buy_min x 2 require_macd) so results are directly comparable across
TFs. Uses production run_candle_backtest unmodified -- no code changes,
pure evaluation.
"""
import asyncio
import itertools
import json
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.risk.models import RiskConfig
from app.strategies.trend_momentum import TrendMomentumStrategy
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
BUFFER_DAYS = 3  # ema_slow<=50 candles @ 5m warmup is <1 day; a few days is ample margin

EMA_PAIRS = [(20, 50), (9, 21), (12, 26)]
RSI_BUY_MIN = [45, 50]
REQUIRE_MACD = [True, False]


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        out[sym] = df
        print(f"  fetched {sym}: {len(df)} candles")
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = TrendMomentumStrategy(params)
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

    combos = []
    for (ef, es), rmin, macd in itertools.product(EMA_PAIRS, RSI_BUY_MIN, REQUIRE_MACD):
        combos.append({"timeframe": TF, "ema_fast": ef, "ema_slow": es, "rsi_period": 14,
                        "rsi_buy_min": rmin, "rsi_buy_max": 70, "rsi_exit": 78,
                        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                        "require_macd": macd})

    results = []
    for params in combos:
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk) if train_m["trades"] > 0 else None
        row = {"params": params, "train": train_m, "test": test_m}
        results.append(row)
        tag = f"ema{params['ema_fast']}/{params['ema_slow']} rsi_min={params['rsi_buy_min']} macd={params['require_macd']}"
        if test_m is None:
            test_str = "None"
        else:
            test_str = (f"pf={test_m['pf']} win%={test_m['win_pct']} "
                        f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")
        print(f"{tag} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || TEST {test_str}")

    results.sort(key=lambda r: (r["train"]["pf"] if r["train"]["pf"] is not None else -1), reverse=True)
    print("\nTop-ranked by train PF:")
    for r in results[:3]:
        print(json.dumps(r))

    out_path = "/tmp/claude-0/-home-user-binance-trader/011c2543-4999-5514-a2ae-0c93a4fdfd3c/scratchpad/trend_momentum_5m_grid.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
