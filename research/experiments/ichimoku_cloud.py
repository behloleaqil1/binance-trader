"""Research script (NOT production code): Ichimoku Cloud, a mechanically new
indicator family (9th strategy family tested overall; first "multi-line
confluence" construction).

Per DISTILLED LEARNINGS (Run 111 snapshot): every concretely-scoped
strategy/signal/gate/cross-symbol/non-signal-lever/scope axis tried so far
is closed -- trend_momentum (EMA cross), mean_reversion (BB/RSI fade), grid,
Donchian breakout, Supertrend (ATR trailing band), Capitulation Wick
Reversal, BB-width squeeze breakout, Price-vs-RSI divergence. Ichimoku is a
genuinely different construction from all eight: it combines THREE lines
derived from rolling high/low midpoints at three different lookbacks
(Tenkan 9, Kijun 26, Senkou B 52 by default) into a forward-projected
"cloud" band, with the entry signal requiring both a Tenkan/Kijun cross AND
price position relative to that cloud -- unlike Supertrend's single
ATR-adaptive line or trend_momentum's two-EMA cross, this is a 3-lookback
multi-line confluence filter, and unlike the already-closed gates (ADX,
relative-volume, MTF, session-time) the filter line (the cloud) is itself
forward-shifted in time, not a same-bar confirmation.

No lookahead: Senkou Span A/B are computed from data up to bar (t -
kijun_period) and then shifted FORWARD by kijun_period bars via
pandas .shift(kijun_period) -- i.e. the cloud value visible at bar t was
knowable kijun_period bars ago. decide() only reads row i and i-1.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file -- only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window, AND survives the 3rd-window check.
"""
import asyncio
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone

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

TODAY = datetime(2026, 11, 24, tzinfo=timezone.utc)
TEST_END = TODAY
TEST_START = TODAY - timedelta(days=60)
TRAIN_END = TEST_START
TRAIN_START = TODAY - timedelta(days=150)
OLDER_END = TRAIN_START
OLDER_START = TODAY - timedelta(days=240)


def _d(dt: datetime) -> str:
    return dt.date().isoformat()


