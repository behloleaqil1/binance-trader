"""Research script (NOT production code): trend_momentum ENTRY (already closed,
best train PF ever 0.99 @15m, rejected at every TF) combined with a genuinely
NEW EXIT mechanism — a volume-weighted VWAP trailing stop — instead of the
strategy's own signal-side exit (EMA cross-down / RSI blow-off / MACD fade).

Why this is a new combination, not a re-test: Run 22 already closed "exit
mechanism" as a non-signal lever, but that experiment only tried a
time-based forced exit and a tighter SL/TP — both PRICE-only constructions.
Run 113/114 flagged that a VOLUME-WEIGHTED exit (trail behind VWAP) on an
already-rejected entry family had not been tried. This is that test: same
EMA20/50 + RSI[50,70] + MACD(12,26,9) entry as production `trend_momentum`
defaults (unmodified, closed family), but while long, exit when close drops
below (VWAP - trail_mult * volume-weighted-std) computed over a rolling
window — the same VWAP/band construction already characterized in Run 113's
VwapBandReversionStrategy. Exchange-side SL/TP (2%/4%, RiskConfig defaults)
stays active and UNCHANGED throughout — this experiment only replaces the
strategy's own early-exit signal, never loosens a risk control.

Prior (Run 22, Run 23) generalization already states: "no mechanism layered
on a PF<1 entry signal (size, exit timing, exit price, or cost) can
manufacture edge that isn't there." This experiment tests whether that
generalization also holds for a volume-weighted exit specifically, closing
the one concretely-named open thread from Run 113/114's distilled notes.

Standalone research strategy class here, NOT registered in
app/strategies/registry.py and NOT touching any production file — only
promoted if it clears the anti-noise bar (OOS PF > 1.1 AND >= 30 OOS
trades) on a genuine held-out window, and then only re-checked against a
3rd non-overlapping window before being considered for adoption.
"""
import asyncio
import json
import math
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import PositionView, Signal, SignalAction
from app.risk.models import RiskConfig
from app.strategies.base import TIMEFRAMES, ParamSpec, Strategy
from app.strategies.indicators import ema, macd, rsi
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

