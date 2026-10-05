"""Research script (NOT production code): Run 42.

Standing self-correction protocol (per Run 31/32/35/36/38/40 recommendation):
DCA dip-buy ON-vs-OFF re-check on rolling-forward windows, due once 2+ full
days of new data have accumulated since the last check. Run 40 set the next
actionable date at "2026-10-02 or later" (2+ full days past its 2026-09-30
anchor); Run 41 fired same-day as Run 40 and deferred. No run fired between
Run 41 (2026-09-30) and today (2026-10-05) -- a 5-day gap, bar is well met.
All 3 windows shifted forward by exactly 5 days vs Run 40 (same window
lengths: older/train 90d, test 60d), anchored on today's close.

Every concretely-scoped strategy/signal/gate axis remains closed per
DISTILLED LEARNINGS as of Run 41 -- this run does NOT re-open any of them.
It only re-validates that the one standing shipped default (DCA dip-buy
dip_threshold_pct=5.0, dip_multiplier=1.5) still reproduces the same
regime-dependent pattern (helps in decline/chop, small drag in sustained
uptrend, both economically trivial) on data through today, per the
top-of-file SELF-CORRECTION mandate ("re-validate own prior committed
changes vs fresh data; revert if the bar is no longer met").

Same capital-normalized ROI methodology as Run 4/14/27/32/35/36/38/40 (DCA
has no round-trip trades, so PF/win-rate/trade-count don't apply): average
ROI (unrealized P&L / invested) across the 8-symbol universe, dip_enabled=True
(shipped) vs dip_enabled=False (control), across 3 non-overlapping windows
rolled forward to use today's close as the test-window anchor.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import json
from datetime import datetime, timezone

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, _fee, _slip
from app.strategies.dca import DCAStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

OLDER_START, OLDER_END = "2026-02-07", "2026-05-08"
TRAIN_START, TRAIN_END = "2026-05-08", "2026-08-06"
TEST_START, TEST_END = "2026-08-06", "2026-10-05"     # anchor = today

SHIPPED_THRESHOLD = 5.0
SHIPPED_MULTIPLIER = 1.5


def run_dca(strategy: DCAStrategy, df: pd.DataFrame, cfg: SimConfig,
            timeframe_ms: int) -> dict:
    cash = cfg.initial_equity
    qty_held = 0.0
    invested = 0.0
    n_dip_fired = 0
    last_run: datetime | None = None
    lookback = max(1, 86_400_000 // timeframe_ms)

    for i in range(len(df)):
        row = df.iloc[i]
        o, ts = float(row["open"]), int(row["open_time"])
        now = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if strategy.is_due(last_run, now):
            last_run = now
            change_pct = None
            if i >= lookback + 1:
                ref = float(df["close"].iloc[i - 1 - lookback])
                prev = float(df["close"].iloc[i - 1])
                change_pct = (prev / ref - 1) * 100 if ref else None

            p = strategy.params
            amount = p["quote_amount"]
            is_dip = (p["dip_enabled"] and change_pct is not None
                      and change_pct <= -p["dip_threshold_pct"])
            if is_dip:
                amount = round(amount * p["dip_multiplier"], 2)
                n_dip_fired += 1

            fill = _slip(o, cfg, "BUY")
            fee = _fee(amount, cfg)
            if cash >= amount + fee and amount > 0 and fill > 0:
                cash -= amount + fee
                qty_held += amount / fill
                invested += amount

    last_close = float(df["close"].iloc[-1]) if len(df) else 0.0
    unrealized = qty_held * last_close - invested
    roi_pct = (unrealized / invested * 100) if invested > 0 else 0.0
    return {"invested": round(invested, 2), "unrealized_pnl": round(unrealized, 4),
            "roi_pct": round(roi_pct, 4), "dip_buys_fired": n_dip_fired}


async def fetch_all(start, end):
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", TF, start, end)
    return out


def eval_window(dfs: dict, dip_enabled: bool):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({
            "interval": "daily", "time_utc": "08:00", "weekday": "MON",
            "quote_amount": 15.0, "dip_enabled": dip_enabled,
            "dip_threshold_pct": SHIPPED_THRESHOLD, "dip_multiplier": SHIPPED_MULTIPLIER,
            "protect_with_stops": False,
        })
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000)
    avg_roi = sum(r["roi_pct"] for r in per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    total_invested = sum(r["invested"] for r in per_symbol.values())
    total_dips = sum(r["dip_buys_fired"] for r in per_symbol.values())
    return {"per_symbol": per_symbol, "avg_roi_pct": round(avg_roi, 4),
            "total_invested": round(total_invested, 2), "total_dips": total_dips}


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)

    print("Fetching older window...")
    older_dfs = await fetch_all(OLDER_START, OLDER_END)
    print("Fetching train window...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print("Fetching test window...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    windows = {"older": older_dfs, "train": train_dfs, "test": test_dfs}

    on_results = {}
    off_results = {}
    for wname, dfs in windows.items():
        on_results[wname] = eval_window(dfs, True)
        off_results[wname] = eval_window(dfs, False)
        on = on_results[wname]["avg_roi_pct"]
        off = off_results[wname]["avg_roi_pct"]
        wins = sum(1 for s in on_results[wname]["per_symbol"]
                   if on_results[wname]["per_symbol"][s]["roi_pct"]
                   > off_results[wname]["per_symbol"].get(s, {}).get("roi_pct", -999))
        n = len(on_results[wname]["per_symbol"])
        print(f"[{wname}] ON avg_roi%={on:+.4f} OFF avg_roi%={off:+.4f} "
              f"delta={on-off:+.4f}pp invested=${on_results[wname]['total_invested']} "
              f"dips={on_results[wname]['total_dips']} win-fraction={wins}/{n}")

    out = {"windows": {"on": on_results, "off": off_results},
           "anchor": TEST_END}
    with open("../research/experiments/dca_self_correction_run42_output.json", "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
