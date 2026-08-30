"""Research script (NOT production code): Run 36.

Per Run 35's close-out note: DCA's two dip-buy parameters (threshold,
multiplier) are both now fully characterized and closed; the one
concretely-named-but-untried idea left on the DCA axis is "a signal-
conditioned threshold ... not yet tried but likely low-value given all 5
signal-source categories are individually null". This run tries it anyway,
narrowly scoped: gate the dip-buy MULTIPLIER (not the schedule, not the
base buy) on the symbol's own price position relative to a rolling SMA —
"only widen the buy when price is already below its own trend average"
(below_sma: catch corrections within/after a downtrend) vs the mirror
control (above_sma: widen only in an intact uptrend, the opposite
hypothesis) vs the shipped ungated baseline (none). This is mechanically
different from every prior DCA test (Run 4/14/27/35 varied threshold/
multiplier magnitude or capped count; none ever conditioned the dip-buy on
a second, independent signal). It reopens "combine a closed signal-source
category (price-level/SMA) with DCA" narrowly, as anticipated in Run 35.

Same capital-normalized ROI methodology as Run 4/14/27/32/35 (DCA has no
round-trip trades, so PF/win-rate/trade-count don't apply): average ROI
(unrealized P&L / invested) across the 8-symbol universe, per gate config,
vs the dip_enabled=False control, across 3 non-overlapping windows.
Windows rolled forward 1 day from Run 35 to use today's fresh close (anchor
2026-08-30) as the self-correction side effect on the baseline row.
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

OLDER_START, OLDER_END = "2026-01-02", "2026-04-02"
TRAIN_START, TRAIN_END = "2026-04-02", "2026-07-01"   # 150d-60d ago
TEST_START, TEST_END = "2026-07-01", "2026-08-30"     # 60d-0d ago (today)

SHIPPED_THRESHOLD = 5.0
SHIPPED_MULTIPLIER = 1.5

# gate_mode: "none" = shipped (ungated), "below_sma"/"above_sma" = only apply
# the dip multiplier when the pre-dip close is below/above its own rolling
# SMA(sma_period) on the entry timeframe (1h bars).
CONFIGS = [
    ("none", None),
    ("below_sma", 50), ("below_sma", 100), ("below_sma", 200),
    ("above_sma", 50), ("above_sma", 100), ("above_sma", 200),
]


def run_dca(strategy: DCAStrategy, df: pd.DataFrame, cfg: SimConfig,
            timeframe_ms: int, gate_mode: str, sma_period: int | None) -> dict:
    cash = cfg.initial_equity
    qty_held = 0.0
    invested = 0.0
    n_dip_fired = 0
    n_dip_gated_out = 0
    last_run: datetime | None = None
    lookback = max(1, 86_400_000 // timeframe_ms)

    sma = df["close"].rolling(sma_period).mean() if sma_period else None

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

            if is_dip and gate_mode != "none":
                sma_val = float(sma.iloc[i - 1]) if sma is not None and i >= 1 else None
                prev_close = float(df["close"].iloc[i - 1]) if i >= 1 else None
                gate_ok = sma_val is not None and prev_close is not None and not pd.isna(sma_val)
                if gate_ok:
                    if gate_mode == "below_sma":
                        gate_ok = prev_close < sma_val
                    elif gate_mode == "above_sma":
                        gate_ok = prev_close > sma_val
                if not gate_ok:
                    is_dip = False
                    n_dip_gated_out += 1

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
            "roi_pct": round(roi_pct, 4), "dip_buys_fired": n_dip_fired,
            "dip_gated_out": n_dip_gated_out}


async def fetch_all(start, end):
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", TF, start, end)
    return out


def eval_window(dfs: dict, gate_mode: str, sma_period: int | None):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    per_symbol = {}
    for sym, df in dfs.items():
        if len(df) < 10:
            continue
        strategy = DCAStrategy({
            "interval": "daily", "time_utc": "08:00", "weekday": "MON",
            "quote_amount": 15.0, "dip_enabled": True,
            "dip_threshold_pct": SHIPPED_THRESHOLD, "dip_multiplier": SHIPPED_MULTIPLIER,
            "protect_with_stops": False,
        })
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000, gate_mode, sma_period)
    avg_roi = sum(r["roi_pct"] for r in per_symbol.values()) / len(per_symbol) if per_symbol else 0.0
    total_invested = sum(r["invested"] for r in per_symbol.values())
    total_dips = sum(r["dip_buys_fired"] for r in per_symbol.values())
    total_gated_out = sum(r["dip_gated_out"] for r in per_symbol.values())
    return {"per_symbol": per_symbol, "avg_roi_pct": round(avg_roi, 4),
            "total_invested": round(total_invested, 2), "total_dips": total_dips,
            "total_gated_out": total_gated_out}


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
        per_symbol[sym] = run_dca(strategy, df, cfg, 3_600_000, "none", None)
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
        for gate_mode, sma_period in CONFIGS:
            key = f"{gate_mode}_{sma_period}"
            r = eval_window(dfs, gate_mode, sma_period)
            results[wname][key] = r
            off = off_results[wname]["avg_roi_pct"]
            print(f"[{wname}] {key} avg_roi%={r['avg_roi_pct']:+.4f} "
                  f"(off={off:+.4f}, delta={r['avg_roi_pct']-off:+.4f}pp) "
                  f"invested=${r['total_invested']} dips={r['total_dips']} "
                  f"gated_out={r['total_gated_out']}")

    print("\n=== Summary: delta vs dip-OFF control, by config x window (pp) ===")
    header = "config".ljust(16) + "".join(w.ljust(12) for w in windows)
    print(header)
    for gate_mode, sma_period in CONFIGS:
        key = f"{gate_mode}_{sma_period}"
        row = key.ljust(16)
        for wname in windows:
            delta = results[wname][key]["avg_roi_pct"] - off_results[wname]["avg_roi_pct"]
            row += f"{delta:+.4f}".ljust(12)
        print(row)

    print("\n=== Per-symbol win-rate: gate config beats OFF (per window, per config) ===")
    for gate_mode, sma_period in CONFIGS:
        key = f"{gate_mode}_{sma_period}"
        for wname in windows:
            on = results[wname][key]["per_symbol"]
            off = off_results[wname]["per_symbol"]
            wins = sum(1 for s in on if on[s]["roi_pct"] > off.get(s, {}).get("roi_pct", -999))
            n = len(on)
            print(f"{key} {wname}: {wins}/{n} symbols beat OFF")

    out = {"windows": results, "off": off_results}
    out_path = "/tmp/claude-0/-home-user-binance-trader/1391d2b2-e4b9-5173-bb3b-96adf28104af/scratchpad/dca_trend_gate.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
