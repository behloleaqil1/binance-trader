"""Research script (NOT production code): Capitulation Wick Reversal, a 6th
strategy family and the first candlestick-SHAPE-derived signal tested in this
programme.

Per DISTILLED LEARNINGS after Run 26: every signal tested so far (5 strategy
families, 3 confirmation gates, 2 cross-symbol constructions) is derived from
either a moving-average relationship (EMA cross, Supertrend band, MTF
direction), a band/threshold touch (Bollinger, RSI, ADX), a fixed price
channel (Donchian), relative volume level, or cross-sectional rank. None of
them look at a single candle's own OHLC *shape* (the ratio of body to wick)
or that candle's volume in combination -- the classic "hammer" / "capitulation
candle" pattern used in discretionary technical analysis: a candle with a long
lower wick (price was sold off hard intra-candle, then bought back up before
close) on above-average volume (real participation, not a thin wick), closing
green (the reversal already visible in the same candle). This is mechanically
distinct from every prior construction: it is a single-candle pattern signal,
not a multi-bar indicator relationship, and it's the first signal here to use
the high/low/open/close shape of one candle rather than a derived series.

Entry (long-only, spot): on candle i with range = high-low > 0,
  lower_wick_ratio = (min(open,close) - low) / range >= wick_ratio
  AND close > open (bullish close within the candle)
  AND volume >= vol_mult * rolling_mean(volume, vol_lookback)  [capitulation
      needs real participation, not a thin/illiquid wick]
Exit: revert-to-mean target, close >= SMA(exit_period) of close (the same
"reversion" thesis mean_reversion's exit_at="middle" uses, just a plain SMA
here since there's no Bollinger band computed) -- on top of the unchanged
exchange-side 2%/4% SL/TP (never loosened).

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS trades)
on a genuine held-out window, AND survives the 3rd-window + per-symbol check.
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
from app.strategies.indicators import sma
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-28", "2026-06-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-27", "2026-08-25"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-28", "2026-03-28"   # 240d-150d ago, 3rd-window check


class WickReversalStrategy(Strategy):
    id = "wick_reversal"
    name = "Capitulation Wick Reversal"
    description = ("Buys on a single candle with a long lower wick (>= wick_ratio of "
                    "its range), a bullish (green) close, and above-average volume -- "
                    "a capitulation-and-bounce pattern. Exits on reversion to a short "
                    "SMA, plus unchanged exchange-side SL/TP. Long-only (spot).")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("wick_ratio", "Min lower-wick fraction of range", "float", 0.6,
                      min=0.1, max=0.95),
            ParamSpec("vol_mult", "Entry volume vs rolling mean", "float", 1.5,
                      min=1.0, max=5.0),
            ParamSpec("vol_lookback", "Volume rolling-mean window", "int", 20, min=5, max=200),
            ParamSpec("exit_period", "Exit SMA period", "int", 10, min=3, max=100),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["vol_lookback"], p["exit_period"]) + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        rng = df["high"] - df["low"]
        lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
        out["lower_wick_ratio"] = (lower_wick / rng).where(rng > 0)
        out["vol_sma"] = df["volume"].rolling(p["vol_lookback"], min_periods=p["vol_lookback"]).mean()
        out["exit_sma"] = sma(df["close"], p["exit_period"])
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        close, open_, volume = float(row["close"]), float(row["open"]), float(row["volume"])
        lwr, vol_sma, exit_sma = row["lower_wick_ratio"], row["vol_sma"], row["exit_sma"]
        if pd.isna(vol_sma) or pd.isna(exit_sma):
            return self.hold(symbol, "indicators warming up")

        if position is None:
            if pd.isna(lwr):
                return self.hold(symbol, "zero-range candle, no setup", price=close)
            lwr = float(lwr)
            is_capitulation = (lwr >= p["wick_ratio"] and close > open_
                                and volume >= p["vol_mult"] * float(vol_sma))
            state = (f"close={close:.6g} lower_wick_ratio={lwr:.3f} "
                     f"vol={volume:.4g} vol_sma={float(vol_sma):.4g}")
            if is_capitulation:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"capitulation wick + bullish close + volume spike. {state}",
                              price=close)
            return self.hold(symbol, f"no capitulation setup. {state}", price=close)

        exit_sma = float(exit_sma)
        if close >= exit_sma:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close {close:.6g} reverted to SMA{p['exit_period']} "
                          f"({exit_sma:.6g}) — take reversion profit.", price=close)
        return self.hold(symbol, f"holding, waiting for reversion to {exit_sma:.6g}.",
                         price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = WickReversalStrategy(params)
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


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()

    results = []
    configs = []
    for tf, buffer_days in [("1h", 10), ("4h", 30)]:
        for wick_ratio in (0.5, 0.6, 0.7):
            for vol_mult in (1.5, 2.0):
                configs.append((tf, buffer_days, wick_ratio, vol_mult))

    cache = {}
    for tf, buffer_days, wick_ratio, vol_mult in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "wick_ratio": wick_ratio, "vol_mult": vol_mult,
                  "vol_lookback": 20, "exit_period": 10}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} wick_reversal(wick_ratio={wick_ratio},vol_mult={vol_mult})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # Any config clearing BOTH sides of the OOS bar (train pf>1.1 AND test
    # pf>1.1 AND test n>=30) gets a 3rd non-overlapping window + per-symbol check.
    survivors = [r for r in results
                 if r["train"]["pf"] is not None and r["train"]["pf"] > 1.1
                 and r["test"]["pf"] is not None and r["test"]["pf"] > 1.1
                 and r["test"]["trades"] >= 30]
    print(f"\n{len(survivors)} config(s) clear both sides of the OOS bar.")
    older_checks = []
    if survivors:
        older_cache = {}
        for r in survivors:
            tf = r["params"]["timeframe"]
            buffer_days = 10 if tf == "1h" else 30
            if tf not in older_cache:
                print(f"Fetching OLDER window for {tf}...")
                older_cache[tf] = await fetch_all(OLDER_START, OLDER_END, tf, buffer_days)
            older_dfs = older_cache[tf]
            older_m = eval_window(older_dfs, OLDER_START, OLDER_END, r["params"], risk,
                                   per_symbol=True)
            train_ps = eval_window(cache[tf][0], TRAIN_START, TRAIN_END, r["params"], risk,
                                    per_symbol=True)
            test_ps = eval_window(cache[tf][1], TEST_START, TEST_END, r["params"], risk,
                                   per_symbol=True)
            print(f"{r['label']} OLDER window: pf={older_m['pf']} win%={older_m['win_pct']} "
                  f"n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            older_checks.append({"label": r["label"], "older": older_m,
                                  "train_per_symbol": train_ps["per_symbol"],
                                  "test_per_symbol": test_ps["per_symbol"],
                                  "older_per_symbol": older_m["per_symbol"]})

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/b8ac67f5-5603-5b0c-8935-8b49de2d70c7/scratchpad/wick_reversal_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "older_checks": older_checks}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
