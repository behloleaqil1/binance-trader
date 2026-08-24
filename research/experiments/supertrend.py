"""Research script (NOT production code): Supertrend, a mechanically new
indicator family (5th strategy family tested; ATR-adaptive trailing bands).

Per DISTILLED LEARNINGS after Run 23: the signal axis is closed for
trend_momentum (EMA-cross), mean_reversion (BB/RSI fade), grid (range
ladder), and Donchian breakout (fixed N-period channel breakout) -- four
mechanically distinct families, all rejected/closed. Supertrend is a fifth,
genuinely different construction: unlike trend_momentum's EMA cross (two
lagging moving averages of price alone) or Donchian's fixed-lookback
channel (a hard N-period high/low, blind to volatility), Supertrend's
band width adapts every bar to current ATR, and the trend state is a
single persistent flip-flop (not a crossover of two independent lines) --
band = (high+low)/2 +/- multiplier*ATR, trend flips up when close crosses
above the prior downtrend's upper band, flips down when close crosses
below the prior uptrend's lower band, and the band itself only ever
tightens toward price within a trend (classic "ratchet" property neither
EMA-cross nor Donchian has). Long-only here (engine has no shorting): BUY
on flip-to-uptrend, SELL on flip-to-downtrend, on top of the unchanged
exchange-side 2%/4% SL/TP.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window, AND survives the 3rd-window check.
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

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-21", "2026-06-19"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-19", "2026-08-19"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-21", "2026-03-21"   # 240d-150d ago, 3rd-window check


class SupertrendStrategy(Strategy):
    """Classic Supertrend: basic bands from (high+low)/2 +/- mult*ATR(period),
    then a stateful final-band ratchet (final upper band can only move down
    within a downtrend or when flat->down, final lower band can only move up
    within an uptrend or when flat->up) and a trend flag that flips when
    close crosses the opposite final band. All computed causally left-to-
    right over the full df (no lookahead: bar i's trend/bands only use data
    from bars <= i, and decide() only acts on bar i's own close)."""
    id = "supertrend"
    name = "Supertrend"
    description = ("ATR-adaptive trailing trend bands. BUY when close flips "
                    "the band from downtrend to uptrend, SELL when it flips "
                    "back to downtrend, plus unchanged exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("atr_period", "ATR period", "int", 10, min=2, max=100),
            ParamSpec("multiplier", "Band multiplier", "float", 3.0, min=0.5, max=10.0),
        ]

    def required_history(self) -> int:
        return self.params["atr_period"] * 3 + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        period, mult = p["atr_period"], p["multiplier"]

        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

        hl2 = (df["high"] + df["low"]) / 2.0
        basic_upper = hl2 + mult * atr
        basic_lower = hl2 - mult * atr
        close = df["close"].values
        bu = basic_upper.values
        bl = basic_lower.values
        n = len(df)
        final_upper = [float("nan")] * n
        final_lower = [float("nan")] * n
        trend = [0] * n  # 1 = uptrend, -1 = downtrend, 0 = undefined (warmup)

        for i in range(n):
            if pd.isna(bu[i]) or pd.isna(bl[i]):
                continue
            if i == 0 or trend[i - 1] == 0:
                final_upper[i] = bu[i]
                final_lower[i] = bl[i]
                trend[i] = 1 if close[i] > final_upper[i] else -1 if close[i] < final_lower[i] else 0
                if trend[i] == 0:
                    trend[i] = 1
                continue
            prev_fu, prev_fl = final_upper[i - 1], final_lower[i - 1]
            fu = bu[i] if (bu[i] < prev_fu or close[i - 1] > prev_fu) else prev_fu
            fl = bl[i] if (bl[i] > prev_fl or close[i - 1] < prev_fl) else prev_fl
            final_upper[i] = fu
            final_lower[i] = fl
            if trend[i - 1] == 1:
                trend[i] = -1 if close[i] < fl else 1
            else:
                trend[i] = 1 if close[i] > fu else -1

        out["st_trend"] = trend
        out["st_upper"] = final_upper
        out["st_lower"] = final_lower
        out["atr"] = atr
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close = float(row["close"])
        cur_trend, prev_trend = int(row["st_trend"]), int(prev["st_trend"])
        if cur_trend == 0 or prev_trend == 0:
            return self.hold(symbol, "supertrend warming up", price=close)
        state = f"close={close:.6g} trend={cur_trend} prev_trend={prev_trend}"

        if position is None:
            if prev_trend == -1 and cur_trend == 1:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"flip to uptrend. {state}", price=close)
            return self.hold(symbol, f"no flip-to-uptrend. {state}", price=close)

        if prev_trend == 1 and cur_trend == -1:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"flip to downtrend. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = SupertrendStrategy(params)
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
    configs = [
        ("1h", 20, 10, 2.0),
        ("1h", 20, 10, 3.0),
        ("1h", 20, 14, 2.0),
        ("1h", 20, 14, 3.0),
        ("4h", 60, 10, 2.0),
        ("4h", 60, 10, 3.0),
        ("4h", 60, 14, 2.0),
        ("4h", 60, 14, 3.0),
    ]
    cache = {}
    for tf, buffer_days, atr_period, mult in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "atr_period": atr_period, "multiplier": mult}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} supertrend(atr={atr_period},mult={mult})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/d2d18bc2-c9c6-5653-85c2-4dd2c11ba9ec/scratchpad/supertrend_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
