"""Research script (NOT production code): ADX-gated grid strategy.

Hypothesis: grid's known failure mode is bag-holding through directional
trends (confirmed at 15m/1h/4h across prior runs). An ADX trend-strength
filter that blocks NEW grid buys while ADX indicates a strong trend (only
allowing entries while the market is genuinely ranging) might fix this,
without touching the existing stop_outside_range/flatten_on_stop safety
mechanisms at all.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, _fee, _slip
from app.backtest.metrics import compute_metrics
from app.strategies.grid import GridStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
TF = "1h"
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-18", "2026-06-16"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-16", "2026-08-15"     # 60d-0d ago
BUFFER_DAYS = 10  # extra history before window start for ADX warmup


def wilder_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(),
                     (high - prev_close).abs(),
                     (low - prev_close).abs()], axis=1).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move[(up_move > down_move) & (up_move > 0)]
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move[(down_move > up_move) & (down_move > 0)]

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx


def run_grid_adx_gated(strategy: GridStrategy, df: pd.DataFrame, cfg: SimConfig,
                        adx: pd.Series, adx_threshold: float | None) -> tuple[pd.Series, list[dict], dict]:
    """Copy of run_grid_backtest with one addition: new buys are skipped on
    any candle where ADX(i) >= adx_threshold (trend too strong to range-trade).
    Sells / pause / flatten logic is completely unchanged from production."""
    p = strategy.params
    first_close = float(df["close"].iloc[0])
    levels = strategy.levels(first_close)
    cash = cfg.initial_equity
    lots: dict[int, dict] = {}
    trades: list[dict] = []
    curve_ts, curve_val = [], []
    skipped_no_cash = 0
    skipped_adx = 0
    paused_at = None
    prev_close = first_close
    adx_vals = adx.values

    for i in range(len(df)):
        row = df.iloc[i]
        o, h, low, c, ts = (float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), int(row["open_time"]))
        if paused_at is None:
            a = adx_vals[i]
            adx_ok = adx_threshold is None or pd.isna(a) or a < adx_threshold
            if adx_ok:
                for idx, lp in enumerate(levels):
                    if lp >= prev_close or idx in lots:
                        continue
                    if low <= lp:
                        quote = p["quote_per_level"]
                        fee = _fee(quote, cfg)
                        if cash < quote + fee:
                            skipped_no_cash += 1
                            continue
                        cash -= quote + fee
                        lots[idx] = {"qty": quote / lp, "cost": lp, "fee": fee, "ts": ts}
            else:
                skipped_adx += 1
            for idx in sorted(list(lots)):
                sell_level = idx + 1
                if sell_level >= len(levels):
                    continue
                sp = levels[sell_level]
                if h >= sp:
                    lot = lots.pop(idx)
                    proceeds = lot["qty"] * sp
                    fee = _fee(proceeds, cfg)
                    cash += proceeds - fee
                    fees = lot["fee"] + fee
                    pnl = lot["qty"] * (sp - lot["cost"]) - fees
                    trades.append({"opened_at": lot["ts"], "closed_at": ts,
                                   "qty": round(lot["qty"], 10), "entry": lot["cost"],
                                   "exit": sp, "pnl": round(pnl, 6),
                                   "pnl_pct": round(pnl / (lot["qty"] * lot["cost"]) * 100, 4),
                                   "fees": round(fees, 6), "exit_kind": "grid_tp",
                                   "entry_reason": f"grid buy level {idx}",
                                   "exit_reason": f"grid sell level {sell_level}"})
            if p["stop_outside_range"] and not strategy.in_range(c, levels):
                paused_at = ts
                if p["flatten_on_stop"] and lots:
                    for idx in sorted(list(lots)):
                        lot = lots.pop(idx)
                        exit_p = _slip(c, cfg, "SELL")
                        proceeds = lot["qty"] * exit_p
                        fee = _fee(proceeds, cfg)
                        cash += proceeds - fee
                        fees = lot["fee"] + fee
                        pnl = lot["qty"] * (exit_p - lot["cost"]) - fees
                        trades.append({"opened_at": lot["ts"], "closed_at": ts,
                                       "qty": round(lot["qty"], 10),
                                       "entry": lot["cost"], "exit": exit_p,
                                       "pnl": round(pnl, 6),
                                       "pnl_pct": round(pnl / (lot["qty"] * lot["cost"]) * 100, 4),
                                       "fees": round(fees, 6),
                                       "exit_kind": "grid_stop",
                                       "entry_reason": f"grid buy level {idx}",
                                       "exit_reason": "price left grid range — flatten"})
        prev_close = c
        curve_ts.append(ts)
        curve_val.append(cash + sum(l["qty"] for l in lots.values()) * c)

    equity = pd.Series(curve_val, index=curve_ts, dtype=float)
    extras = {"warmup": 0, "skipped_no_cash": skipped_no_cash, "skipped_adx": skipped_adx,
              "paused_at": paused_at}
    return equity, trades, extras


async def fetch_all(start, end):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", TF, buf_start, end)
        out[sym] = df
    return out


def eval_window(dfs: dict, start, end, config: dict, adx_threshold):
    strategy = GridStrategy({**config})
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    for sym, full_df in dfs.items():
        adx_full = wilder_adx(full_df, 14)
        mask = (full_df["open_time"] >= start_ms) & (full_df["open_time"] < end_ms)
        df = full_df[mask].reset_index(drop=True)
        adx = adx_full[mask].reset_index(drop=True)
        if len(df) < 10:
            continue
        equity, trades, extras = run_grid_adx_gated(strategy, df, cfg, adx, adx_threshold)
        metrics = compute_metrics(equity, trades, EQUITY, df, 0)
        rets.append(metrics["total_return_pct"])
        all_trades.extend(trades)

    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)
    pf = gross_win / gross_loss if gross_loss > 1e-9 else (float("inf") if gross_win > 0 else 0.0)
    win_pct = len(wins) / len(all_trades) * 100 if all_trades else 0.0
    avg_ret = sum(rets) / len(rets) if rets else 0.0
    return {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
            "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4)}


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    print("Fetching train window data (with ADX warmup buffer)...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END)
    print("Fetching test window data...")
    test_dfs = await fetch_all(TEST_START, TEST_END)

    configs = [
        {"auto_range_pct": 10.0, "levels": 13, "flatten_on_stop": True,
         "quote_per_level": 150.0, "stop_outside_range": True},
        {"auto_range_pct": 6.0, "levels": 13, "flatten_on_stop": True,
         "quote_per_level": 150.0, "stop_outside_range": True},
    ]
    thresholds = [None, 30, 25, 20, 15]

    results = []
    for config in configs:
        for thr in thresholds:
            train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, config, thr)
            test_m = eval_window(test_dfs, TEST_START, TEST_END, config, thr)
            row = {"config": config, "adx_threshold": thr, "train": train_m, "test": test_m}
            results.append(row)
            print(f"range={config['auto_range_pct']} lvl={config['levels']} "
                  f"adx<{thr} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                  f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                  f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                  f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    import json
    with open("/tmp/claude-0/-home-user-binance-trader/e5fd3353-38f1-5fab-a651-e8d350a21d71/scratchpad/adx_grid_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved results to adx_grid_results.json")


if __name__ == "__main__":
    asyncio.run(main())
