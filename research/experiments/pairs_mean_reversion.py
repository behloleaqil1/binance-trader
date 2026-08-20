"""Research script (NOT production code): cross-symbol pairs / relative-
value mean reversion, Run 20's new hypothesis.

Per DISTILLED LEARNINGS after Run 19, flagged next step (b): the one
cross-symbol construction tried so far (rs_rotation, Run 19) is a *momentum*
bet — buy the leader, ranked across all 8 symbols — and it failed, closing
with the diagnosis that 8 symbols may be too few to separate real relative
strength from single-name noise in a rank-based construction. The suggested
alternative is a *materially different construction*: pairs/spread trading
between two correlated symbols, rather than ranking 8 symbols at once.

This script does the mirror-image bet to rs_rotation: instead of buying the
cross-sectional LEADER (momentum), it buys the LAGGARD within a single pair
whenever the pair's price ratio has stretched away from its rolling mean
(mean reversion of *relative* performance, not of a symbol's own absolute
price/RSI/BB the way mean_reversion.py already tested and failed). This is
mechanically distinct from every prior signal in this programme: it is
neither a momentum bet (trend_momentum, Donchian, rs_rotation) nor a
same-symbol range/oscillator fade (mean_reversion, grid) — it is a
convergence bet on the *relationship between two symbols*.

Mechanics: for a pair (A, B), compute the rolling z-score of
spread = log(close_A) - log(close_B) over `lookback` bars (causal, no
lookahead — z at row i only uses spread up to and including row i). Define
each symbol's own "underperformance" score relative to its pair partner:
underperf_A = -z, underperf_B = +z (positive = this symbol has lagged its
partner by that many std devs). BUY when underperf > entry_z (this symbol
is the laggard, betting on catch-up). SELL (exit) when underperf drops
below exit_z (spread has reverted toward its rolling mean). Because this
engine is spot/long-only (no shorting — confirmed: no SHORT signal action
or short-side logic anywhere in app/core/types.py, app/backtest/simulator.py,
or app/risk/models.py), this is a real-money-implementable proxy for the
relative-value thesis, not a market-neutral spread trade — same
simplification rs_rotation.py already made buying the cross-sectional
leader outright rather than a neutral long/short book. Basis risk is
explicit and disclosed: if both legs fall together while the ratio still
reverts, the long spot leg can still lose money. Unchanged exchange-side
2%/4% SL/TP, same fee/slippage assumptions and train/test/older-window
anti-noise methodology as every prior run.

Pair selection is principled, not data-mined: every altcoin in the
programme's 8-symbol universe paired against BTC (the natural crypto market
anchor), fixed before any threshold/lookback tuning — not chosen by
searching for the highest in-sample correlation.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file — only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window.
"""
import asyncio
import sys
sys.path.insert(0, ".")

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
PAIRS = [(alt, ANCHOR) for alt in ALTS]  # (laggard-candidate, anchor)
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-23", "2026-06-21"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-21", "2026-08-20"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-23", "2026-03-23"   # 240d-150d ago, 3rd-window check


class PairsMeanReversionStrategy(Strategy):
    """BUY this symbol when it has underperformed its pair partner by more
    than entry_z rolling std devs (betting on relative catch-up). SELL once
    the underperformance shrinks back below exit_z (spread reverted toward
    its rolling mean). pair_underperf column must already be present on df
    (merged in by the caller — see build_pair_frame below) since the
    z-score needs both symbols in the pair, not just this symbol's own
    history."""
    id = "pairs_mean_reversion"
    name = "Pairs Mean Reversion"
    description = ("Cross-symbol relative-value: buy this symbol when it "
                    "has lagged its pair partner by entry_z std devs, exit "
                    "once the gap closes back below exit_z.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("lookback_period", "Spread z-score lookback (bars)", "int", 50, min=10, max=300),
            ParamSpec("entry_z", "Enter when underperformance >", "float", 1.5, min=0.5, max=4.0),
            ParamSpec("exit_z", "Exit when underperformance <", "float", 0.3, min=-2.0, max=3.0),
        ]

    def required_history(self) -> int:
        return self.params["lookback_period"] + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        return df  # pair_underperf already merged in by the caller

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        u = row.get("pair_underperf")
        close = float(row["close"])
        if pd.isna(u):
            return self.hold(symbol, "spread z-score warming up", price=close)
        state = f"close={close:.6g} underperf_z={u:.3f}"

        if position is None:
            if u > p["entry_z"]:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"lagged pair partner by {u:.2f} std devs, entering. {state}",
                              price=close)
            return self.hold(symbol, f"not lagging enough. {state}", price=close)

        if u < p["exit_z"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"spread reverted below exit threshold {p['exit_z']}. {state}",
                          price=close)
        return self.hold(symbol, f"still lagging, holding for reversion. {state}", price=close)


