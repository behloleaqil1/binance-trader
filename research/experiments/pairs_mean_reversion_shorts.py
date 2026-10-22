"""Research script (NOT production code): Run 66.

Tests the one remaining open sub-item flagged by Run 65 and the
2026-10-21 capability-addition note: pairs mean-reversion *with actual
shorting*, as opposed to the long-laggard-only proxy already closed in
Run 20 (`pairs_mean_reversion.py`). Run 20 only ever bought the laggard
leg of a pair (spot/long-only engine at the time) — a real-money-
implementable proxy for the relative-value thesis, but not a true
market-neutral spread trade, and explicitly disclosed basis risk (if both
legs fall together while the ratio still reverts, the long-only proxy can
still lose money). The 2026-10-21 capability addition (backtest-only
`allow_short` on `run_candle_backtest`, generic — works for any strategy
emitting SHORT/COVER signals, not just trend_momentum) makes the TRUE
construction testable for the first time: LONG the laggard AND SHORT the
leader simultaneously, removing market beta from the bet.

Run 65 already found that mirroring trend_momentum's long signal into a
short (same EMA-cross+RSI+MACD mechanism) fails identically to the long
side -- fees apply symmetrically, no edge on either side. This run checks
whether the market-neutral *construction* itself (removing shared-market-
direction risk via a true two-legged hedge) changes the outcome for the
one cross-symbol mean-reversion signal that came closest to a "no train
support" clean rejection (Run 20: 11/42 near-misses, but ALL had train
PF<1, so the signal itself never had train-side support -- the long-only
proxy never got a fair test of whether basis risk was swamping real
convergence edge). Prediction stated up front (per Run 65's own note):
fees apply per leg, so a 2-leg hedge pays roughly 2x the round-trip cost
of the long-only proxy -- if anything this construction should look WORSE
on a pure cost basis, even if it cleans up the basis-risk noise. Hypothesis
is being tested honestly, not fished for a positive result.

Mechanics: for pair (alt, BTC), identical causal rolling z-score of
spread = log(close_alt) - log(close_anchor) over `lookback` bars as Run 20
(no lookahead). Signed per-leg signal:
  alt leg:    signal_z = +z   (z very positive => alt rich vs anchor => SHORT alt;
                                z very negative => alt cheap vs anchor => BUY alt)
  anchor leg: signal_z = -z   (mirror -- exactly opposite side of every trade)
Entry: |signal_z| > entry_z, direction per sign. Exit: position flips to
flat once signal_z crosses back through +-exit_z from whichever side it
entered (symmetric to the long-only proxy's entry_z/exit_z meaning, just
doubled to cover both signs). Each leg is an independent symbol backtest
in this engine (as every prior cross-symbol script has done) with its own
sizing/equity curve; trades and returns are aggregated across both legs
of a pair, matching the methodology trend_momentum_shorts.py and
pairs_mean_reversion.py both already used. RiskConfig defaults (2% SL /
4% TP) unchanged, never loosened. Same 7.5bps fees / 4bps slippage,
8-symbol-derived universe (7 alts vs BTC anchor), train (150d-60d ago) /
test (60d-0d ago) split, anti-noise bar OOS PF>1.1 AND >=30 OOS trades.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file.
"""
import asyncio
import json
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import PositionView, Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.config import Settings
from app.db import database

ANCHOR = "BTC"
ALTS = ["ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

OLDER_START, OLDER_END = "2026-02-24", "2026-05-25"   # 240d-150d ago, 3rd-window check
TRAIN_START, TRAIN_END = "2026-05-25", "2026-08-23"   # 150d-60d ago
TEST_START, TEST_END = "2026-08-23", "2026-10-22"     # 60d-0d ago (today's anchor)


class PairsMeanReversionShortStrategy(Strategy):
    """True two-legged pairs trade: SHORT this symbol when it has
    outperformed its pair partner by more than entry_z rolling std devs,
    BUY it when it has underperformed by more than entry_z. Exit (flat)
    once the signal reverts back through +-exit_z. pair_signal_z column
    must already be present on df (merged in by the caller, signed per
    leg -- see with_pair_columns below)."""
    id = "pairs_mean_reversion_short"
    name = "Pairs Mean Reversion (Short-Enabled)"
    description = ("True market-neutral pairs trade: short the relative "
                    "outperformer, long the relative underperformer within "
                    "a pair, exit once the spread reverts.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("lookback_period", "Spread z-score lookback (bars)", "int", 50, min=10, max=300),
            ParamSpec("entry_z", "Enter when |signal_z| >", "float", 1.5, min=0.5, max=4.0),
            ParamSpec("exit_z", "Exit when signal crosses back through +-", "float", 0.3, min=0.0, max=3.0),
            ParamSpec("allow_short", "Allow short entries (backtest-only)", "bool", True),
        ]

    def required_history(self) -> int:
        return self.params["lookback_period"] + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df  # pair_signal_z already merged in by the caller

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        sz = row.get("pair_signal_z")
        close = float(row["close"])
        if pd.isna(sz):
            return self.hold(symbol, "spread z-score warming up", price=close)
        state = f"close={close:.6g} signal_z={sz:.3f}"

        if position is None:
            if sz > p["entry_z"]:
                return Signal(SignalAction.SHORT, symbol, self.id,
                              f"outperformed pair partner by {sz:.2f} std devs, shorting. {state}",
                              price=close)
            if sz < -p["entry_z"]:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"underperformed pair partner by {-sz:.2f} std devs, buying. {state}",
                              price=close)
            return self.hold(symbol, f"spread within entry band. {state}", price=close)

        if position.side == "SHORT":
            if sz < p["exit_z"]:
                return Signal(SignalAction.COVER, symbol, self.id,
                              f"spread reverted below exit threshold {p['exit_z']}, covering. {state}",
                              price=close)
            return self.hold(symbol, f"still overperforming, holding short. {state}", price=close)
        else:  # LONG
            if sz > -p["exit_z"]:
                return Signal(SignalAction.SELL, symbol, self.id,
                              f"spread reverted above exit threshold {-p['exit_z']}, selling. {state}",
                              price=close)
            return self.hold(symbol, f"still underperforming, holding long. {state}", price=close)


