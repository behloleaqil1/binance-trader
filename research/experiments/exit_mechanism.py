"""Research script (NOT production code): the EXIT-mechanism axis (Run 22).

Every prior run (1-21) has varied *which trades are taken* (entry signal,
timeframe, gate, cross-symbol construction) or *how big they are* (Run 21,
sizing). None has ever varied the EXIT mechanism. Risk config (stop-loss 2%,
take-profit 4%, daily-loss halt, drawdown kill switch, position caps) has
been held at repo defaults throughout. This run opens that axis with two
sub-experiments, both layered onto previously-closed base signals so the
comparison isolates the exit change:

(A) Time-based forced exit (`max_hold_bars`): if a position is still open N
    candles after entry, force-close it at market on the NEXT candle's open
    (same no-lookahead fill convention the simulator already uses for
    strategy-signalled exits), regardless of what the strategy's own SELL
    logic would otherwise decide. SL/TP remain fully active and checked
    intra-candle FIRST every bar, so they can still fire before the cap ever
    would -- this only bounds worst-case holding time, it does not loosen
    any existing control. Implemented as `run_candle_backtest_capped`, a
    standalone copy of app/backtest/simulator.run_candle_backtest with
    exactly one addition (the forced-exit check). The max_hold_bars=None
    control is verified trade-for-trade identical to unmodified production
    run_candle_backtest before any deltas are trusted.

(B) Tighter SL/TP (secondary): production run_candle_backtest is already
    parameterized by RiskConfig, so this needs no new simulator code -- just
    pass a RiskConfig with stop_loss_pct<=2.0 and take_profit_pct<=4.0
    (never wider, per the hard limit) directly to production
    run_candle_backtest.

Bases: trend_momentum@1h and mean_reversion@1h, both at shipped-default
params, both deeply characterized in decisions.jsonl already. Same
train/test/older windows Run 21 used (for direct comparability with its
recorded control numbers): train 2026-03-19..2026-06-18, test
2026-06-18..2026-08-18, older 2025-12-19..2026-03-19.
"""
import asyncio
import sys
sys.path.insert(0, ".")

import json

import pandas as pd
from app.backtest.data import fetch_klines, interval_ms
from app.backtest.simulator import SimConfig, _fee, _slip, run_candle_backtest
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

TRAIN_START, TRAIN_END = "2026-03-19", "2026-06-18"   # 150d-60d ago (Run 21's window)
TEST_START, TEST_END = "2026-06-18", "2026-08-18"     # 60d-0d ago (Run 21's window)
OLDER_START, OLDER_END = "2025-12-19", "2026-03-19"   # 240d-150d ago (3rd window)
BUFFER_DAYS = 20  # EMA/MACD/BB warmup (matches Run 21's buffer, for comparability)
SCRATCH = "/tmp/claude-0/-home-user-binance-trader/a03bd0d6-670a-5e8b-9dd3-dd6b28efe8d5/scratchpad"


