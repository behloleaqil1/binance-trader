"""Research script (NOT production code): Run 35.

Per DISTILLED LEARNINGS after Run 34: all 8 strategy families and all 5
signal-source categories are closed on the 8-symbol/1h-4h scope; the
standing recommendation is the Run 31/32 self-correction protocol (DCA
dip-buy re-check on rolling-forward windows). Run 32's re-check was only
1 day ago (2026-08-28 anchor) — re-running it verbatim today would be near-
duplicate. Instead this run isolates a variable Run 4 only ever tested
*bundled* with a multiplier change (its "3%/2.5x" variant): `dip_threshold_pct`
on its own, with `dip_multiplier` held at the shipped 1.5x. Run 27 already
isolated the multiplier (holding threshold=5.0 fixed); this is the mirror
case, closing out DCA's two dip-buy parameters as both independently
characterized. The baseline row (threshold=5.0, shipped) also re-validates
the shipped default on fresh rolling-forward data as a side effect,
serving the standing self-correction requirement.

Same capital-normalized ROI methodology as Run 4/14/27/32 (DCA has no
round-trip trades, so PF doesn't apply): invested capital vs unrealized
mark-to-market, averaged per-symbol, then across symbols, dip_enabled vs
disabled control, 3 non-overlapping windows.
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

# Same anchor as Run 34/35 (today = 2026-08-29), consistent with the
# recently-fetched windows already used this run cycle.
OLDER_START, OLDER_END = "2026-01-01", "2026-04-01"
TRAIN_START, TRAIN_END = "2026-04-01", "2026-06-30"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-30", "2026-08-29"     # 60d-0d ago (today)

# Shipped default is 5.0; sweep around it, multiplier fixed at shipped 1.5x.
THRESHOLDS = [3.0, 4.0, 5.0, 7.0, 10.0]


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


def eval_window(dfs: dict, threshold: float):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({
            "interval": "daily", "time_utc": "08:00", "weekday": "MON",
            "quote_amount": 15.0, "dip_enabled": True,
            "dip_threshold_pct": threshold, "dip_multiplier": 1.5,
            "protect_with_stops": False,
        })
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000)
    avg_roi = sum(r["roi_pct"] for r in per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    total_invested = sum(r["invested"] for r in per_symbol.values())
    total_dips = sum(r["dip_buys_fired"] for r in per_symbol.values())
    return {"per_symbol": per_symbol, "avg_roi_pct": round(avg_roi, 4),
            "total_invested": round(total_invested, 2), "total_dips": total_dips}


def eval_off(dfs: dict):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({
            "interval": "daily", "time_utc": "08:00", "weekday": "MON",
            "quote_amount": 15.0, "dip_enabled": False,
            "dip_threshold_pct": 5.0, "dip_multiplier": 1.5,
            "protect_with_stops": False,
        })
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000)
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

    results = {}
    off_results = {}
    for wname, dfs in windows.items():
        off_results[wname] = eval_off(dfs)
        results[wname] = {}
        for t in THRESHOLDS:
            r = eval_window(dfs, t)
            results[wname][str(t)] = r
            off = off_results[wname]["avg_roi_pct"]
            print(f"[{wname}] threshold={t} avg_roi%={r['avg_roi_pct']:+.4f} "
                  f"(off={off:+.4f}, delta={r['avg_roi_pct']-off:+.4f}pp) "
                  f"invested=${r['total_invested']} dips={r['total_dips']}")

    print("\n=== Summary: delta vs dip-OFF control, by threshold x window (pp) ===")
    header = "threshold".ljust(10) + "".join(w.ljust(12) for w in windows)
    print(header)
    for t in THRESHOLDS:
        row = str(t).ljust(10)
        for wname in windows:
            delta = results[wname][str(t)]["avg_roi_pct"] - off_results[wname]["avg_roi_pct"]
            row += f"{delta:+.4f}".ljust(12)
        print(row)

    print("\n=== Per-symbol win-rate: dip-ON beats OFF (per window, per threshold) ===")
    for t in THRESHOLDS:
        for wname in windows:
            on = results[wname][str(t)]["per_symbol"]
            off = off_results[wname]["per_symbol"]
            wins = sum(1 for s in on if on[s]["roi_pct"] > off.get(s, {}).get("roi_pct", -999))
            n = len(on)
            print(f"threshold={t} {wname}: {wins}/{n} symbols beat OFF")

    out = {"windows": results, "off": off_results}
    out_path = "/tmp/claude-0/-home-user-binance-trader/18b2a9a0-f6ea-5847-9c97-660e17d1cbb0/scratchpad/dca_threshold_isolation.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
