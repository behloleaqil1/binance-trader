"""Research script (NOT production code): Donchian channel breakout, a
mechanically new strategy family.

Per DISTILLED LEARNINGS after Run 17: all three existing families
(trend_momentum EMA-cross, mean_reversion BB/RSI, grid) are exhausted
across the full TF sweep, and both confirmation-gate mechanisms tried
(same-candle: ADX/volume; cross-TF: MTF direction) are closed too. The
flagged next step is a strategy with a mechanically distinct entry signal
rather than another EMA/RSI/BB recombination. This is a breakout/
volatility-expansion signal (classic Donchian/Turtle system): BUY when
price closes above its own N-period high (momentum WITH the breakout,
the opposite of mean_reversion's fade-the-band-touch logic and unrelated
to trend_momentum's lagging EMA cross). Exit on a close below a shorter
N-period low (trailing breakdown), on top of the unchanged exchange-side
2%/4% SL/TP.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file — only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window.
"""
import asyncio
import math
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


class DonchianBreakoutStrategy(Strategy):
    """BUY when close breaks above the highest HIGH of the prior
    entry_period candles (channel computed on candles strictly before i,
    no lookahead). SELL when close breaks below the lowest LOW of the
    prior exit_period candles (trailing breakdown exit), independent of
    the exchange-side SL/TP which stays at repo defaults."""
    id = "donchian_breakout"
    name = "Donchian Breakout"
    description = ("Buys on a close above its own N-period high (momentum "
                    "WITH the breakout). Exits on a close below a shorter "
                    "N-period low (trailing breakdown), plus unchanged "
                    "exchange-side SL/TP.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("entry_period", "Entry channel period", "int", 20, min=5, max=200),
            ParamSpec("exit_period", "Exit channel period", "int", 10, min=3, max=200),
            ParamSpec("vol_filter", "Require ATR expansion", "bool", False),
            ParamSpec("atr_period", "ATR period", "int", 14, min=2, max=100),
            ParamSpec("atr_avg_period", "ATR rolling-mean period", "int", 50, min=5, max=300),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["entry_period"], p["exit_period"],
                   p["atr_period"] + p["atr_avg_period"]) + 5

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        # shift(1): channel is built from candles strictly before the
        # current one, so the breakout is judged against a channel the
        # current candle could not have contributed to (no lookahead).
        out["donchian_high"] = df["high"].rolling(p["entry_period"]).max().shift(1)
        out["donchian_low"] = df["low"].rolling(p["exit_period"]).min().shift(1)
        prev_close = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / p["atr_period"], adjust=False, min_periods=p["atr_period"]).mean()
        out["atr"] = atr
        out["atr_avg"] = atr.rolling(p["atr_avg_period"]).mean()
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row = df.iloc[i]
        close = float(row["close"])
        dh, dl = row["donchian_high"], row["donchian_low"]
        if pd.isna(dh) or pd.isna(dl):
            return self.hold(symbol, "channel warming up", price=close)
        dh, dl = float(dh), float(dl)
        state = f"close={close:.6g} donHigh{p['entry_period']}={dh:.6g} donLow{p['exit_period']}={dl:.6g}"

        if position is None:
            if close > dh:
                if p["vol_filter"]:
                    atr, atr_avg = row["atr"], row["atr_avg"]
                    if pd.isna(atr) or pd.isna(atr_avg) or float(atr) <= float(atr_avg):
                        return self.hold(symbol, f"breakout but ATR not expanding "
                                         f"(atr={atr}, atr_avg={atr_avg}) — no entry. {state}",
                                         price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"close broke above {p['entry_period']}-period high. {state}",
                              price=close)
            return self.hold(symbol, f"no breakout. {state}", price=close)

        if close < dl:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close broke below {p['exit_period']}-period low — "
                          f"trailing breakdown exit. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = DonchianBreakoutStrategy(params)
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
    for tf, buffer_days in [("1h", 20), ("4h", 60)]:
        print(f"\n=== timeframe {tf} ===")
        print("Fetching train window...")
        train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf, buffer_days)
        print("Fetching test window...")
        test_dfs = await fetch_all(TEST_START, TEST_END, tf, buffer_days)

        entry_exit_pairs = [(20, 10), (55, 20), (40, 20)]
        for entry_p, exit_p in entry_exit_pairs:
            for vol_filter in (False, True):
                params = {"timeframe": tf, "entry_period": entry_p, "exit_period": exit_p,
                          "vol_filter": vol_filter, "atr_period": 14, "atr_avg_period": 50}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
                label = f"{tf} donchian({entry_p}/{exit_p}) vol_filter={vol_filter}"
                results.append({"label": label, "params": params, "train": train_m, "test": test_m})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/0717c991-8ce2-5043-9086-777e44d4ff33/scratchpad/donchian_breakout_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
