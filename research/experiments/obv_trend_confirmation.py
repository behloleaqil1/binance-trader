"""Research script (NOT production code): On-Balance Volume (OBV) Trend
Confirmation, the 14th mechanically distinct strategy family tested.

Per DISTILLED LEARNINGS after Run 120: 13 strategy families are closed
(trend_momentum, mean_reversion, grid, Donchian breakout, Supertrend,
Capitulation Wick Reversal, BB-width squeeze breakout, Price-vs-RSI
divergence, Ichimoku Cloud, VWAP Band Reversion, Keltner Channel Breakout,
Stochastic RSI Crossover, Parabolic SAR Stop-and-Reverse). OBV is
mechanically distinct from all of them:
  - vs every price/volatility-band family (Bollinger/Keltner/VWAP-band/
    Donchian/Supertrend/Ichimoku/Parabolic SAR): none of those touch
    volume at all. OBV is a pure volume-flow line: cumulative sum of
    +volume on up-closes and -volume on down-closes, with no price band
    or price-extreme concept whatsoever.
  - vs the already-closed "relative-volume gate" (Run ~ in DISTILLED
    LEARNINGS "gates" section): that gate applies a raw, memoryless
    volume *ratio* (current volume vs its own rolling average) as a
    filter bolted onto a separate price signal. OBV is a *cumulative*,
    *directional*, path-dependent running total with its own multi-bar
    memory, used here as the PRIMARY entry signal via a line/MA
    crossover, not a instantaneous magnitude gate on someone else's
    signal.
  - vs momentum rotation / pairs mean-reversion (cross-symbol category):
    those rank or compare PRICE RETURNS across symbols. OBV never looks
    at price momentum directly, only the sign of each bar's close-over-
    close move combined with that bar's traded volume.
  - vs trend_momentum/mean_reversion/Stochastic RSI/RSI-divergence: none
    of those incorporate volume into the signal construction at all.

Entry: BUY when OBV crosses above its own `obv_ma_period`-bar SMA (volume
flow turning net-bullish), optionally gated by requiring close > its own
`trend_filter_period`-bar SMA (price-trend confirmation, swept on/off).
Exit: SELL when OBV crosses back below its MA. Long-only (engine has no
shorting for this registry strategy). Exchange-side 2%/4% SL/TP unchanged
throughout -- never loosened.

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
from app.strategies.indicators import sma
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-06-30", "2026-09-28"   # 150d-60d ago
TEST_START, TEST_END = "2026-09-28", "2026-11-27"     # 60d-0d ago (today's anchor)


class ObvTrendConfirmStrategy(Strategy):
    """On-Balance Volume: cumsum(sign(close.diff()) * volume), causally
    computed. BUY on an OBV/OBV-MA bullish crossover (optionally gated by
    close > price-trend SMA). SELL on the mirror bearish crossover. All
    columns populated using only data from bars <= i (no lookahead)."""
    id = "obv_trend_confirm"
    name = "OBV Trend Confirmation"
    description = ("On-Balance Volume line crossing its own moving average "
                    "as a volume-flow entry/exit signal, optionally gated "
                    "by a price-trend SMA filter, plus unchanged "
                    "exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("obv_ma_period", "OBV MA period", "int", 20, min=2, max=200),
            ParamSpec("use_trend_filter", "Require price trend confirmation", "bool", False),
            ParamSpec("trend_filter_period", "Price trend SMA period", "int", 50, min=2, max=300),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["obv_ma_period"], p["trend_filter_period"]) + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        close = df["close"]
        direction = close.diff().apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
        direction.iloc[0] = 0.0
        obv = (direction * df["volume"]).cumsum()
        out["obv"] = obv
        out["obv_ma"] = sma(obv, p["obv_ma_period"])
        out["price_trend_sma"] = sma(close, p["trend_filter_period"])
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        if i < 1:
            return self.hold(symbol, "not enough candles")
        p = self.params
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close = float(row["close"])
        obv, obv_ma = row["obv"], row["obv_ma"]
        prev_obv, prev_obv_ma = prev["obv"], prev["obv_ma"]
        if pd.isna(obv_ma) or pd.isna(prev_obv_ma):
            return self.hold(symbol, "obv warming up", price=close)
        state = f"close={close:.6g} obv={obv:.4g} obv_ma={obv_ma:.4g}"

        bullish_cross = prev_obv <= prev_obv_ma and obv > obv_ma
        bearish_cross = prev_obv >= prev_obv_ma and obv < obv_ma

        if position is None:
            if bullish_cross:
                if p["use_trend_filter"]:
                    trend_sma = row["price_trend_sma"]
                    if pd.isna(trend_sma) or close <= trend_sma:
                        return self.hold(symbol, f"bullish OBV cross but trend filter fails. {state}", price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"bullish OBV/MA cross. {state}", price=close)
            return self.hold(symbol, f"no entry cross. {state}", price=close)

        if bearish_cross:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"bearish OBV/MA cross. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = ObvTrendConfirmStrategy(params)
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
        for obv_ma_period in (14, 20, 30):
            for use_trend_filter in (False, True):
                configs.append((tf, buffer_days, obv_ma_period, use_trend_filter))

    cache = {}
    for tf, buffer_days, obv_ma_period, use_trend_filter in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
            test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "obv_ma_period": obv_ma_period,
                  "use_trend_filter": use_trend_filter, "trend_filter_period": 50}
        train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
        test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
        label = f"{tf} obv_ma={obv_ma_period} trend_filter={use_trend_filter}"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/c266be5b-7a31-5fc6-98ac-557f4a48a65f/scratchpad/obv_trend_confirmation_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
