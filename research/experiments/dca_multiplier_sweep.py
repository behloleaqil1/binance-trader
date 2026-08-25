"""Research script (NOT production code): DCA dip-multiplier magnitude sweep.

Per DISTILLED LEARNINGS: the last explicitly flagged, not-yet-tested DCA
variant is the dip_multiplier MAGNITUDE at the shipped dip_threshold_pct=5.0.
Run 4 tested a *combined* change (3% threshold + 2.5x multiplier together,
rejected: wins only 4/8 symbols in a trending-up window and costs 13-30% more
deployed capital) and Run 14 tested capping the *count* of dip-buys (rejected:
capping can only match or hurt ROI, never help). Neither isolated the
multiplier magnitude alone at the shipped 5% threshold. This script does:
dip_multiplier in {1.5 (shipped), 1.75, 2.0, 2.5} at dip_threshold_pct=5.0
fixed, same capital-normalized ROI methodology as Run 4/5/14 (ROI =
unrealized_pnl / invested; DCA has no round-trip trades so PF doesn't apply).
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

OLDER_START, OLDER_END = "2025-12-28", "2026-03-28"
TRAIN_START, TRAIN_END = "2026-03-28", "2026-06-27"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-27", "2026-08-25"     # 60d-0d ago (today)


def run_dca(strategy: DCAStrategy, df: pd.DataFrame, cfg: SimConfig,
            timeframe_ms: int) -> dict:
    """Unmodified DCA schedule/dip-buy loop (matches production run_dca_backtest
    shape exactly, dip_multiplier magnitude is the only thing varied via params)."""
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


def eval_window(dfs: dict, dip_multiplier: float):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({
            "interval": "daily", "time_utc": "08:00", "weekday": "MON",
            "quote_amount": 15.0, "dip_enabled": True,
            "dip_threshold_pct": 5.0, "dip_multiplier": dip_multiplier,
            "protect_with_stops": False,
        })
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000)
    avg_roi = sum(r["roi_pct"] for r in per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    total_invested = sum(r["invested"] for r in per_symbol.values())
    return {"per_symbol": per_symbol, "avg_roi_pct": round(avg_roi, 4),
            "total_invested": round(total_invested, 2)}


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
    multipliers = [1.5, 1.75, 2.0, 2.5]  # 1.5 = shipped default

    results = {}
    for wname, dfs in windows.items():
        results[wname] = {}
        for m in multipliers:
            r = eval_window(dfs, m)
            results[wname][str(m)] = r
            print(f"[{wname}] dip_multiplier={m} avg_roi%={r['avg_roi_pct']} "
                  f"invested=${r['total_invested']}")

    print("\n=== Summary: avg ROI% by window x multiplier ===")
    for wname in windows:
        row = " | ".join(f"mult={m}: {results[wname][str(m)]['avg_roi_pct']:+.4f}%"
                          for m in multipliers)
        print(f"{wname}: {row}")

    print("\n=== Symbol win-rate vs shipped 1.5x baseline (per window) ===")
    for wname in windows:
        base = results[wname]["1.5"]["per_symbol"]
        for m in multipliers[1:]:
            variant = results[wname][str(m)]["per_symbol"]
            wins = sum(1 for s in base if variant.get(s, {}).get("roi_pct", -999) > base[s]["roi_pct"])
            n = len(base)
            print(f"{wname} mult={m}: beats 1.5x in {wins}/{n} symbols")

    out_path = "/tmp/claude-0/-home-user-binance-trader/b8ac67f5-5603-5b0c-8935-8b49de2d70c7/scratchpad/dca_multiplier_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
