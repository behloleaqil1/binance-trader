"""Research script (NOT production code): Bollinger Band Width (BBW)
volatility-squeeze breakout, a mechanically new (7th) strategy family.

Per DISTILLED LEARNINGS after Run 31: all 6 prior strategy families
(trend_momentum, mean_reversion, grid, Donchian breakout, Supertrend,
Capitulation Wick Reversal) and all signal-source categories tried so far
(price level/band, moving-average cross, price shape, volume/cross-symbol,
calendar/session-time) are closed. This tests a genuinely new construction:
volatility CONTRACTION as a precondition for a breakout entry (the "TTM
squeeze" idea) — not just a breakout (Donchian, Run 18: fixed N-period
channel, no volatility precondition) and not an ATR-trailing-band flip
(Supertrend, Run 24). The BB width (upper-lower)/middle is tracked over its
own rolling history; a "squeeze" is when width sits in its own lowest
percentile (volatility compressed, mechanically distinct from ATR magnitude
— width also encodes *mean reversion of price toward the band*, not just
raw range). BUY only when a squeeze occurred within a short recent lookback
AND close breaks above the upper band (compression -> expansion, WITH the
breakout — momentum, not mean_reversion's fade-the-touch). Exit on close
back below the middle band (reversion), plus unchanged exchange-side 2%/4%
SL/TP.

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

# Same anchor as Run 32 (today = 2026-08-28) so results are directly
# comparable to every recent run's windows.
TRAIN_START, TRAIN_END = "2026-03-31", "2026-06-29"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-29", "2026-08-28"     # 60d-0d ago
OLDER_START, OLDER_END = "2025-12-31", "2026-03-31"   # 240d-150d ago, 3rd-window check


class BBSqueezeBreakoutStrategy(Strategy):
    """BUY when BB width was in its own lowest `squeeze_pct` percentile
    (over a trailing `squeeze_lookback` window) at any point in the last
    `squeeze_recency` candles, AND the current close breaks above the
    upper band. SELL on close back below the middle band (mean-reversion
    exit of the expansion move), independent of exchange-side SL/TP."""
    id = "bb_squeeze_breakout"
    name = "BB Squeeze Breakout"
    description = ("Buys on a volatility expansion (close above upper BB) "
                    "that follows a recent volatility contraction (BB width "
                    "in its own low percentile). Exits on close back below "
                    "the middle band, plus unchanged exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("bb_period", "BB period", "int", 20, min=5, max=200),
            ParamSpec("bb_std", "BB std devs", "float", 2.0, min=0.5, max=4.0),
            ParamSpec("squeeze_lookback", "Width-percentile lookback", "int", 100, min=20, max=500),
            ParamSpec("squeeze_pct", "Squeeze percentile threshold", "float", 20.0, min=1.0, max=90.0),
            ParamSpec("squeeze_recency", "Squeeze recency window (candles)", "int", 3, min=1, max=50),
            ParamSpec("require_squeeze", "Require prior squeeze (else plain BB breakout)", "bool", True),
        ]

    def required_history(self) -> int:
        p = self.params
        return p["bb_period"] + p["squeeze_lookback"] + p["squeeze_recency"] + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        mid = out["close"].rolling(p["bb_period"], min_periods=p["bb_period"]).mean()
        std = out["close"].rolling(p["bb_period"], min_periods=p["bb_period"]).std(ddof=0)
        upper = mid + p["bb_std"] * std
        lower = mid - p["bb_std"] * std
        width = (upper - lower) / mid
        out["bb_mid"] = mid
        out["bb_upper"] = upper
        out["bb_lower"] = lower
        out["bb_width"] = width
        # percentile rank of *today's* width within its own trailing window,
        # computed on width values strictly up to and including i (no
        # lookahead — each row's rank only ever looks backward at itself).
        out["width_pct_rank"] = width.rolling(p["squeeze_lookback"], min_periods=p["squeeze_lookback"]) \
            .apply(lambda w: (w <= w.iloc[-1]).mean() * 100, raw=False)
        was_squeeze = out["width_pct_rank"] <= p["squeeze_pct"]
        out["squeeze_recent"] = was_squeeze.rolling(p["squeeze_recency"], min_periods=1).max().astype(bool)
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        row = df.iloc[i]
        close = float(row["close"])
        upper, mid = row["bb_upper"], row["bb_mid"]
        if pd.isna(upper) or pd.isna(mid) or pd.isna(row["width_pct_rank"]):
            return self.hold(symbol, "indicators warming up", price=close)
        upper, mid = float(upper), float(mid)
        squeeze_recent = bool(row["squeeze_recent"])
        state = f"close={close:.6g} upper={upper:.6g} mid={mid:.6g} squeeze_recent={squeeze_recent}"

        if position is None:
            breakout = close > upper
            if breakout and (squeeze_recent or not p["require_squeeze"]):
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"breakout above upper band, squeeze precondition "
                              f"{'met' if squeeze_recent else 'not required'}. {state}",
                              price=close)
            return self.hold(symbol, f"no qualifying breakout. {state}", price=close)

        if close < mid:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close back below middle band — reversion exit. {state}",
                          price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = BBSqueezeBreakoutStrategy(params)
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
    for tf, buffer_days in [("1h", 15), ("4h", 40)]:
        print(f"\n=== timeframe {tf} ===")
        print("Fetching train window...")
        train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
        print("Fetching test window...")
        test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)

        for squeeze_pct in (10.0, 20.0, 30.0):
            for require_squeeze in (True, False):
                params = {"timeframe": tf, "bb_period": 20, "bb_std": 2.0,
                          "squeeze_lookback": 100, "squeeze_pct": squeeze_pct,
                          "squeeze_recency": 3, "require_squeeze": require_squeeze}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
                label = f"{tf} squeeze_pct={squeeze_pct} require_squeeze={require_squeeze}"
                results.append({"label": label, "params": params, "train": train_m, "test": test_m})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/05707945-55c5-5340-ae9f-c9422496f094/scratchpad/bb_squeeze_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