# Anchor = today, 2026-11-25. TRAIN = 150d-60d ago, TEST = 60d-0d ago.
ANCHOR = pd.Timestamp("2026-11-25", tz="UTC")
TRAIN_START = (ANCHOR - pd.Timedelta(days=150)).strftime("%Y-%m-%d")
TRAIN_END = (ANCHOR - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
TEST_START = TRAIN_END
TEST_END = ANCHOR.strftime("%Y-%m-%d")


class TrendMomentumVwapTrailExit(Strategy):
    """Entry identical to production trend_momentum defaults (EMA cross +
    RSI band + MACD confirmation, long-only). Exit replaced: while long,
    exit when close closes below a rolling volume-weighted VWAP trailing
    band (VWAP - trail_mult * volume-weighted std), instead of EMA
    cross-down/RSI-blowoff/MACD-fade. Exchange-side SL/TP unchanged."""
    id = "trend_momentum_vwap_trail_exit"
    name = "Trend/Momentum + VWAP Trailing Exit (research)"
    description = "trend_momentum entry, VWAP-trailing-stop exit (research only)."

    @classmethod
    def param_specs(cls) -> list[ParamSpec]:
        return [
            ParamSpec("timeframe", "Timeframe", "select", "1h", choices=TIMEFRAMES),
            ParamSpec("ema_fast", "Fast EMA", "int", 20, min=2, max=200),
            ParamSpec("ema_slow", "Slow EMA", "int", 50, min=5, max=400),
            ParamSpec("rsi_period", "RSI period", "int", 14, min=2, max=50),
            ParamSpec("rsi_buy_min", "RSI min for entry", "float", 50, min=0, max=100),
            ParamSpec("rsi_buy_max", "RSI max for entry", "float", 70, min=0, max=100),
            ParamSpec("macd_fast", "MACD fast", "int", 12, min=2, max=100),
            ParamSpec("macd_slow", "MACD slow", "int", 26, min=5, max=200),
            ParamSpec("macd_signal", "MACD signal", "int", 9, min=2, max=50),
            ParamSpec("require_macd", "Require MACD confirmation", "bool", True),
            ParamSpec("vwap_period", "VWAP rolling window", "int", 20, min=5, max=200),
            ParamSpec("trail_mult", "Trail width (x volume-weighted std)", "float", 1.5, min=0.25, max=4.0),
        ]

    def required_history(self) -> int:
        p = self.params
        return max(p["ema_slow"], p["macd_slow"] + p["macd_signal"], p["rsi_period"],
                   p["vwap_period"]) + 10

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        out = df.copy()
        out["ema_fast"] = ema(df["close"], p["ema_fast"])
        out["ema_slow"] = ema(df["close"], p["ema_slow"])
        out["rsi"] = rsi(df["close"], p["rsi_period"])
        _, _, out["macd_hist"] = macd(df["close"], p["macd_fast"], p["macd_slow"],
                                      p["macd_signal"])
        pv = out["close"] * out["volume"]
        roll_vol = out["volume"].rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum()
        vwap = pv.rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum() / roll_vol
        sq_dev = (out["close"] - vwap) ** 2 * out["volume"]
        var = sq_dev.rolling(p["vwap_period"], min_periods=p["vwap_period"]).sum() / roll_vol
        std = var.clip(lower=0) ** 0.5
        out["vwap"] = vwap
        out["trail_level"] = vwap - p["trail_mult"] * std
        return out

    def decide(self, symbol: str, df: pd.DataFrame, i: int,
               position: PositionView | None) -> Signal:
        p = self.params
        if i < 1:
            return self.hold(symbol, "not enough candles")
        row, prev = df.iloc[i], df.iloc[i - 1]
        close = float(row["close"])
        ef, es, r, hist, trail = (float(row["ema_fast"]), float(row["ema_slow"]),
                                   float(row["rsi"]), float(row["macd_hist"]),
                                   row["trail_level"])
        if any(math.isnan(v) for v in (ef, es, r, hist,
                                        float(prev["ema_fast"]), float(prev["ema_slow"]))):
            return self.hold(symbol, "indicators warming up")

        crossed_up = float(prev["ema_fast"]) <= float(prev["ema_slow"]) and ef > es
        state = f"close={close:.6g} EMA{p['ema_fast']}={ef:.6g} EMA{p['ema_slow']}={es:.6g} RSI={r:.1f}"

        if position is None:
            if crossed_up:
                if not (p["rsi_buy_min"] <= r <= p["rsi_buy_max"]):
                    return self.hold(symbol, f"EMA crossed up but RSI out of band. {state}", price=close)
                if p["require_macd"] and hist <= 0:
                    return self.hold(symbol, f"EMA crossed up but MACD not confirmed. {state}", price=close)
                return Signal(SignalAction.BUY, symbol, self.id,
                              f"EMA cross-up entry (identical to trend_momentum defaults). {state}",
                              price=close)
            return self.hold(symbol, f"no entry. {state}", price=close)

        # Managing an open long: VWAP trailing-stop exit replaces the
        # signal-side EMA/RSI/MACD exit. Exchange-side SL/TP still active
        # (enforced by the simulator independently of this strategy).
        if pd.isna(trail):
            return self.hold(symbol, f"trail warming up. {state}", price=close)
        trail = float(trail)
        if close < trail:
            return Signal(SignalAction.SELL, symbol, self.id,
                          f"close below VWAP trailing stop ({trail:.6g}) — exit. {state}",
                          price=close)
        return self.hold(symbol, f"holding long, trail={trail:.6g}. {state}", price=close)


async def fetch_all(start, end, tf, buffer_days):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=buffer_days)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, params: dict, risk: RiskConfig, per_symbol=False):
    strategy = TrendMomentumVwapTrailExit(params)
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
            for trail_mult in (1.0, 1.5, 2.0):
                params = {"timeframe": tf, "ema_fast": 20, "ema_slow": 50,
                          "rsi_period": 14, "rsi_buy_min": 50, "rsi_buy_max": 70,
                          "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
                          "require_macd": True, "vwap_period": vwap_period,
                          "trail_mult": trail_mult}
                train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, params, risk)
                test_m = eval_window(test_dfs, TEST_START, TEST_END, params, risk)
                label = f"{tf} vwap_period={vwap_period} trail_mult={trail_mult}"
                results.append({"label": label, "params": params, "train": train_m, "test": test_m})
                print(f"{label} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                      f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                      f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                      f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    out_path = "/tmp/claude-0/-home-user-binance-trader/3ba3cf2f-6c2c-5117-b9c2-80f726d798de/scratchpad/trend_momentum_vwap_trail_results.json"
    with open(out_path, "w") as f:
        json.dump({"sweep": results, "train_window": [TRAIN_START, TRAIN_END],
                    "test_window": [TEST_START, TEST_END]}, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
