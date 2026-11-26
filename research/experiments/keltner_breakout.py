"""Research script (NOT production code): Keltner Channel Breakout, the 11th
mechanically distinct strategy family tested (ATR-adaptive channel around an
EMA midline, entered on a directional BREAKOUT through the band rather than
faded or used as a trailing-stop ratchet).

Per DISTILLED LEARNINGS after Run 115: 10 strategy families are closed
(trend_momentum, mean_reversion, grid, Donchian breakout, Supertrend,
Capitulation Wick Reversal, BB-width squeeze breakout, Price-vs-RSI
divergence, Ichimoku Cloud, VWAP Band Reversion). Keltner Channel Breakout is
mechanically distinct from all of them:
  - vs Donchian breakout: Donchian's channel is the raw N-bar rolling
    high/low (no smoothing, blind to volatility); Keltner's channel is an
    EMA midline +/- ATR*multiplier -- the band width adapts to volatility
    like Supertrend's, but the midline is a smoothed EMA, not hl2, and there
    is no ratchet/trend-flip state machine.
  - vs Supertrend: Supertrend is a continuous trend-following position that
    flips on a stateful ratcheting band (the band can only tighten within a
    trend) and is always in the market in one direction or the other once
    warmed up. Keltner breakout here is a discrete entry/exit: BUY only on a
    fresh breakout above the upper band (close crosses from <= upper to >
    upper), SELL on a decisive reversal back through the EMA midline -- no
    ratchet, no persistent trend flag, and it can sit flat for long stretches
    between breakouts.
  - vs mean_reversion (Bollinger): same EMA+band shape family but the
    opposite trade direction -- Keltner breakout here BUYS the breakout
    (momentum), mean_reversion fades price back toward the mean.
  - vs BB-width squeeze breakout: that strategy used Bollinger Band *width*
    contraction as an entry precondition on top of a separate breakout
    signal; this strategy's entry IS the channel breakout itself, with no
    squeeze precondition.

Long-only (engine has no shorting for this registry strategy): BUY on
close crossing above the upper Keltner band, SELL on close crossing back
below the EMA midline, on top of the unchanged exchange-side 2%/4% SL/TP.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS trades)
on a genuine held-out window, AND survives the 3rd-window check.
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
from app.strategies.indicators import ema
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-06-29", "2026-09-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-09-27", "2026-11-26"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2026-03-31", "2026-06-29"   # 240d-150d ago, 3rd-window check


class KeltnerBreakoutStrategy(Strategy):
    """EMA midline +/- ATR*multiplier channel. BUY on a fresh breakout above
    the upper band, SELL on close crossing back below the EMA midline. All
    computed causally left-to-right (no lookahead: decide() at bar i only
    ever reads columns already populated using data from bars <= i)."""
    id = "keltner_breakout"
    name = "Keltner Channel Breakout"
    description = ("ATR-adaptive channel around an EMA midline. BUY on a "
                    "fresh close-breakout above the upper band, SELL when "
                    "close crosses back below the EMA midline, plus "
                    "unchanged exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("ema_period", "EMA midline period", "int", 20, min=5, max=200),
            ParamSpec("atr_period", "ATR period", "int", 14, min=2, max=100),
            ParamSpec("multiplier", "Band multiplier", "float", 2.0, min=0.5, max=10.0),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["ema_period"], p["atr_period"]) * 3 + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        ema_period, atr_period, mult = p["ema_period"], p["atr_period"], p["multiplier"]

        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / atr_period, adjust=False, min_periods=atr_period).mean()

        mid = ema(df["close"], ema_period)
        out["kc_mid"] = mid
        out["kc_upper"] = mid + mult * atr
        out["kc_lower"] = mid - mult * atr
        out["atr"] = atr
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close, mid, upper = float(row["close"]), row["kc_mid"], row["kc_upper"]
        prev_close, prev_upper = float(prev["close"]), prev["kc_upper"]
        if pd.isna(mid) or pd.isna(upper) or pd.isna(prev_upper):
            return self.hold(symbol, "keltner warming up", price=close)
        state = f"close={close:.6g} mid={mid:.6g} upper={upper:.6g}"

        if position is None:
            fresh_breakout = prev_close <= prev_upper and close > upper
            if fresh_breakout:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"fresh breakout above upper band. {state}", price=close)
            return self.hold(symbol, f"no breakout. {state}", price=close)

        if close < mid:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close back below EMA midline. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = KeltnerBreakoutStrategy(params)
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
    for tf, buffer_days in (("15m", 10), ("1h", 30), ("4h", 90)):
        for ema_period in (20, 50):
            for atr_period in (10, 14):
                for mult in (1.5, 2.0, 2.5):
                    configs.append((tf, buffer_days, ema_period, atr_period, mult))

    cache = {}
    for tf, buffer_days, ema_period, atr_period, mult in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "ema_period": ema_period, "atr_period": atr_period,
                  "multiplier": mult}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} keltner(ema={ema_period},atr={atr_period},mult={mult})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/2ebf8469-0f2c-542d-935b-c7910ff5d780/scratchpad/keltner_breakout_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
