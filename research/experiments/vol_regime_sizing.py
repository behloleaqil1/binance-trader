"""Research script (NOT production code): volatility-regime position sizing.

Hypothesis (Run 21, per Run 20's flagged next step (b)): 20 runs / ~207
configs of *entry/exit signal* tuning (per-symbol indicators, same-candle
gates, cross-TF gates, cross-symbol rotation/pairs) have all failed to find
edge on this 8-symbol/1h-4h/majors/long-only universe. Every gate mechanism
tried so far works by *excluding* trades in an unfavorable regime, which is
mechanically identical to further signal filtering and has always shown the
same train-improves/test-doesn't overfitting shape (relative-volume gate,
ADX gate, MTF gate). This experiment tries something structurally different
that has never been tested: instead of excluding trades, *rescale* their
size by the ATR-percentile volatility regime at entry, keeping the exact
same entry/exit signal (trend_momentum's shipped-default EMA/RSI/MACD
cross) untouched. Because profit factor is gross-win/gross-loss in dollar
terms, rescaling position size by a regime that correlates with trade
quality changes account-level PF even when the underlying win/loss trade
*count* and win-rate are identical to the baseline -- a lever no prior gate
experiment could exercise.

Mechanism: rolling ATR(14) as a % of close, ranked into a percentile over
the trailing `lookback` closed candles (no lookahead -- percentile uses only
current + past ATR values). At the entry candle, bucket into tertiles
(low/mid/high) and apply a size multiplier `mult_low`/`mult_mid`/`mult_high`
to the normal position_size_pct notional. Two opposing hypotheses tested:
  (A) high_boost: bigger size when volatility is HIGH (trend momentum edge,
      if any, should be more pronounced when the market is actually moving)
  (B) low_boost:  bigger size when volatility is LOW (calmer trend = less
      whipsaw risk on the same EMA cross)
Baseline (mult=1.0 everywhere) is included as a control -- it must reproduce
the exact same trades/PF as unmodified production trend_momentum @ 1h,
verifying this script's copy of run_candle_backtest introduces no drift.

Implemented as a standalone copy of run_candle_backtest (not a subclass --
sizing is a simulator-level concern, not a strategy-level one) with one
extra step: notional *= size_mult column, looked up at the entry candle.
Everything else (fees, slippage, stop-loss/take-profit, adaptive layer) is
copied verbatim from app/backtest/simulator.py. No production code touched.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import pandas as pd
from app.backtest.data import fetch_klines
from app.backtest.simulator import SimConfig, _fee, _slip
from app.core.types import PositionView, SignalAction
from app.risk.adaptive import evaluate_adaptive
from app.risk.models import RiskConfig
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.trend_momentum import TrendMomentumStrategy
from app.config import Settings
from app.db import database

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE", "ADA"]
FEE_BPS = 7.5
SLIP_BPS = 4.0
EQUITY = 10_000.0

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago
TEST_START, TEST_END = "2026-06-18", "2026-08-18"     # 60d-0d ago (today's anchor)
OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 20  # EMA/MACD/ATR warmup + percentile lookback


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def add_vol_regime(df: pd.DataFrame, atr_period: int, lookback: int) -> pd.DataFrame:
    out = df.copy()
    a = atr(out, atr_period)
    norm_atr = a / out["close"]
    # rolling percentile rank of the current value within the trailing
    # `lookback` window (inclusive), no lookahead -- rank() over an expanding
    # window would leak nothing but a fixed trailing window matches the
    # ADX/relative-volume gate methodology (own recent history only).
    out["vol_pctile"] = norm_atr.rolling(lookback, min_periods=lookback).apply(
        lambda w: (w.iloc[-1] >= w).mean(), raw=False)
    return out


def size_mult_for(pctile: float, mult_low: float, mult_mid: float, mult_high: float) -> float:
    if pd.isna(pctile):
        return 1.0
    if pctile < 1 / 3:
        return mult_low
    if pctile < 2 / 3:
        return mult_mid
    return mult_high


def run_candle_backtest_sized(strategy, risk: RiskConfig, df: pd.DataFrame,
                              cfg: SimConfig, mult_low: float, mult_mid: float,
                              mult_high: float, symbol: str = "SIM"):
    idf = strategy.compute_indicators(df)
    warmup = min(strategy.required_history(), max(len(df) - 2, 1))
    cash = cfg.initial_equity
    pos = None
    trades: list[dict] = []
    curve_ts, curve_val = [], []
    pending_entry = None
    pending_exit = None

    def close_trade(exit_price, ts, kind, reason):
        nonlocal cash, pos
        exit_fee = _fee(pos["qty"] * exit_price, cfg)
        cash += pos["qty"] * exit_price - exit_fee
        fees = pos["entry_fee"] + exit_fee
        pnl = pos["qty"] * (exit_price - pos["entry"]) - fees
        entry_value = pos["qty"] * pos["entry"]
        trades.append({"opened_at": pos["ts"], "closed_at": ts, "qty": round(pos["qty"], 10),
                       "entry": pos["entry"], "exit": exit_price, "pnl": round(pnl, 6),
                       "pnl_pct": round(pnl / entry_value * 100, 4) if entry_value else 0.0,
                       "fees": round(fees, 6), "exit_kind": kind,
                       "size_mult": pos["size_mult"],
                       "entry_reason": pos["reason"], "exit_reason": reason})
        pos = None

    for i in range(warmup, len(df)):
        row = idf.iloc[i]
        o, h, low, c, ts = (float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), int(row["open_time"]))

        if pending_exit and pos:
            close_trade(_slip(o, cfg, "SELL"), ts, "signal_exit", pending_exit)
        if pending_entry and pos is None:
            adaptive = evaluate_adaptive([t["pnl"] for t in trades], risk)
            if adaptive.paused:
                pending_entry = None
        if pending_entry and pos is None:
            fill = _slip(o, cfg, "BUY")
            smult = size_mult_for(float(row["vol_pctile"]) if not pd.isna(row["vol_pctile"]) else float("nan"),
                                  mult_low, mult_mid, mult_high)
            notional = min(cash * risk.position_size_pct / 100 * adaptive.size_multiplier * smult, cash)
            if notional > 1e-9 and fill > 0:
                qty = notional / fill
                entry_fee = _fee(notional, cfg)
                cash -= notional + entry_fee
                pos = {"qty": qty, "entry": fill, "ts": ts, "reason": pending_entry,
                       "entry_fee": entry_fee, "hwm": fill, "size_mult": smult,
                       "sl": fill * (1 - risk.stop_loss_pct / 100),
                       "tp": fill * (1 + risk.take_profit_pct / 100)}
        pending_entry = pending_exit = None

        if pos:
            sl_hit = low <= pos["sl"]
            tp_hit = h >= pos["tp"]
            if cfg.pessimistic and sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss", f"stop {pos['sl']:.6g} hit (low {low:.6g})")
            elif tp_hit:
                close_trade(max(pos["tp"], o), ts, "take_profit", f"take-profit {pos['tp']:.6g} hit (high {h:.6g})")
            elif sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss", f"stop {pos['sl']:.6g} hit (low {low:.6g})")

        if pos and risk.trailing_stop_enabled:
            pos["hwm"] = max(pos["hwm"], h)
            if pos["hwm"] >= pos["entry"] * (1 + risk.trailing_activation_pct / 100):
                pos["sl"] = max(pos["sl"], pos["hwm"] * (1 - risk.trailing_stop_pct / 100))

        view = (PositionView(0, symbol, strategy.id, pos["qty"], pos["entry"], c) if pos else None)
        sig = strategy.decide(symbol, idf, i, view)
        if sig.action == SignalAction.BUY and pos is None:
            pending_entry = sig.reason
        elif sig.action == SignalAction.SELL and pos is not None:
            pending_exit = sig.reason

        curve_ts.append(ts)
        curve_val.append(cash + (pos["qty"] * c if pos else 0.0))

    if pos:
        last = df.iloc[-1]
        close_trade(float(last["close"]), int(last["open_time"]), "end_of_backtest",
                    "backtest ended with position open")
        curve_val[-1] = cash
    equity = pd.Series(curve_val, index=curve_ts, dtype=float)
    return trades, equity


async def fetch_all(start, end, atr_period, lookback, tf):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        df = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
        out[sym] = add_vol_regime(df, atr_period, lookback)
    return out


def eval_window(dfs, start, end, strategy, risk, mult_low, mult_mid, mult_high, per_symbol=False):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        trades, eq = run_candle_backtest_sized(strategy, risk, df, cfg, mult_low, mult_mid, mult_high, symbol=sym)
        window_trades = [t for t in trades if start_ms <= t["opened_at"] < end_ms]
        all_trades.extend(window_trades)
        in_win = [(ts, v) for ts, v in zip(eq.index, eq.values) if start_ms <= ts < end_ms]
        ret = (in_win[-1][1] / in_win[0][1] - 1) * 100 if len(in_win) >= 2 else 0.0
        rets.append(ret)
        sw = [t for t in window_trades if t["pnl"] > 0]
        sl_ = [t for t in window_trades if t["pnl"] <= 0]
        gw, gl = sum(t["pnl"] for t in sw), -sum(t["pnl"] for t in sl_)
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


TM_PARAMS = {"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_buy_min": 50,
             "rsi_buy_max": 70, "rsi_exit": 78, "macd_fast": 12, "macd_slow": 26,
             "macd_signal": 9, "require_macd": True}
MR_PARAMS = {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14, "rsi_oversold": 30,
             "rsi_overbought": 70, "exit_at": "middle", "trend_ema": 0}

SIZING_CONFIGS = [
    {"label": "baseline (mult=1 everywhere, control)", "mults": (1.0, 1.0, 1.0)},
    {"label": "high_boost (1.5x high-vol, 0.5x low-vol)", "mults": (0.5, 1.0, 1.5)},
    {"label": "low_boost (1.5x low-vol, 0.5x high-vol)", "mults": (1.5, 1.0, 0.5)},
    {"label": "high_boost_strong (2.0x high-vol, 0.25x low-vol)", "mults": (0.25, 1.0, 2.0)},
    {"label": "low_boost_strong (2.0x low-vol, 0.25x high-vol)", "mults": (2.0, 1.0, 0.25)},
]


def make_strategy(family: str, tf: str):
    if family == "trend_momentum":
        return TrendMomentumStrategy({"timeframe": tf, **TM_PARAMS})
    return MeanReversionStrategy({"timeframe": tf, **MR_PARAMS})


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk = RiskConfig()
    atr_period, lookback = 14, 100

    # Three base signals so the conclusion is about the SIZING LEVER, not one
    # signal: two families x two TFs, all previously closed as no-edge on
    # their own. If regime sizing can rescue any of them, it shows up as a
    # test-PF lift vs that base's own mult=1 control.
    bases = [
        {"family": "trend_momentum", "tf": "1h"},
        {"family": "trend_momentum", "tf": "4h"},
        {"family": "mean_reversion", "tf": "1h"},
    ]

    results = []
    cache: dict[str, dict] = {}
    for b in bases:
        tf = b["tf"]
        strategy = make_strategy(b["family"], tf)
        if tf not in cache:
            print(f"Fetching {tf} windows (ATR({atr_period}) pctile over trailing {lookback})...")
            cache[tf] = {
                "train": await fetch_all(TRAIN_START, TRAIN_END, atr_period, lookback, tf),
                "test": await fetch_all(TEST_START, TEST_END, atr_period, lookback, tf),
            }
        train_dfs, test_dfs = cache[tf]["train"], cache[tf]["test"]
        print(f"\n=== {b['family']} @ {tf} ===")
        for c in SIZING_CONFIGS:
            ml, mm, mh = c["mults"]
            train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, strategy, risk, ml, mm, mh)
            test_m = eval_window(test_dfs, TEST_START, TEST_END, strategy, risk, ml, mm, mh)
            row = {"family": b["family"], "tf": tf, "label": c["label"],
                   "mults": c["mults"], "train": train_m, "test": test_m}
            results.append(row)
            print(f"{c['label']} | TRAIN pf={train_m['pf']} win%={train_m['win_pct']} "
                  f"n={train_m['trades']} ret%={train_m['avg_ret_pct']} || "
                  f"TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                  f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    # 3rd non-overlapping window + per-symbol breakdown for any non-control
    # config that clears the OOS screen on TEST (test pf>1.1, n>=30).
    near_misses = [r for r in results if (r["test"]["pf"] or 0) > 1.1 and r["test"]["trades"] >= 30
                   and not r["label"].startswith("baseline")]
    if near_misses:
        print(f"\n{len(near_misses)} config(s) cleared the OOS screen -- 3rd window + per-symbol...")
        older_cache: dict[str, dict] = {}
        for r in near_misses:
            tf = r["tf"]
            if tf not in older_cache:
                older_cache[tf] = await fetch_all(OLDER_START, OLDER_END, atr_period, lookback, tf)
            strategy = make_strategy(r["family"], tf)
            ml, mm, mh = r["mults"]
            older_m = eval_window(older_cache[tf], OLDER_START, OLDER_END, strategy, risk, ml, mm, mh, per_symbol=True)
            test_ps = eval_window(cache[tf]["test"], TEST_START, TEST_END, strategy, risk, ml, mm, mh, per_symbol=True)
            r["older"] = older_m
            r["test_per_symbol"] = test_ps["per_symbol"]
            print(f"{r['family']}@{tf} {r['label']} OLDER window: pf={older_m['pf']} "
                  f"win%={older_m['win_pct']} n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            print(f"  Per-symbol TEST: {test_ps['per_symbol']}")
    else:
        print("\nNo config cleared the OOS screen -- no 3rd-window check needed.")

    import json
    out_path = "/tmp/claude-0/-home-user-binance-trader/16d89351-a0f3-5079-9153-462a47d34f85/scratchpad/vol_regime_sizing_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
