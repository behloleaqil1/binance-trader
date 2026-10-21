"""Research script (NOT production code): Run 65.

First test of the short side of trend_momentum since the 2026-10-21
capability addition (backtest-only allow_short on run_candle_backtest and
TrendMomentumStrategy — see RESEARCH_LOG.md "Capability addition" section
right after Run 64). That section explicitly recommends a dedicated run
testing trend-following shorts before assuming shorting changes the
headline "no edge found" conclusion. Long-only trend_momentum is closed
(DISTILLED LEARNINGS: best train PF ever 0.99 @15m, rejected at every TF
1m-1d) — this does NOT re-test the long side; it isolates the SHORT side.

Three configs, same train/test/older discipline as every prior run
(optimize 150d-60d ago, validate held-out 60d-0d ago, 3rd older window as
a robustness check only if the first two clear):
  A) short-only @ 1h  — longs suppressed via a thin subclass (see
     TrendMomentumShortOnly below) so the short mechanism is judged in
     isolation, not mixed with the already-closed long side's trades.
  B) short-only @ 4h  — same mechanism, slower TF (less fee drag per trade).
  C) symmetric long+short @ 1h — the literal mirror strategy as shipped
     (allow_short=True, no suppression), to see whether adding shorts to
     the existing long entries changes the aggregate PF at all.

TrendMomentumShortOnly is a subclass defined ONLY in this research script —
it is not registered in app/strategies/registry.py and does not touch any
production file. It defers entirely to the parent's unmodified decide()
and converts any BUY signal into a hold, so the parent's exact short
entry/exit logic (already covered by the 12 new backend tests) runs
unmodified. Same fee/slippage/risk-config assumptions as every prior run:
7.5bps fees, 4bps slippage, exchange-side 2%/4% SL/TP (RiskConfig
defaults), never loosened.

Anti-noise bar unchanged: promising only if OOS (test) PF > 1.1 AND >= 30
test trades. Universe: BTC, ETH, SOL, BNB, XRP, LINK, DOGE, ADA vs USDT.
"""
import asyncio
import json
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, run_candle_backtest
from app.core.types import SignalAction
from app.risk.models import RiskConfig
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

OLDER_START, OLDER_END = "2025-12-23", "2026-05-24"   # 300d-150d ago, 3rd-window check
TRAIN_START, TRAIN_END = "2026-05-24", "2026-08-22"   # 150d-60d ago
TEST_START, TEST_END = "2026-08-22", "2026-10-21"     # 60d-0d ago (today's anchor)
BUFFER_DAYS = 20  # EMA/MACD/RSI warmup


class TrendMomentumShortOnly(TrendMomentumStrategy):
    """Defers to the parent's unmodified decide(); converts any BUY into a
    hold so only the short side's entries/exits are judged. Short logic
    itself is 100% parent code (allow_short must still be True in params)."""

    def decide(self, symbol, df, i, position):
        sig = super().decide(symbol, df, i, position)
        if sig.action == SignalAction.BUY:
            return self.hold(symbol, f"long entry suppressed (short-only research "
                              f"mode): {sig.reason}", price=sig.price)
        return sig


async def fetch_all(start, end, tf):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs: dict, start, end, strategy_cls, params: dict, risk: RiskConfig,
                 per_symbol=False):
    strategy = strategy_cls(params)
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        result = run_candle_backtest(strategy, risk, df, cfg, symbol=sym, allow_short=True)
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


BASE_PARAMS = {"ema_fast": 20, "ema_slow": 50, "rsi_period": 14,
               "rsi_buy_min": 50, "rsi_buy_max": 70, "rsi_exit": 78,
               "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
               "require_macd": True, "allow_short": True,
               "rsi_short_min": 30, "rsi_short_max": 50, "rsi_cover": 22}

CONFIGS = [
    {"label": "A: short-only @1h", "tf": "1h", "cls": TrendMomentumShortOnly},
    {"label": "B: short-only @4h", "tf": "4h", "cls": TrendMomentumShortOnly},
    {"label": "C: symmetric long+short @1h", "tf": "1h", "cls": TrendMomentumStrategy},
]


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()  # defaults: 2% SL / 4% TP, never loosened

    results = []
    for c in CONFIGS:
        tf = c["tf"]
        params = dict(BASE_PARAMS, timeframe=tf)
        print(f"\n=== {c['label']} ===")
        print("Fetching train window...")
        train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf)
        print("Fetching test window...")
        test_dfs = await fetch_all(TEST_START, TEST_END, tf)

        train = eval_window(train_dfs, TRAIN_START, TRAIN_END, c["cls"], params, risk)
        test = eval_window(test_dfs, TEST_START, TEST_END, c["cls"], params, risk,
                            per_symbol=True)
        print(f"TRAIN: pf={train['pf']} win%={train['win_pct']} trades={train['trades']} "
              f"avg_ret%={train['avg_ret_pct']}")
        print(f"TEST:  pf={test['pf']} win%={test['win_pct']} trades={test['trades']} "
              f"avg_ret%={test['avg_ret_pct']}")

        clears = (test["pf"] is not None and test["pf"] > 1.1 and test["trades"] >= 30
                  and train["pf"] is not None and train["pf"] > 1.1)
        older = None
        if clears:
            print("CLEARS initial OOS bar -- fetching 3rd (older) window for robustness check...")
            older_dfs = await fetch_all(OLDER_START, OLDER_END, tf)
            older = eval_window(older_dfs, OLDER_START, OLDER_END, c["cls"], params, risk,
                                 per_symbol=True)
            print(f"OLDER: pf={older['pf']} win%={older['win_pct']} trades={older['trades']} "
                  f"avg_ret%={older['avg_ret_pct']}")

        results.append({"label": c["label"], "timeframe": tf, "params": params,
                         "train": train, "test": test, "older": older,
                         "clears_oos_bar": clears})

    with open("../research/experiments/trend_momentum_shorts_output.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nWrote trend_momentum_shorts_output.json")


if __name__ == "__main__":
    asyncio.run(main())