class IchimokuCloudStrategy(Strategy):
    id = "ichimoku_cloud"
    name = "Ichimoku Cloud"
    description = ("Tenkan/Kijun cross entry, optionally filtered by price "
                    "position relative to the forward-projected Senkou cloud. "
                    "Exits on opposite cross or (if filtered) a close back "
                    "inside/below the cloud. Long-only; exchange-side SL/TP "
                    "unchanged.")

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("tenkan_period", "Tenkan period", "int", 9, min=2, max=100),
            ParamSpec("kijun_period", "Kijun period", "int", 26, min=5, max=200),
            ParamSpec("senkou_b_period", "Senkou B period", "int", 52, min=10, max=400),
            ParamSpec("require_cloud_filter", "Require price above cloud", "bool", True),
        ]

    def required_history(self) -> int:
        p = self.params
        return p["senkou_b_period"] + p["kijun_period"] + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        tp, kp, sbp = p["tenkan_period"], p["kijun_period"], p["senkou_b_period"]

        tenkan = (df["high"].rolling(tp).max() + df["low"].rolling(tp).min()) / 2.0
        kijun = (df["high"].rolling(kp).max() + df["low"].rolling(kp).min()) / 2.0
        span_a_raw = (tenkan + kijun) / 2.0
        span_b_raw = (df["high"].rolling(sbp).max() + df["low"].rolling(sbp).min()) / 2.0

        out["tenkan"] = tenkan
        out["kijun"] = kijun
        # Forward-shift by kijun_period: the cloud value visible "now" was
        # fully knowable kijun_period bars ago -- causal, no lookahead.
        out["cloud_a"] = span_a_raw.shift(kp)
        out["cloud_b"] = span_b_raw.shift(kp)
        out["cloud_top"] = out[["cloud_a", "cloud_b"]].max(axis=1)
        out["cloud_bottom"] = out[["cloud_a", "cloud_b"]].min(axis=1)
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row, prev = df.iloc[i], df.iloc[i - 1]
        close = float(row["close"])
        tk, kj, ptk, pkj = (float(row["tenkan"]), float(row["kijun"]),
                            float(prev["tenkan"]), float(prev["kijun"]))
        ctop, cbot = row.get("cloud_top"), row.get("cloud_bottom")
        vals_to_check = [tk, kj, ptk, pkj]
        if p["require_cloud_filter"]:
            vals_to_check += [ctop, cbot]
        if any(pd.isna(v) for v in vals_to_check):
            return self.hold(symbol, "ichimoku warming up", price=close)

        crossed_up = ptk <= pkj and tk > kj
        crossed_down = ptk >= pkj and tk < kj
        above_cloud = close > float(ctop) if not pd.isna(ctop) else True
        below_cloud = close < float(cbot) if not pd.isna(cbot) else False
        state = f"close={close:.6g} tenkan={tk:.6g} kijun={kj:.6g}"

        if position is None:
            if crossed_up:
                if p["require_cloud_filter"] and not above_cloud:
                    return self.hold(symbol, f"Tenkan crossed above Kijun but price "
                                     f"not above cloud -- no entry. {state}", price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"Tenkan crossed above Kijun" +
                              (", price above cloud" if p["require_cloud_filter"] else "") +
                              f". {state}", price=close)
            return self.hold(symbol, f"no bullish cross. {state}", price=close)

        if crossed_down:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"Tenkan crossed below Kijun -- exit. {state}", price=close)
        if p["require_cloud_filter"] and below_cloud:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"price fell below cloud -- exit. {state}", price=close)
        return self.hold(symbol, f"holding long. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = IchimokuCloudStrategy(params)
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
    # (timeframe, buffer_days, tenkan, kijun, senkou_b, require_cloud_filter)
    configs = [
        ("1h", 14, 9, 26, 52, True),
        ("1h", 14, 9, 26, 52, False),
        ("1h", 14, 10, 30, 60, True),
        ("1h", 14, 10, 30, 60, False),
        ("1h", 14, 7, 22, 44, True),
        ("4h", 40, 9, 26, 52, True),
        ("4h", 40, 9, 26, 52, False),
        ("4h", 40, 10, 30, 60, True),
        ("4h", 40, 10, 30, 60, False),
        ("4h", 40, 7, 22, 44, True),
    ]
    cache = {}
    for tf, buffer_days, tk, kj, sb, filt in configs:
        if tf not in cache:
            print(f"\n=== fetching timeframe {tf} ===")
            train_dfs = await fetch_all(_d(TRAIN_START), _d(TRAIN_END), tf, buffer_days)
            test_dfs = await fetch_all(_d(TEST_START), _d(TEST_END), tf, buffer_days)
            cache[tf] = (train_dfs, test_dfs)
        train_dfs, test_dfs = cache[tf]

        params = {"timeframe": tf, "tenkan_period": tk, "kijun_period": kj,
                  "senkou_b_period": sb, "require_cloud_filter": filt}
        train_m = eval_window(train_dfs, _d(TRAIN_START), _d(TRAIN_END), params, risk)
        test_m = eval_window(test_dfs, _d(TEST_START), _d(TEST_END), params, risk)
        label = f"{tf} ichimoku(tk={tk},kj={kj},sb={sb},filt={filt})"
        results.append({"label": label, "params": params, "train": train_m, "test": test_m})
        print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
              f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
              f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
              f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/4f57d4f3-3df5-59f5-8da8-ffbca878efea/scratchpad/ichimoku_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results,
                   "windows": {"train": [_d(TRAIN_START), _d(TRAIN_END)],
                               "test": [_d(TEST_START), _d(TEST_END)],
                               "older": [_d(OLDER_START), _d(OLDER_END)]}}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
