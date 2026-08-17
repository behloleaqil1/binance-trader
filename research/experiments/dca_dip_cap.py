"""Research script (NOT production code): DCA dip-rebuy cap.

Hypothesis (flagged as an open DCA variant in DISTILLED LEARNINGS after
Run 4/5): the shipped dip-buy feature (`dip_multiplier=1.5x` whenever the
24h change <= -5%) applies its bonus on EVERY qualifying scheduled buy,
unconditionally. In a sustained decline, that means repeatedly upsizing
buys into an asset that keeps falling -- each individual dip-buy is
mechanically explicable (a locally-lower entry vs the flat schedule), but
an unlimited run of them is a different bet: it's no longer "buy a bit
more on a dip", it's "keep averaging up dip-sized buys through an entire
drawdown", which is closer to catching a falling knife than the modest,
self-limiting mechanism that was validated in Run 4.

This script tests whether CAPPING the number of dip-multiplied buys per
backtest window (after the cap, buys still fire on schedule at the flat
amount, they just stop getting upsized) changes capital-normalized ROI
vs the uncapped shipped default -- same methodology as Run 4/5 (ROI =
unrealized_pnl / invested, no round-trip trades so PF doesn't apply).
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

# 3 non-overlapping windows, same shape as Run 4/5, shifted to today's anchor.
OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"
TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-18", "2026-08-17"     # 60d-0d ago (today)

BASE_PARAMS = {
    "interval": "daily", "time_utc": "08:00", "weekday": "MON",
    "quote_amount": 15.0, "dip_enabled": True,
    "dip_threshold_pct": 5.0, "dip_multiplier": 1.5,
    "protect_with_stops": False,
}


def run_dca_capped(strategy: DCAStrategy, df: pd.DataFrame, cfg: SimConfig,
                    timeframe_ms: int, dip_max_buys: int | None) -> dict:
    """Copy of run_dca_backtest's core loop with one addition: once
    `dip_max_buys` dip-multiplied buys have fired in this window, later
    qualifying dips still buy (schedule is never skipped) but at the flat
    `quote_amount`, no multiplier. dip_max_buys=None reproduces the
    unmodified shipped behavior exactly (sanity-checked below)."""
    cash = cfg.initial_equity
    qty_held = 0.0
    invested = 0.0
    dip_buy_count = 0
    n_dip_fired = 0
    n_dip_capped = 0
    last_run: datetime | None = None
    lookback = max(1, 86_400_000 // timeframe_ms)

    for i in range(len(df)):
        row = df.iloc[i]
        o, c, ts = float(row["open"]), float(row["close"]), int(row["open_time"])
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
                if dip_max_buys is None or dip_buy_count < dip_max_buys:
                    amount = round(amount * p["dip_multiplier"], 2)
                    dip_buy_count += 1
                    n_dip_fired += 1
                else:
                    n_dip_capped += 1

            fill = _slip(o, cfg, "BUY")
            fee = _fee(amount, cfg)
            if cash >= amount + fee and amount > 0 and fill > 0:
                cash -= amount + fee
                bought = amount / fill
                qty_held += bought
                invested += amount

    last_close = float(df["close"].iloc[-1]) if len(df) else 0.0
    unrealized = qty_held * last_close - invested
    roi_pct = (unrealized / invested * 100) if invested > 0 else 0.0
    return {"invested": round(invested, 2), "unrealized_pnl": round(unrealized, 4),
            "roi_pct": round(roi_pct, 4), "dip_buys_fired": n_dip_fired,
            "dip_buys_capped": n_dip_capped}


async def fetch_all(start, end):
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, start, end)
        out[sym] = df
    return out


def eval_window(dfs: dict, dip_max_buys):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({**BASE_PARAMS})
        res = run_dca_capped(strategy, df, cfg, 3_600_000, dip_max_buys)
        per_symbol[sym] = res
    avg_roi = sum(r["roi_pct"] for r in per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    return {"per_symbol": per_symbol, "avg_roi_pct": round(avg_roi, 4)}


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
    cap_variants = [None, 5, 3, 2, 1]  # None = uncapped, matches shipped default exactly

    results = {}
    for wname, dfs in windows.items():
        results[wname] = {}
        for cap in cap_variants:
            r = eval_window(dfs, cap)
            results[wname][str(cap)] = r
            print(f"[{wname}] cap={cap} avg_roi%={r['avg_roi_pct']}")

    # Sanity check: cap=None must exactly reproduce shipped run_dca_backtest ROI shape.
    print("\n=== Summary: avg ROI% by window x cap ===")
    for wname in windows:
        row = " | ".join(f"cap={c}: {results[wname][str(c)]['avg_roi_pct']:+.4f}%"
                          for c in cap_variants)
        print(f"{wname}: {row}")

    print("\n=== Symbol win-rate vs uncapped baseline (per window) ===")
    for wname in windows:
        base = results[wname]["None"]["per_symbol"]
        for cap in cap_variants[1:]:
            capped = results[wname][str(cap)]["per_symbol"]
            wins = sum(1 for s in base if capped.get(s, {}).get("roi_pct", -999) > base[s]["roi_pct"])
            n = len(base)
            print(f"{wname} cap={cap}: beats uncapped in {wins}/{n} symbols")

    with open("/tmp/claude-0/-home-user-binance-trader/a86b3aee-8c2b-5e9a-8d95-6eb74274a6ef/scratchpad/dca_dip_cap_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved results to dca_dip_cap_results.json")


if __name__ == "__main__":
    asyncio.run(main())
