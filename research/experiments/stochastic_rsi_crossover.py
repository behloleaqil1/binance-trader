"""Research script (NOT production code): Stochastic RSI %K/%D Crossover, the
12th mechanically distinct strategy family tested.

Per DISTILLED LEARNINGS after Run 116: 11 strategy families are closed
(trend_momentum, mean_reversion, grid, Donchian breakout, Supertrend,
Capitulation Wick Reversal, BB-width squeeze breakout, Price-vs-RSI
divergence, Ichimoku Cloud, VWAP Band Reversion, Keltner Channel Breakout).
Stochastic RSI crossover is mechanically distinct from all of them:
  - vs trend_momentum: trend_momentum uses raw RSI as a static *threshold*
    filter (RSI < X / > Y) alongside an unrelated EMA-cross + MACD entry.
    This strategy applies a stochastic-oscillator transform ON TOP OF RSI
    (min-max normalizing RSI over a rolling window into a 0-100 %K line,
    then smoothing into %K/%D), and the entry signal is a %K/%D LINE
    CROSSOVER inside an extreme zone -- a second-order derivative of RSI,
    not a threshold on RSI itself, and there is no EMA/MACD component at
    all.
  - vs Price-vs-RSI Bullish Divergence: that strategy compares the SHAPE of
    price swing-lows against RSI swing-lows (price making a lower low while
    RSI makes a higher low) -- a multi-bar structural comparison. This
    strategy has no concept of price structure at all; it only crosses two
    lines derived purely from RSI's own history.
  - vs Ichimoku/Keltner/Donchian/Supertrend/VWAP-band/Bollinger: none of
    those touch RSI; they are all price/volatility-band constructions. This
    is a pure momentum-oscillator construction with no price band at all.

Entry: %K crosses above %D while %K was below `oversold` (classic StochRSI
bullish crossover in the oversold zone). Exit: %K crosses below %D while
%K was above `overbought` (bearish crossover in the overbought zone), OR a
simple midline exit variant (close below 50) is swept separately via the
`exit_mode` param. Long-only (engine has no shorting for this registry
strategy). Exchange-side 2%/4% SL/TP unchanged throughout.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS trades)
on a genuine held-out window, AND survives a 3rd-window check.
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
from app.strategies.indicators import rsi
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-06-29", "2026-09-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-09-27", "2026-11-26"     # 60d-0d ago (today's anchor)


class StochRsiCrossoverStrategy(Strategy):
    """Stochastic RSI: min-max normalize RSI over `stoch_period` bars into a
    raw 0-100 line, SMA-smooth by `k_smooth` into %K, SMA-smooth %K by
    `d_smooth` into %D. BUY on a %K/%D bullish crossover while %K was below
    `oversold` just before the cross. SELL on a %K/%D bearish crossover
    while %K was above `overbought`. All computed causally left-to-right
    (no lookahead: decide() at bar i only ever reads columns already
    populated using data from bars <= i)."""
    id = "stoch_rsi_crossover"
    name = "Stochastic RSI Crossover"
    description = ("Stochastic oscillator applied to RSI. BUY on a %K/%D "
                    "bullish crossover from the oversold zone, SELL on a "
                    "bearish crossover from the overbought zone, plus "
                    "unchanged exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("rsi_period", "RSI period", "int", 14, min=2, max=100),
            ParamSpec("stoch_period", "Stochastic lookback", "int", 14, min=2, max=100),
            ParamSpec("k_smooth", "%K smoothing", "int", 3, min=1, max=20),
            ParamSpec("d_smooth", "%D smoothing", "int", 3, min=1, max=20),
            ParamSpec("oversold", "Oversold zone", "float", 20.0, min=0.0, max=50.0),
            ParamSpec("overbought", "Overbought zone", "float", 80.0, min=50.0, max=100.0),
        ]

    def required_history(self) -> int:
        p = self.params
        return p["rsi_period"] + p["stoch_period"] + p["k_smooth"] + p["d_smooth"] + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        rsi_period, stoch_period = p["rsi_period"], p["stoch_period"]
        k_smooth, d_smooth = p["k_smooth"], p["d_smooth"]

        r = rsi(df["close"], rsi_period)
        roll_min = r.rolling(stoch_period, min_periods=stoch_period).min()
        roll_max = r.rolling(stoch_period, min_periods=stoch_period).max()
        span = (roll_max - roll_min).replace(0.0, float("nan"))
        stoch_raw = ((r - roll_min) / span * 100.0).clip(0, 100)

        k = stoch_raw.rolling(k_smooth, min_periods=k_smooth).mean()
        d = k.rolling(d_smooth, min_periods=d_smooth).mean()
        out["stoch_k"] = k
        out["stoch_d"] = d
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        if i < 1:
            return self.hold(symbol, "not enough candles")
        p = self.params
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close = float(row["close"])
        k, d = row["stoch_k"], row["stoch_d"]
        prev_k, prev_d = prev["stoch_k"], prev["stoch_d"]
        if pd.isna(k) or pd.isna(d) or pd.isna(prev_k) or pd.isna(prev_d):
            return self.hold(symbol, "stoch rsi warming up", price=close)
        state = f"close={close:.6g} k={k:.4g} d={d:.4g}"

        bullish_cross = prev_k <= prev_d and k > d
        bearish_cross = prev_k >= prev_d and k < d

        if position is None:
            if bullish_cross and prev_k < p["oversold"]:
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"bullish %K/%D cross from oversold. {state}", price=close)
            return self.hold(symbol, f"no entry cross. {state}", price=close)

        if bearish_cross and prev_k > p["overbought"]:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"bearish %K/%D cross from overbought. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = StochRsiCrossoverStrategy(params)
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
        for rsi_period in (14,):
            for stoch_period in (14, 21):
                for zones in ((20.0, 80.0), (25.0, 75.0)):
                    configs.append((tf, buffer_days, rsi_period, stoch_period, zones[0], zones[1]))

    cache = {}
    for tf, buffer_days, rsi_period, stoch_period, oversold, overbought in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "rsi_period": rsi_period, "stoch_period": stoch_period,
                  "k_smooth": 3, "d_smooth": 3, "oversold": oversold, "overbought": overbought}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = (f"{tf} stochrsi(rsi={rsi_period},stoch={stoch_period},"
                 f"zones={oversold}/{overbought})")
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/28f5594d-6129-5517-a7bf-1ab0a33853d9/scratchpad/stochastic_rsi_crossover_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
