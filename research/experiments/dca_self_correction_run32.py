"""Research script (NOT production code): Run 32 self-correction check.

Per Run 31's explicit recommendation ("further runs should default to
periodic self-correction — revalidating the shipped DCA dip-buy against
rolling-forward windows as real time passes") — every concretely-scoped new
axis (signal source x5 categories/6 families, TF 1m-1d, symbol universe,
historical era, position sizing, exit mechanism, cost level, gate
combinations) is exhausted per DISTILLED LEARNINGS. This run does NOT invent
a new recombination; it re-validates the one standing positive finding (DCA
dip-buy, dip_threshold_pct=5.0 / dip_multiplier=1.5x, both shipped defaults)
against today's rolling windows, one day forward of Run 4/27's checks, using
the identical capital-normalized ROI methodology (ROI = unrealized_pnl /
invested; DCA has no round-trip trades so PF doesn't apply).
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

OLDER_START, OLDER_END = "2025-12-31", "2026-03-31"
TRAIN_START, TRAIN_END = "2026-03-31", "2026-06-29"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-29", "2026-08-28"     # 60d-0d ago (today)


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
            "dip_threshold_pct": 5.0, "dip_multiplier": 1.5,
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

    results = {}
    for wname, dfs in windows.items():
        results[wname] = {}
        for dip_enabled in [True, False]:
            r = eval_window(dfs, dip_enabled)
            results[wname][str(dip_enabled)] = r
            print(f"[{wname}] dip_enabled={dip_enabled} avg_roi%={r['avg_roi_pct']} "
                  f"invested=${r['total_invested']} dip_fires="
                  f"{sum(v['dip_buys_fired'] for v in r['per_symbol'].values())}")

    print("\n=== Summary: avg ROI% by window, dip-buy ON vs OFF ===")
    for wname in windows:
        on = results[wname]["True"]["avg_roi_pct"]
        off = results[wname]["False"]["avg_roi_pct"]
        print(f"{wname}: dip_ON={on:+.4f}% dip_OFF={off:+.4f}% delta={on - off:+.4f}pp")

    print("\n=== Symbol win-rate: dip-buy ON beats OFF (per window) ===")
    for wname in windows:
        on = results[wname]["True"]["per_symbol"]
        off = results[wname]["False"]["per_symbol"]
        wins = sum(1 for s in on if on[s]["roi_pct"] > off.get(s, {}).get("roi_pct", -999))
        n = len(on)
        print(f"{wname}: {wins}/{n} symbols")

    out_path = "/tmp/claude-0/-home-user-binance-trader/a2dd58b5-0d37-543e-af8d-8f875ac3eaea/scratchpad/dca_self_correction_run32.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
