"""Research script (NOT production code): volume-confirmed trend_momentum.

Hypothesis: trend_momentum's known failure mode across every TF tested
(15m/1h/4h/5m, Runs 1/3/7/12) is whipsaw EMA-cross entries during weak/choppy
conditions. Every prior confirmation attempt has re-used indicators derived
from price alone (MACD, then ADX in Runs 10-11 — both closed, ADX floor/
ceiling failed a 3rd-window check or was flat-to-worse). This is the first
genuinely different indicator FAMILY tried: relative VOLUME at the entry
candle. Real breakouts are commonly associated with participation (volume)
confirming the move; a low-volume EMA cross is more likely a fakeout/noise
crossing than a real trend start. Gate: only take the BUY when the entry
candle's volume is >= vol_mult * its own N-period rolling mean volume.

Implemented as a thin subclass of the production TrendMomentumStrategy —
compute_indicators adds one relative-volume column, decide() defers entirely
to the parent's decide() and only adds one extra veto on BUY signals. No
production code is touched; run_candle_backtest (production, unmodified) is
used as-is. Fixed at the same 1h shipped-default combo Run 11 used for the
ADX floor test (ema_fast=20, ema_slow=50, rsi_buy_min=50, require_macd=True)
for direct comparability between gate mechanisms on the same base signal.
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

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-18", "2026-08-17"     # 60d-0d ago (today's anchor)
BUFFER_DAYS = 15  # extra history before window start for EMA/volume warmup


class TrendMomentumVolumeGated(TrendMomentumStrategy):
    """Adds one veto on top of the unmodified parent decide(): BUY signals are
    blocked unless volume at the entry candle is >= vol_mult * its own
    vol_period-candle rolling mean volume (None = off, behaves identically to
    the parent). vol_mult/vol_period are NOT routed through
    param_specs()/validate_params() (which silently drops unknown keys) — set
    directly as instance attributes after construction, same pattern as
    Run 11's adx_min_for_entry."""

    vol_period: int = 20
    vol_mult: float | None = None

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = super().compute_indicators(df)
        out["vol_avg"] = df["volume"].rolling(self.vol_period, min_periods=self.vol_period).mean()
        out["rel_vol"] = df["volume"] / out["vol_avg"]
        return out

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.vol_mult is not None and sig.action == SignalAction.BUY:
            rv = float(df.iloc[i]["rel_vol"])
            if math.isnan(rv) or rv < self.vol_mult:
                return self.hold(symbol, f"BUY vetoed: rel_vol {rv:.2f} < floor "
                                  f"{self.vol_mult} (low-volume cross, not confirmed)",
                                  price=sig.price)
        return sig


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        out[sym] = df
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = TrendMomentumVolumeGated(params)
    strategy.vol_period = params.get("vol_period", 20)
    strategy.vol_mult = params.get("vol_mult")
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
                   "require_macd": True, "vol_period": 20}
    mults = [None, 1.0, 1.2, 1.5, 2.0]

    results = []
    for m in mults:
        params = {**base_params, "vol_mult": m}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        row = {"params": params, "vol_mult": m, "train": train_m, "test": test_m}
        results.append(row)
        print(f"vol_mult={m} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = ("/tmp/claude-0/-home-user-binance-trader/"
                "087a2c30-0b91-56e0-b7a1-30a9ea1661d5/scratchpad/volume_gate_results.json")
    with open(out_path, "w") as f:
        json.dump({"threshold_sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}.")


if __name__ == "__main__":
    asyncio.run(main())