# ── (A) time-based forced exit: standalone copy of run_candle_backtest ──────
def run_candle_backtest_capped(strategy, risk: RiskConfig, df: pd.DataFrame,
                               cfg: SimConfig, max_hold_bars: int | None,
                               symbol: str = "SIM"):
    idf = strategy.compute_indicators(df)
    warmup = min(strategy.required_history(), max(len(df) - 2, 1))
    cash = cfg.initial_equity
    pos: dict | None = None
    trades: list[dict] = []
    curve_ts: list[int] = []
    curve_val: list[float] = []
    pending_entry: str | None = None
    pending_exit: str | None = None

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
                       "held_bars": None,  # filled below before pos is cleared
                       "entry_reason": pos["reason"], "exit_reason": reason})
        pos = None

    for i in range(warmup, len(df)):
        row = idf.iloc[i]
        o, h, low, c, ts = (float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), int(row["open_time"]))

        # 1) execute decisions made at the previous close
        if pending_exit and pos:
            held = i - pos["entry_idx"]
            trades_before = len(trades)
            close_trade(_slip(o, cfg, "SELL"), ts, "signal_exit", pending_exit)
            if len(trades) > trades_before:
                trades[-1]["held_bars"] = held
        if pending_entry and pos is None:
            adaptive = evaluate_adaptive([t["pnl"] for t in trades], risk)
            if adaptive.paused:
                pending_entry = None
        if pending_entry and pos is None:
            fill = _slip(o, cfg, "BUY")
            notional = min(cash * risk.position_size_pct / 100 * adaptive.size_multiplier, cash)
            if notional > 1e-9 and fill > 0:
                qty = notional / fill
                entry_fee = _fee(notional, cfg)
                cash -= notional + entry_fee
                pos = {"qty": qty, "entry": fill, "ts": ts, "reason": pending_entry,
                       "entry_fee": entry_fee, "hwm": fill, "entry_idx": i,
                       "sl": fill * (1 - risk.stop_loss_pct / 100),
                       "tp": fill * (1 + risk.take_profit_pct / 100)}
        pending_entry = pending_exit = None

        # 2) intra-candle protective exits (stop checked first = pessimistic)
        #    UNCHANGED from production -- SL/TP still fire before the max-hold
        #    cap ever gets a chance to.
        if pos:
            sl_hit = low <= pos["sl"]
            tp_hit = h >= pos["tp"]
            held = i - pos["entry_idx"]
            if cfg.pessimistic and sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss", f"stop {pos['sl']:.6g} hit (low {low:.6g})")
                trades[-1]["held_bars"] = held
            elif tp_hit:
                close_trade(max(pos["tp"], o), ts, "take_profit", f"take-profit {pos['tp']:.6g} hit (high {h:.6g})")
                trades[-1]["held_bars"] = held
            elif sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss", f"stop {pos['sl']:.6g} hit (low {low:.6g})")
                trades[-1]["held_bars"] = held

        # 3) trailing stop ratchets for the NEXT candle
        if pos and risk.trailing_stop_enabled:
            pos["hwm"] = max(pos["hwm"], h)
            if pos["hwm"] >= pos["entry"] * (1 + risk.trailing_activation_pct / 100):
                pos["sl"] = max(pos["sl"], pos["hwm"] * (1 - risk.trailing_stop_pct / 100))

        # 4) strategy decision at candle close
        view = (PositionView(0, symbol, strategy.id, pos["qty"], pos["entry"], c) if pos else None)
        sig = strategy.decide(symbol, idf, i, view)
        if sig.action == SignalAction.BUY and pos is None:
            pending_entry = sig.reason
        elif sig.action == SignalAction.SELL and pos is not None:
            pending_exit = sig.reason

        # 4b) NEW: time-based forced exit. Overrides whatever the strategy
        # decided (or didn't) this candle -- fires at the NEXT candle's open,
        # same fill convention as every other signal exit. SL/TP have already
        # had first crack at this candle above (step 2), so they still win
        # any race; this only bounds worst-case holding time when neither
        # SL/TP nor the strategy's own exit logic has fired by bar N.
        if pos and max_hold_bars is not None:
            held_now = i - pos["entry_idx"]
            if held_now >= max_hold_bars:
                pending_exit = f"max_hold: held {held_now} bars >= cap {max_hold_bars}"

        curve_ts.append(ts)
        curve_val.append(cash + (pos["qty"] * c if pos else 0.0))

    if pos:
        last = df.iloc[-1]
        held = len(df) - 1 - pos["entry_idx"]
        close_trade(float(last["close"]), int(last["open_time"]),
                    "end_of_backtest", "backtest ended with position open")
        trades[-1]["held_bars"] = held
        curve_val[-1] = cash
    equity = pd.Series(curve_val, index=curve_ts, dtype=float)
    return trades, equity


async def fetch_all(start, end, tf):
    buf_start = (pd.Timestamp(start, tz="UTC") - pd.Timedelta(days=BUFFER_DAYS)).isoformat()
    out = {}
    for sym in SYMBOLS:
        out[sym] = await fetch_klines(f"{sym}USDT", tf, buf_start, end)
    return out


def eval_window(dfs, start, end, strategy, risk, max_hold_bars, per_symbol=False):
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        trades, eq = run_candle_backtest_capped(strategy, risk, df, cfg, max_hold_bars, symbol=sym)
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
    held = [t["held_bars"] for t in all_trades if t.get("held_bars") is not None]
    out = {"pf": round(pf, 3) if pf != float("inf") else None, "win_pct": round(win_pct, 2),
           "trades": len(all_trades), "avg_ret_pct": round(avg_ret, 4),
           "avg_held_bars": round(sum(held) / len(held), 2) if held else None}
    if per_symbol:
        out["per_symbol"] = sym_stats
    return out