async def fetch_pair(alt, anchor, start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    df_alt = await fetch_klines(f"{alt}USDT", tf, buf_start, end)
    df_anchor = await fetch_klines(f"{anchor}USDT", tf, buf_start, end)
    return {alt: df_alt, anchor: df_anchor}


def build_pair_frame(dfs: dict, alt: str, anchor: str, lookback: int):
    """Causal rolling z-score of spread = log(close_alt) - log(close_anchor),
    indexed by open_time. Row i only uses spread values up to and including
    row i (rolling().mean()/.std() are backward-looking by construction, no
    lookahead)."""
    closes = pd.DataFrame({
        alt: dfs[alt].set_index("open_time")["close"],
        anchor: dfs[anchor].set_index("open_time")["close"],
    }).sort_index()
    import numpy as np
    log_spread = np.log(closes[alt]) - np.log(closes[anchor])
    roll_mean = log_spread.rolling(lookback).mean()
    roll_std = log_spread.rolling(lookback).std()
    z = (log_spread - roll_mean) / roll_std.replace(0, pd.NA)
    return z  # positive z => alt outperformed anchor => anchor is the laggard


def with_pair_columns(dfs: dict, alt: str, anchor: str, z: pd.Series) -> dict:
    out = {}
    d_alt = dfs[alt].copy()
    d_alt["pair_underperf"] = d_alt["open_time"].map(-z)   # alt laggard when z very negative
    out[alt] = d_alt
    d_anchor = dfs[anchor].copy()
    d_anchor["pair_underperf"] = d_anchor["open_time"].map(z)  # anchor laggard when z very positive
    out[anchor] = d_anchor
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, symbols, per_symbol=False):
    strategy = PairsMeanReversionStrategy(params)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym in symbols:
        df = dfs[sym]
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


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()

    results = []
    tf, buffer_days = "1h", 15  # covers max lookback (100 bars * 1h ~4.2d) + safety margin
    lookbacks = [20, 50, 100]
    entry_exit_pairs = [(1.5, 0.3), (2.0, 0.3)]

    for alt in ALTS:
        anchor = ANCHOR
        print(f"\n=== pair {alt}/{anchor} @ {tf} ===")
        print("Fetching train window...")
        train_raw = await fetch_pair(alt, anchor, TRAIN_START, TRAIN_END, tf, buffer_days)
        print("Fetching test window...")
        test_raw = await fetch_pair(alt, anchor, TEST_START, TEST_END, tf, buffer_days)

        for lookback in lookbacks:
            train_z = build_pair_frame(train_raw, alt, anchor, lookback)
            test_z = build_pair_frame(test_raw, alt, anchor, lookback)
            train_dfs = with_pair_columns(train_raw, alt, anchor, train_z)
            test_dfs = with_pair_columns(test_raw, alt, anchor, test_z)
            for entry_z, exit_z in entry_exit_pairs:
                params = {"timeframe": tf, "lookback_period": lookback,
                          "entry_z": entry_z, "exit_z": exit_z}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk, [alt, anchor])
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk, [alt, anchor])
                label = (f"{tf} pairs({alt}/{anchor},lb={lookback},"
                         f"entry_z={entry_z},exit_z={exit_z})")
                results.append({"label": label, "pair": [alt, anchor], "params": params,
                                 "train": train_m, "test": test_m})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/4a86a216-b3a4-5ea2-8243-da3fc3de56b6/scratchpad/pairs_mr_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
