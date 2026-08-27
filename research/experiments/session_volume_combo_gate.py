"""Research script (NOT production code): Run 30 — combined session-hour +
relative-volume BUY gate (interaction of two previously-CLOSED single-axis
levers).

Every single-axis confirmation gate tried in this programme (ADX, relative-
volume, MTF trend-direction, session-hour, day-of-week) has closed as
decisive-reject or noise on its own. DISTILLED LEARNINGS' own flagged next
step (end of Run 29 section) names combining two closed levers as the one
unexplored combination, while predicting it likely inherits the same
regime-luck failure rather than creating new edge. This run tests that
prediction directly rather than assuming it: does requiring BOTH real
participation (volume >= vol_mult x its own rolling mean) AND a favorable
session window (each base's own best single-gate window from Run 28)
survive where neither did alone?

trend_momentum@1h: session=US 13-21 UTC (Run 28's best single-gate train PF
for this base, 0.889) x volume gate (Run 15's mechanism, vol_mult in
{1.2, 1.5}, moderate, not the most sample-starved extreme).
mean_reversion@1h: session=EU 07-15 UTC (Run 28's best single-gate train PF
for this base, 1.088 — the highest ever recorded for this base, though it
failed its 3rd-window check) x the same volume gate mechanism (never before
applied to mean_reversion — Run 15 only tested it on trend_momentum).

Implemented as a thin subclass of production TrendMomentumStrategy /
MeanReversionStrategy — decide() defers entirely to the parent's unmodified
decide() and adds at most two vetoes on BUY (session window, then relative
volume), the same "defer to parent, add vetoes" pattern used for every
prior gate in this programme. No production code touched; run_candle_backtest
(production, unmodified) runs on the 1h data exactly as-is. Any config that
clears or near-clears both OOS bars gets the standard 3rd-window
(2025-12-29..2026-03-29) + per-symbol cross-check before being trusted.
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
from app.strategies.mean_reversion import MeanReversionStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-30", "2026-06-28"   # 150d-60d ago (today's anchor 2026-08-27)
TEST_START, TEST_END = "2026-06-28", "2026-08-27"     # 60d-0d ago
OLDER_START, OLDER_END = "2025-12-30", "2026-03-30"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 15


def _hour_ok(open_time_ms: int, start_hour: int, end_hour: int) -> bool:
    hour = pd.Timestamp(open_time_ms, unit="ms", tz="UTC").hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


class TrendMomentumComboGated(TrendMomentumStrategy):
    session_gate = None  # (start_hour, end_hour) or None
    vol_period: int = 20
    vol_mult: float | None = None

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = super().compute_indicators(df)
        out["vol_avg"] = df["volume"].rolling(self.vol_period, min_periods=self.vol_period).mean()
        out["rel_vol"] = df["volume"] / out["vol_avg"]
        return out

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if sig.action != SignalAction.BUY:
            return sig
        if self.session_gate:
            sh, eh = self.session_gate
            ot = int(df.iloc[i]["open_time"])
            if not _hour_ok(ot, sh, eh):
                return self.hold(symbol, f"BUY vetoed: outside session window "
                                  f"UTC[{sh}:00,{eh}:00)", price=sig.price)
        if self.vol_mult is not None:
            rv = float(df.iloc[i]["rel_vol"])
            if math.isnan(rv) or rv < self.vol_mult:
                return self.hold(symbol, f"BUY vetoed: rel_vol {rv:.2f} < floor "
                                  f"{self.vol_mult}", price=sig.price)
        return sig


class MeanReversionComboGated(MeanReversionStrategy):
    session_gate = None
    vol_period: int = 20
    vol_mult: float | None = None

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = super().compute_indicators(df)
        out["vol_avg"] = df["volume"].rolling(self.vol_period, min_periods=self.vol_period).mean()
        out["rel_vol"] = df["volume"] / out["vol_avg"]
        return out

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if sig.action != SignalAction.BUY:
            return sig
        if self.session_gate:
            sh, eh = self.session_gate
            ot = int(df.iloc[i]["open_time"])
            if not _hour_ok(ot, sh, eh):
                return self.hold(symbol, f"BUY vetoed: outside session window "
                                  f"UTC[{sh}:00,{eh}:00)", price=sig.price)
        if self.vol_mult is not None:
            rv = float(df.iloc[i]["rel_vol"])
            if math.isnan(rv) or rv < self.vol_mult:
                return self.hold(symbol, f"BUY vetoed: rel_vol {rv:.2f} < floor "
                                  f"{self.vol_mult}", price=sig.price)
        return sig


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
    return out


def eval_window(dfs, start, end, cls, params, session_gate, vol_mult, risk, per_symbol=False):
    strategy = cls(params)
    strategy.session_gate = session_gate
    strategy.vol_mult = vol_mult
    strategy.vol_period = 20
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

# (label, session_gate, vol_mult)
TM_VARIANTS = [
    ("baseline (no gates)", None, None),
    ("session-only US 13-21", (13, 21), None),
    ("volume-only vol_mult=1.2", None, 1.2),
    ("volume-only vol_mult=1.5", None, 1.5),
    ("combo US session + vol=1.2", (13, 21), 1.2),
    ("combo US session + vol=1.5", (13, 21), 1.5),
]
MR_VARIANTS = [
    ("baseline (no gates)", None, None),
    ("session-only EU 07-15", (7, 15), None),
    ("volume-only vol_mult=1.2", None, 1.2),
    ("volume-only vol_mult=1.5", None, 1.5),
    ("combo EU session + vol=1.2", (7, 15), 1.2),
    ("combo EU session + vol=1.5", (7, 15), 1.5),
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
    for base_name, cls, params, variants in (
        ("trend_momentum", TrendMomentumComboGated, TM_PARAMS, TM_VARIANTS),
        ("mean_reversion", MeanReversionComboGated, MR_PARAMS, MR_VARIANTS),
    ):
        for label, sgate, vmult in variants:
            train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, cls, params, sgate, vmult, risk)
            test_m = eval_window(test_dfs, TEST_START, TEST_END, cls, params, sgate, vmult, risk)
            row = {"base": base_name, "label": label, "session_gate": sgate, "vol_mult": vmult,
                   "train": train_m, "test": test_m}
            results.append(row)
            print(f"[{base_name}] {label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                  f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                  f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                  f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # Standard near-miss screen: test PF>1.1 and test n>=30 (regardless of train).
    near_misses = [r for r in results
                   if r["test"]["pf"] is not None and r["test"]["pf"] > 1.1
                   and r["test"]["trades"] >= 30]
    print(f"\n{len(near_misses)} near-miss config(s) clearing the OOS screen: "
          f"{[(r['base'], r['label']) for r in near_misses]}")
    if near_misses:
        print("Fetching OLDER window for cross-check...")
        older_dfs = await fetch_all(OLDER_START, OLDER_END)
        for r in near_misses:
            cls = TrendMomentumComboGated if r["base"] == "trend_momentum" else MeanReversionComboGated
            params = TM_PARAMS if r["base"] == "trend_momentum" else MR_PARAMS
            older_m = eval_window(older_dfs, OLDER_START, OLDER_END, cls, params,
                                   r["session_gate"], r["vol_mult"], risk, per_symbol=True)
            train_ps = eval_window(train_dfs, TRAIN_START, TRAIN_END, cls, params,
                                    r["session_gate"], r["vol_mult"], risk, per_symbol=True)
            test_ps = eval_window(test_dfs, TEST_START, TEST_END, cls, params,
                                   r["session_gate"], r["vol_mult"], risk, per_symbol=True)
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
    out_path = "/tmp/claude-0/-home-user-binance-trader/e177b2aa-b696-5994-a21e-9214a655bce3/scratchpad/session_volume_combo_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
