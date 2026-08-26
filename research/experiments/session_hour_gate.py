"""Research script (NOT production code): UTC session-hour BUY gate (Run 28).

Hypothesis: every signal-source category tried across 27 runs is
price-level/band, moving-average, price-shape, or cross-symbol/volume
(per DISTILLED LEARNINGS). A calendar/session-time filter is a genuinely
different, 5th category: it doesn't derive from OHLCV at all, just the
candle's own UTC open_time. Crypto trades 24/7 but liquidity/participation
is known to cluster by session (Asia/EU/US); gating entries to a session
window is mechanically distinct from every closed price/volume gate (ADX,
relative-volume, MTF trend-direction) tested so far.

Implemented as a thin subclass of production TrendMomentumStrategy /
MeanReversionStrategy — decide() defers entirely to the parent's unmodified
decide() and adds exactly one veto on BUY: block unless the candle's own
UTC hour-of-day falls inside a configured [start_hour, end_hour) window (no
lookahead — uses only the current candle's own open_time). No production
code touched; run_candle_backtest (production, unmodified) runs on the 1h
data exactly as-is.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import SignalAction
from app.risk.models import RiskConfig
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-29", "2026-06-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-27", "2026-08-26"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-29", "2026-03-29"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 15  # extra history before window start for EMA/BB/RSI warmup


def _hour_ok(open_time_ms: int, start_hour: int, end_hour: int) -> bool:
    hour = pd.Timestamp(open_time_ms, unit="ms", tz="UTC").hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour  # wraps past midnight


class TrendMomentumSessionGated(TrendMomentumStrategy):
    """session_gate: None/False = off (byte-for-byte parent behavior).
    Else (start_hour, end_hour) UTC half-open window; BUY vetoed outside it."""
    session_gate = None

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.session_gate and sig.action == SignalAction.BUY:
            sh, eh = self.session_gate
            ot = int(df.iloc[i]["open_time"])
            if not _hour_ok(ot, sh, eh):
                return self.hold(symbol, f"BUY vetoed: outside session window "
                                  f"UTC[{sh}:00,{eh}:00) — hour={pd.Timestamp(ot, unit='ms', tz='UTC').hour}",
                                  price=sig.price)
        return sig


class MeanReversionSessionGated(MeanReversionStrategy):
    session_gate = None

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if self.session_gate and sig.action == SignalAction.BUY:
            sh, eh = self.session_gate
            ot = int(df.iloc[i]["open_time"])
            if not _hour_ok(ot, sh, eh):
                return self.hold(symbol, f"BUY vetoed: outside session window "
                                  f"UTC[{sh}:00,{eh}:00) — hour={pd.Timestamp(ot, unit='ms', tz='UTC').hour}",
                                  price=sig.price)
        return sig


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, cls, params: dict, session_gate, risk: RiskConfig,
                 per_symbol=False):
    strategy = cls(params)
    strategy.session_gate = session_gate
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


TM_PARAMS = {"timeframe": TF, "ema_fast": 20, "ema_slow": 50, "rsi_period": 14,
             "rsi_buy_min": 50, "rsi_buy_max": 70, "rsi_exit": 78,
             "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "require_macd": True}
MR_PARAMS = {"timeframe": TF, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14,
             "rsi_oversold": 30, "rsi_overbought": 70, "exit_at": "middle", "trend_ema": 0}

# Session windows (UTC): baseline (off), Asia, EU, US, EU/US overlap (peak liquidity).
SESSIONS = [
    ("baseline (no gate)", None),
    ("Asia 00-08 UTC", (0, 8)),
    ("EU 07-15 UTC", (7, 15)),
    ("US 13-21 UTC", (13, 21)),
    ("EU/US overlap 13-16 UTC", (13, 16)),
]


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()
    print("Fetching train/test windows...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    test_dfs = await fetch_all(TEST_START, TEST_END)

    results = []
    for base_name, cls, params in (("trend_momentum", TrendMomentumSessionGated, TM_PARAMS),
                                    ("mean_reversion", MeanReversionSessionGated, MR_PARAMS)):
        for label, gate in SESSIONS:
            train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, cls, params, gate, risk)
            test_m = eval_window(test_dfs, TEST_START, TEST_END, cls, params, gate, risk)
            row = {"base": base_name, "label": label, "session_gate": gate,
                   "train": train_m, "test": test_m}
            results.append(row)
            print(f"[{base_name}] {label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                  f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                  f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                  f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # Third non-overlapping window + per-symbol breakdown for any near-miss
    # (test PF>1.1 and test n>=30 while train PF also clears, or test PF>1.1
    # with train PF close to 1 — the same near-miss bar used throughout this
    # programme).
    near_misses = [r for r in results if r["session_gate"] is not None
                   and r["test"]["pf"] is not None and r["test"]["pf"] > 1.1
                   and r["test"]["trades"] >= 30]
    print(f"\n{len(near_misses)} near-miss config(s) clearing the OOS screen: "
          f"{[(r['base'], r['label']) for r in near_misses]}")
    if near_misses:
        print("Fetching OLDER window for cross-check...")
        older_dfs = await fetch_all(OLDER_START, OLDER_END)
        for r in near_misses:
            cls = TrendMomentumSessionGated if r["base"] == "trend_momentum" else MeanReversionSessionGated
            params = TM_PARAMS if r["base"] == "trend_momentum" else MR_PARAMS
            older_m = eval_window(older_dfs, OLDER_START, OLDER_END, cls, params,
                                   r["session_gate"], risk, per_symbol=True)
            train_ps = eval_window(train_dfs, TRAIN_START, TRAIN_END, cls, params,
                                    r["session_gate"], risk, per_symbol=True)
            test_ps = eval_window(test_dfs, TEST_START, TEST_END, cls, params,
                                   r["session_gate"], risk, per_symbol=True)
            r["older"] = older_m
            r["train_per_symbol"] = train_ps["per_symbol"]
            r["test_per_symbol"] = test_ps["per_symbol"]
            r["older_per_symbol"] = older_m["per_symbol"]
            print(f"[{r['base']}] {r['label']} OLDER window: pf={older_m['pf']} "
                  f"win%={older_m['win_pct']} n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            print("  Per-symbol (TRAIN):", train_ps["per_symbol"])
            print("  Per-symbol (TEST):", test_ps["per_symbol"])
            print("  Per-symbol (OLDER):", older_m["per_symbol"])

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/c5f03a68-7f51-545a-b233-c68f84e4f8c7/scratchpad/session_hour_gate_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