def eval_window_prod(dfs, start, end, strategy, risk, per_symbol=False):
    """Production run_candle_backtest, for (B) SL/TP variants and the control check."""
    cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    all_trades, rets = [], []
    sym_stats = {}
    for sym, df in dfs.items():
        res = run_candle_backtest(strategy, risk, df, cfg, symbol=sym)
        trades, eq = res.trades, res.equity
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


def make_strategy(family: str, tf: str):
    if family == "trend_momentum":
        return TrendMomentumStrategy({"timeframe": tf, **TM_PARAMS})
    return MeanReversionStrategy({"timeframe": tf, **MR_PARAMS})


async def main():
    settings = Settings()
    database.init_engine(settings)
    await database.create_all_and_seed(settings)
    risk_default = RiskConfig()
    tf = "1h"

    print(f"Fetching {tf} windows...")
    train_dfs = await fetch_all(TRAIN_START, TRAIN_END, tf)
    test_dfs = await fetch_all(TEST_START, TEST_END, tf)

    bases = [
        {"family": "trend_momentum", "tf": tf},
        {"family": "mean_reversion", "tf": tf},
    ]

    # ── Control validation: max_hold_bars=None copy vs unmodified production ──
    print("\n=== Control validation (max_hold_bars=None vs production run_candle_backtest) ===")
    for b in bases:
        strategy = make_strategy(b["family"], tf)
        cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
        df_btc = train_dfs["BTC"]
        prod = run_candle_backtest(strategy, risk_default, df_btc, cfg, symbol="BTC")
        capped_trades, capped_eq = run_candle_backtest_capped(
            strategy, risk_default, df_btc, cfg, None, symbol="BTC")
        match = (len(prod.trades) == len(capped_trades) and
                 all(pt["opened_at"] == ct["opened_at"] and pt["closed_at"] == ct["closed_at"]
                     and abs(pt["pnl"] - ct["pnl"]) < 1e-6
                     for pt, ct in zip(prod.trades, capped_trades)) and
                 abs(float(prod.equity.iloc[-1]) - float(capped_eq.iloc[-1])) < 1e-6)
        print(f"{b['family']}@{tf} BTCUSDT train: prod n={len(prod.trades)} "
              f"final_eq={prod.equity.iloc[-1]:.4f} | capped(None) n={len(capped_trades)} "
              f"final_eq={capped_eq.iloc[-1]:.4f} -> {'MATCH' if match else 'MISMATCH -- ABORT'}")
        assert match, f"Control validation FAILED for {b['family']}@{tf} -- do not trust deltas"

    # ── Holding-duration profile of the no-cap baseline (train window), to
    # pick sensible max_hold_bars sweep values instead of guessing blindly ──
    print("\n=== No-cap baseline holding-duration profile (TRAIN window) ===")
    duration_info = {}
    for b in bases:
        strategy = make_strategy(b["family"], tf)
        base = eval_window(train_dfs, TRAIN_START, TRAIN_END, strategy, risk_default, None)
        # per-trade durations across all symbols in the train window
        cfg = SimConfig(initial_equity=EQUITY, fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
        start_ms = int(pd.Timestamp(TRAIN_START, tz="UTC").timestamp() * 1000)
        end_ms = int(pd.Timestamp(TRAIN_END, tz="UTC").timestamp() * 1000)
        all_durs = []
        for sym, df in train_dfs.items():
            trades, _ = run_candle_backtest_capped(strategy, risk_default, df, cfg, None, symbol=sym)
            all_durs.extend(t["held_bars"] for t in trades
                            if start_ms <= t["opened_at"] < end_ms and t["held_bars"] is not None)
        s = pd.Series(all_durs, dtype=float)
        info = {"n": len(s), "mean": round(float(s.mean()), 1) if len(s) else None,
                "median": round(float(s.median()), 1) if len(s) else None,
                "p25": round(float(s.quantile(0.25)), 1) if len(s) else None,
                "p75": round(float(s.quantile(0.75)), 1) if len(s) else None,
                "p90": round(float(s.quantile(0.90)), 1) if len(s) else None,
                "max": round(float(s.max()), 1) if len(s) else None}
        duration_info[b["family"]] = info
        print(f"{b['family']}@{tf} TRAIN held_bars (n={info['n']}): mean={info['mean']} "
              f"median={info['median']} p25={info['p25']} p75={info['p75']} p90={info['p90']} max={info['max']}")
        print(f"  (no-cap baseline for reference: pf={base['pf']} win%={base['win_pct']} n={base['trades']})")

    import json as _json
    with open(SCRATCH + "/duration_profile.json", "w") as f:
        _json.dump(duration_info, f, indent=2)
    print("\nSaved duration profile.")

    # ── (A) max_hold_bars sweep, data-driven per base (not blind 12/24/48/96
    # for both -- their holding-time distributions differ by ~2x) ──
    HOLD_SWEEP = {
        "trend_momentum": [8, 16, 33, 52],   # ~ P25/median/P75/P90 of its own no-cap train durations
        "mean_reversion": [6, 11, 17, 24],   # ~ P25/median/P75/just-above-P90 of its own no-cap train durations
    }

    all_results = {"duration_profile": duration_info, "exp_a": [], "exp_b": []}

    print("\n=== (A) Time-based forced exit sweep ===")
    for b in bases:
        strategy = make_strategy(b["family"], tf)
        # control row (no cap) -- reference, already computed above but record formally
        ctrl_train = eval_window(train_dfs, TRAIN_START, TRAIN_END, strategy, risk_default, None)
        ctrl_test = eval_window(test_dfs, TEST_START, TEST_END, strategy, risk_default, None)
        row = {"family": b["family"], "tf": tf, "max_hold_bars": None,
               "train": ctrl_train, "test": ctrl_test}
        all_results["exp_a"].append(row)
        print(f"{b['family']}@{tf} max_hold=None (control) | TRAIN pf={ctrl_train['pf']} "
              f"win%={ctrl_train['win_pct']} n={ctrl_train['trades']} ret%={ctrl_train['avg_ret_pct']} "
              f"avg_held={ctrl_train['avg_held_bars']} || TEST pf={ctrl_test['pf']} "
              f"win%={ctrl_test['win_pct']} n={ctrl_test['trades']} ret%={ctrl_test['avg_ret_pct']} "
              f"avg_held={ctrl_test['avg_held_bars']}")

        for n in HOLD_SWEEP[b["family"]]:
            train_m = eval_window(train_dfs, TRAIN_START, TRAIN_END, strategy, risk_default, n)
            test_m = eval_window(test_dfs, TEST_START, TEST_END, strategy, risk_default, n)
            row = {"family": b["family"], "tf": tf, "max_hold_bars": n,
                   "train": train_m, "test": test_m}
            all_results["exp_a"].append(row)
            print(f"{b['family']}@{tf} max_hold={n} | TRAIN pf={train_m['pf']} "
                  f"win%={train_m['win_pct']} n={train_m['trades']} ret%={train_m['avg_ret_pct']} "
                  f"avg_held={train_m['avg_held_bars']} || TEST pf={test_m['pf']} "
                  f"win%={test_m['win_pct']} n={test_m['trades']} ret%={test_m['avg_ret_pct']} "
                  f"avg_held={test_m['avg_held_bars']}")

    older_dfs = None
    # near-miss escalation for (A): test pf>1.1 and n>=30, non-control
    near_misses_a = [r for r in all_results["exp_a"]
                      if r["max_hold_bars"] is not None
                      and (r["test"]["pf"] or 0) > 1.1 and r["test"]["trades"] >= 30]
    if near_misses_a:
        print(f"\n{len(near_misses_a)} (A) config(s) cleared the OOS screen -- 3rd window + per-symbol...")
        older_dfs = await fetch_all(OLDER_START, OLDER_END, tf)
        for r in near_misses_a:
            strategy = make_strategy(r["family"], tf)
            older_m = eval_window(older_dfs, OLDER_START, OLDER_END, strategy, risk_default,
                                  r["max_hold_bars"], per_symbol=True)
            test_ps = eval_window(test_dfs, TEST_START, TEST_END, strategy, risk_default,
                                  r["max_hold_bars"], per_symbol=True)
            r["older"] = older_m
            r["test_per_symbol"] = test_ps["per_symbol"]
            print(f"{r['family']}@{tf} max_hold={r['max_hold_bars']} OLDER window: "
                  f"pf={older_m['pf']} win%={older_m['win_pct']} n={older_m['trades']} "
                  f"ret%={older_m['avg_ret_pct']}")
            print(f"  Per-symbol TEST: {test_ps['per_symbol']}")
    else:
        print("\nNo (A) config cleared the OOS screen -- no 3rd-window check needed.")

    # ── (B) tighter SL/TP variants (secondary) -- production run_candle_backtest,
    # RiskConfig only, no new simulator code. Hard limit: SL<=2.0, TP<=4.0, never wider. ──
    print("\n=== (B) Tighter SL/TP sweep (production run_candle_backtest, RiskConfig only) ===")
    SLTP_SWEEP = [
        {"label": "control (2.0/4.0, shipped default)", "sl": 2.0, "tp": 4.0},
        {"label": "tight_75pct (1.5/3.0)", "sl": 1.5, "tp": 3.0},
        {"label": "tight_50pct (1.0/2.0)", "sl": 1.0, "tp": 2.0},
        {"label": "tight_sl_only (1.5/4.0)", "sl": 1.5, "tp": 4.0},
    ]
    for b in bases:
        strategy = make_strategy(b["family"], tf)
        for c in SLTP_SWEEP:
            assert c["sl"] <= 2.0 and c["tp"] <= 4.0, "HARD LIMIT: never test SL/TP wider than shipped default"
            risk = RiskConfig(stop_loss_pct=c["sl"], take_profit_pct=c["tp"])
            train_m = eval_window_prod(train_dfs, TRAIN_START, TRAIN_END, strategy, risk)
            test_m = eval_window_prod(test_dfs, TEST_START, TEST_END, strategy, risk)
            row = {"family": b["family"], "tf": tf, "sl": c["sl"], "tp": c["tp"], "label": c["label"],
                   "train": train_m, "test": test_m}
            all_results["exp_b"].append(row)
            print(f"{b['family']}@{tf} SL/TP={c['sl']}/{c['tp']} ({c['label']}) | "
                  f"TRAIN pf={train_m['pf']} win%={train_m['win_pct']} n={train_m['trades']} "
                  f"ret%={train_m['avg_ret_pct']} || TEST pf={test_m['pf']} win%={test_m['win_pct']} "
                  f"n={test_m['trades']} ret%={test_m['avg_ret_pct']}")

    near_misses_b = [r for r in all_results["exp_b"]
                      if not r["label"].startswith("control")
                      and (r["test"]["pf"] or 0) > 1.1 and r["test"]["trades"] >= 30]
    if near_misses_b:
        print(f"\n{len(near_misses_b)} (B) config(s) cleared the OOS screen -- 3rd window + per-symbol...")
        if older_dfs is None:
            older_dfs = await fetch_all(OLDER_START, OLDER_END, tf)
        for r in near_misses_b:
            strategy = make_strategy(r["family"], tf)
            risk = RiskConfig(stop_loss_pct=r["sl"], take_profit_pct=r["tp"])
            older_m = eval_window_prod(older_dfs, OLDER_START, OLDER_END, strategy, risk, per_symbol=True)
            test_ps = eval_window_prod(test_dfs, TEST_START, TEST_END, strategy, risk, per_symbol=True)
            r["older"] = older_m
            r["test_per_symbol"] = test_ps["per_symbol"]
            print(f"{r['family']}@{tf} SL/TP={r['sl']}/{r['tp']} OLDER window: pf={older_m['pf']} "
                  f"win%={older_m['win_pct']} n={older_m['trades']} ret%={older_m['avg_ret_pct']}")
            print(f"  Per-symbol TEST: {test_ps['per_symbol']}")
    else:
        print("\nNo (B) config cleared the OOS screen -- no 3rd-window check needed.")

    with open(SCRATCH + "/exit_mechanism_results.json", "w") as f:
        _json.dump(all_results, f, indent=2)
    print(f"\nSaved full results to {SCRATCH}/exit_mechanism_results.json")


if __name__ == "__main__":
    asyncio.run(main())