async def fetch_pair(alt, anchor, start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    df_alt = await fetch_klines(f"{alt}USDT", tf, buf_start, end)
    df_anchor = await fetch_klines(f"{anchor}USDT", tf, buf_start, end)
    return {alt: df_alt, anchor: df_anchor}


def build_pair_z(dfs: dict, alt: str, anchor: str, lookback: int) -> pd.Series:
    """Causal rolling z-score of spread = log(close_alt) - log(close_anchor),
    indexed by open_time. Row i only uses spread values up to and including
    row i (rolling().mean()/.std() are backward-looking by construction, no
    lookahead)."""
    closes = pd.DataFrame({
        alt: dfs[alt].set_index("open_time")["close"],
        anchor: dfs[anchor].set_index("open_time")["close"],
    }).sort_index()
    log_spread = np.log(closes[alt]) - np.log(closes[anchor])
    roll_mean = log_spread.rolling(lookback).mean()
    roll_std = log_spread.rolling(lookback).std()
    z = (log_spread - roll_mean) / roll_std.replace(0, pd.NA)
    return z  # positive z => alt outperformed anchor


def with_pair_columns(dfs: dict, alt: str, anchor: str, z: pd.Series) -> dict:
    out = {}
    d_alt = dfs[alt].copy()
    d_alt["pair_signal_z"] = d_alt["open_time"].map(z)        # alt's own signal = +z
    out[alt] = d_alt
    d_anchor = dfs[anchor].copy()
    d_anchor["pair_signal_z"] = d_anchor["open_time"].map(-z)  # anchor's signal = -z (mirror)
    out[anchor] = d_anchor
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, symbols, per_symbol=False):
    strategy = PairsMeanReversionShortStrategy(params)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym in symbols:
        df = dfs[sym]
        result = run_candle_backtest(strategy, risk, df, cfg, symbol=sym, allow_short=True)
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
        n_short = len([t for t in window_trades if t.get("side") == "SHORT"])
        sym_stats[sym] = {"pf": round(spf, 3) if spf not in (None, float("inf")) else spf,
                           "trades": len(window_trades), "n_short": n_short,
                           "ret_pct": round(ret, 4)}

    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (float("inf") if gross_win > 0 else 0.0)
    win_pct = len(wins) / len(all_trades) * 100 if all_trades else 0.0
    avg_ret = sum(rets) / len(rets) if rets else 0.0
    n_short_total = len([t for t in all_trades if t.get("side") == "SHORT"])
    out = {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
           "trades": len(all_trades), "n_short": n_short_total, "avg_ret_pct": round(avg_ret, 4)}
    if per_symbol:
        out["per_symbol"] = sym_stats
    return out


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()  # defaults: 2% SL / 4% TP, never loosened

    results = []
    tf, buffer_days = "1h", 15  # covers max lookback (100 bars * 1h ~4.2d) + safety margin
    lookbacks = [20, 50, 100]
    entry_exit_pairs = [(1.5, 0.3), (2.0, 0.3)]

    for alt in ALTS:
        anchor = ANCHOR
        print(f"\n=== pair {alt}/{anchor} @ {tf} (short-enabled) ===")
        print("Fetching train window...")
        train_raw = await fetch_pair(alt, anchor, TRAIN_START, TRAIN_END, tf, buffer_days)
        print("Fetching test window...")
        test_raw = await fetch_pair(alt, anchor, TEST_START, TEST_END, tf, buffer_days)

        for lookback in lookbacks:
            train_z = build_pair_z(train_raw, alt, anchor, lookback)
            test_z = build_pair_z(test_raw, alt, anchor, lookback)
            train_dfs = with_pair_columns(train_raw, alt, anchor, train_z)
            test_dfs = with_pair_columns(test_raw, alt, anchor, test_z)
            for entry_z, exit_z in entry_exit_pairs:
                params = {"timeframe": tf, "lookback_period": lookback,
                          "entry_z": entry_z, "exit_z": exit_z, "allow_short": True}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk, [alt, anchor])
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk, [alt, anchor],
                                      per_symbol=True)
                label = (f"{tf} pairs_short({alt}/{anchor},lb={lookback},"
                         f"entry_z={entry_z},exit_z={exit_z})")
                clears = (train_m["pf"] is not None and train_m["pf"] > 1.1 and
                          test_m["pf"] is not None and test_m["pf"] > 1.1 and
                          test_m["trades"] >= 30)
                results.append({"label": label, "pair": [alt, anchor], "params": params,
                                 "train": train_m, "test": test_m, "clears_oos_bar": clears})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} (shorts={train_m['n_short']}) ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} (shorts={test_m['n_short']}) ret%={test_m['avg_ret_pct']}"
                      f"{'  <<< CLEARS BAR' if clears else ''}")

    with open("../research/experiments/pairs_mean_reversion_shorts_output.json", "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nWrote pairs_mean_reversion_shorts_output.json ({len(results)} configs)")
    n_clear = sum(1 for r in results if r["clears_oos_bar"])
    print(f"Configs clearing OOS bar (train&test PF>1.1, test trades>=30): {n_clear}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
