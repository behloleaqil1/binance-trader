"""Research script (NOT production code): rolling VWAP band mean-reversion,
a mechanically new (10th) strategy family.

Per DISTILLED LEARNINGS after Run 112: all 9 prior strategy families
(trend_momentum, mean_reversion [BB+RSI], grid, Donchian breakout,
Supertrend, Capitulation Wick Reversal, BB-width squeeze breakout,
Price-vs-RSI Bullish Divergence, Ichimoku Cloud) are closed. Every one of
those bands/levels is computed from PRICE alone. This tests a genuinely
new construction: a rolling VOLUME-WEIGHTED average price (VWAP) with a
deviation band sized from the volume-weighted variance of price around
that VWAP (not a plain price SMA +/- price std like Bollinger). The idea:
VWAP anchors to where volume actually transacted, so a close far below a
high-volume VWAP is a different claim than "price is N std below its own
SMA" (BB) or "price is below a fixed N-period low" (Donchian) — large
low-price volume pulls the anchor down with it, which plain price bands
cannot express. BUY on close crossing below the lower VWAP band (price
cheap relative to where volume has been transacting), exit on reversion to
the VWAP mid-line, plus unchanged exchange-side 2%/4% SL/TP.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file — only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window, and then only re-checked against a
3rd non-overlapping window before being considered for adoption.
"""
import asyncio
import json
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

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

# Anchor = today, 2026-11-24. TRAIN = 150d-60d ago, TEST = 60d-0d ago,
# OLDER = 240d-150d ago (3rd-window check, only used if TEST clears the bar).
ANCHOR = pd.Timestamp("2026-11-24", tz="UTC")
TRAIN_START = (ANCHOR - pd.Timedelta(days=150)).strftime("%Y-%m-%d")
TRAIN_END = (ANCHOR - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
TEST_START = TRAIN_END
TEST_END = ANCHOR.strftime("%Y-%m-%d")
OLDER_START = (ANCHOR - pd.Timedelta(days=240)).strftime("%Y-%m-%d")
OLDER_END = TRAIN_START


class VwapBandReversionStrategy(Strategy):
    """BUY when close crosses below the lower volume-weighted VWAP band
    (price cheap relative to recent volume-weighted average). SELL on
    close back above the VWAP mid-line (reversion exit), independent of
    exchange-side SL/TP."""
    id = "vwap_band_reversion"
    name = "VWAP Band Reversion"
    description = ("Buys when close crosses below a rolling volume-weighted "
                    "VWAP's lower deviation band; exits on reversion back "
                    "above the VWAP mid-line, plus unchanged exchange-side "
                    "SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("vwap_period", "VWAP rolling window", "int", 20, min=5, max=200),
            ParamSpec("band_mult", "Band width (x volume-weighted std)", "float", 2.0, min=0.5, max=4.0),
            ParamSpec("trend_filter_period", "SMA trend filter period (0=off)", "int", 0, min=0, max=400),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["vwap_period"], p["trend_filter_period"]) + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        pv = out["close"] * out["volume"]
        roll_vol = out["volume"].rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum()
        vwap = pv.rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum() / roll_vol
        # volume-weighted variance of price around the rolling vwap
        sq_dev = (out["close"] - vwap) ** 2 * out["volume"]
        var = sq_dev.rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum() / roll_vol
        std = var.clip(lower=0) ** 0.5
        out["vwap"] = vwap
        out["vwap_upper"] = vwap + p["band_mult"] * std
        out["vwap_lower"] = vwap - p["band_mult"] * std
        if p["trend_filter_period"] > 0:
            out["trend_sma"] = out["close"].rolling(p["trend_filter_period"],
                                                      min_periods=p["trend_filter_period"]).mean()
        else:
            out["trend_sma"] = float("nan")
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        close = float(row["close"])
        vwap, lower = row["vwap"], row["vwap_lower"]
        if pd.isna(vwap) or pd.isna(lower):
            return self.hold(symbol, "indicators warming up", price=close)
        vwap, lower = float(vwap), float(lower)
        trend_ok = True
        if p["trend_filter_period"] > 0:
            tsma = row["trend_sma"]
            if pd.isna(tsma):
                return self.hold(symbol, "trend filter warming up", price=close)
            trend_ok = close > float(tsma)
        state = f"close={close:.6g} vwap={vwap:.6g} lower={lower:.6g} trend_ok={trend_ok}"

        if position is None:
            if close < lower and trend_ok:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"close below lower VWAP band, buy the dip. {state}",
                              price=close)
            return self.hold(symbol, f"no entry. {state}", price=close)

        if close > vwap:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close reverted above VWAP mid-line — exit. {state}",
                          price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = VwapBandReversionStrategy(params)
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
    for tf, buffer_days in [("15m", 5), ("1h", 15), ("4h", 40)]:
        print(f"\n=== timeframe {tf} ===")
        print("Fetching train window...")
        train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
        print("Fetching test window...")
        test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)

        for vwap_period in (20, 50):
            for band_mult in (1.5, 2.0, 2.5):
                for trend_filter_period in (0, 100):
                    params = {"timeframe": tf, "vwap_period": vwap_period,
                              "band_mult": band_mult, "trend_filter_period": trend_filter_period}
                    train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
                    test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
                    label = (f"{tf} vwap_period={vwap_period} band_mult={band_mult} "
                             f"trend_filter={trend_filter_period}")
                    results.append({"label": label, "params": params, "train": train_m, "test": test_m})
                    print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                          f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                          f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                          f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/40f2080f-6b60-5a8b-a158-9c0d1a43e69c/scratchpad/vwap_band_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "train_window": [TRAIN_START, TRAIN_END],
                    "test_window": [TEST_START, TEST_END],
                    "older_window": [OLDER_START, OLDER_END]}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
