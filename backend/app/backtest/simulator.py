"""Event-driven backtest simulators.

Fidelity rules:
  • Candle strategies run the exact same compute_indicators()/decide() code as
    live trading; decisions at candle close execute at the NEXT candle open
    (no lookahead), with slippage and taker fees applied.
  • Protective SL/TP are checked intra-candle via high/low. When both could
    fill in one candle the pessimistic assumption (stop first) is used.
  • Grid and DCA reuse the same ladder/schedule math as the live engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from app.core.types import PositionView, SignalAction
from app.risk.adaptive import evaluate_adaptive
from app.risk.models import RiskConfig
from app.strategies.base import Strategy
from app.strategies.dca import DCAStrategy
from app.strategies.grid import GridStrategy


@dataclass(slots=True)
class SimConfig:
    initial_equity: float = 10_000.0
    fee_bps: float = 10.0        # 0.10% taker
    slippage_bps: float = 5.0    # 0.05% adverse fill on market orders
    pessimistic: bool = True     # SL before TP when both hit in one candle


@dataclass(slots=True)
class SimResult:
    equity: pd.Series            # indexed by open_time ms
    trades: list[dict]
    extras: dict


def _fee(notional: float, cfg: SimConfig) -> float:
    return abs(notional) * cfg.fee_bps / 10_000


def _slip(price: float, cfg: SimConfig, side: str) -> float:
    s = cfg.slippage_bps / 10_000
    return price * (1 + s) if side == "BUY" else price * (1 - s)


# ── trend / mean-reversion (any "candle" strategy) ──────────────────────────
def run_candle_backtest(strategy: Strategy, risk: RiskConfig, df: pd.DataFrame,
                        cfg: SimConfig, symbol: str = "SIM") -> SimResult:
    idf = strategy.compute_indicators(df)
    warmup = min(strategy.required_history(), max(len(df) - 2, 1))
    cash = cfg.initial_equity
    pos: dict | None = None
    trades: list[dict] = []
    curve_ts: list[int] = []
    curve_val: list[float] = []
    pending_entry: str | None = None
    pending_exit: str | None = None
    adaptive_blocked = 0

    def close_trade(exit_price: float, ts: int, kind: str, reason: str) -> None:
        nonlocal cash, pos
        exit_fee = _fee(pos["qty"] * exit_price, cfg)
        cash += pos["qty"] * exit_price - exit_fee
        fees = pos["entry_fee"] + exit_fee
        pnl = pos["qty"] * (exit_price - pos["entry"]) - fees
        entry_value = pos["qty"] * pos["entry"]
        trades.append({
            "opened_at": pos["ts"], "closed_at": ts, "qty": round(pos["qty"], 10),
            "entry": pos["entry"], "exit": exit_price, "pnl": round(pnl, 6),
            "pnl_pct": round(pnl / entry_value * 100, 4) if entry_value else 0.0,
            "fees": round(fees, 6), "exit_kind": kind,
            "entry_reason": pos["reason"], "exit_reason": reason})
        pos = None

    for i in range(warmup, len(df)):
        row = df.iloc[i]
        o, h, low, c, ts = (float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), int(row["open_time"]))

        # 1) execute decisions made at the previous close
        if pending_exit and pos:
            close_trade(_slip(o, cfg, "SELL"), ts, "signal_exit", pending_exit)
        if pending_entry and pos is None:
            # Same adaptive layer as live: losing streaks shrink size,
            # probation blocks the entry entirely.
            adaptive = evaluate_adaptive([t["pnl"] for t in trades], risk)
            if adaptive.paused:
                adaptive_blocked += 1
                pending_entry = None
        if pending_entry and pos is None:
            fill = _slip(o, cfg, "BUY")
            notional = min(cash * risk.position_size_pct / 100
                           * adaptive.size_multiplier, cash)
            if notional > 1e-9 and fill > 0:
                qty = notional / fill
                entry_fee = _fee(notional, cfg)
                cash -= notional + entry_fee
                pos = {"qty": qty, "entry": fill, "ts": ts, "reason": pending_entry,
                       "entry_fee": entry_fee, "hwm": fill,
                       "sl": fill * (1 - risk.stop_loss_pct / 100),
                       "tp": fill * (1 + risk.take_profit_pct / 100)}
        pending_entry = pending_exit = None

        # 2) intra-candle protective exits (stop checked first = pessimistic)
        if pos:
            sl_hit = low <= pos["sl"]
            tp_hit = h >= pos["tp"]
            if cfg.pessimistic and sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss",
                            f"stop {pos['sl']:.6g} hit (low {low:.6g})")
            elif tp_hit:
                close_trade(max(pos["tp"], o), ts, "take_profit",
                            f"take-profit {pos['tp']:.6g} hit (high {h:.6g})")
            elif sl_hit:
                close_trade(min(pos["sl"], o), ts, "stop_loss",
                            f"stop {pos['sl']:.6g} hit (low {low:.6g})")

        # 3) trailing stop ratchets for the NEXT candle
        if pos and risk.trailing_stop_enabled:
            pos["hwm"] = max(pos["hwm"], h)
            if pos["hwm"] >= pos["entry"] * (1 + risk.trailing_activation_pct / 100):
                pos["sl"] = max(pos["sl"], pos["hwm"] * (1 - risk.trailing_stop_pct / 100))

        # 4) strategy decision at candle close
        view = (PositionView(0, symbol, strategy.id, pos["qty"], pos["entry"], c)
                if pos else None)
        sig = strategy.decide(symbol, idf, i, view)
        if sig.action == SignalAction.BUY and pos is None:
            pending_entry = sig.reason
        elif sig.action == SignalAction.SELL and pos is not None:
            pending_exit = sig.reason

        curve_ts.append(ts)
        curve_val.append(cash + (pos["qty"] * c if pos else 0.0))

    if pos:  # liquidate at the last close so every trade is a closed round-trip
        last = df.iloc[-1]
        close_trade(float(last["close"]), int(last["open_time"]),
                    "end_of_backtest", "backtest ended with position open")
        curve_val[-1] = cash
    equity = pd.Series(curve_val, index=curve_ts, dtype=float)
    return SimResult(equity, trades, {"warmup": warmup,
                                      "adaptive_blocked_entries": adaptive_blocked})


# ── grid ────────────────────────────────────────────────────────────────────
def run_grid_backtest(strategy: GridStrategy, df: pd.DataFrame,
                      cfg: SimConfig) -> SimResult:
    p = strategy.params
    first_close = float(df["close"].iloc[0])
    levels = strategy.levels(first_close)
    cash = cfg.initial_equity
    lots: dict[int, dict] = {}          # level -> {qty, cost, fee, ts}
    trades: list[dict] = []
    curve_ts: list[int] = []
    curve_val: list[float] = []
    skipped_no_cash = 0
    paused_at: int | None = None
    prev_close = first_close

    for i in range(len(df)):
        row = df.iloc[i]
        o, h, low, c, ts = (float(row["open"]), float(row["high"]), float(row["low"]),
                            float(row["close"]), int(row["open_time"]))
        if paused_at is None:
            # Buy fills: ladder levels below the previous close whose price traded.
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
            # Sell fills: each lot exits one level up.
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
    extras = {"warmup": 0, "grid_levels": [round(x, 8) for x in levels],
              "open_lots_at_end": len(lots), "skipped_no_cash": skipped_no_cash,
              "paused_at": paused_at}
    return SimResult(equity, trades, extras)


# ── DCA ─────────────────────────────────────────────────────────────────────
def run_dca_backtest(strategy: DCAStrategy, df: pd.DataFrame,
                     cfg: SimConfig, timeframe_ms: int) -> SimResult:
    cash = cfg.initial_equity
    qty_held = 0.0
    invested = 0.0
    buys: list[dict] = []
    curve_ts: list[int] = []
    curve_val: list[float] = []
    last_run: datetime | None = None
    lookback = max(1, 86_400_000 // timeframe_ms)  # candles in 24h

    for i in range(len(df)):
        row = df.iloc[i]
        o, c, ts = float(row["open"]), float(row["close"]), int(row["open_time"])
        now = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        if strategy.is_due(last_run, now):
            last_run = now
            change_pct = None
            if i >= lookback + 1:  # latest known close vs the close 24h before it
                ref = float(df["close"].iloc[i - 1 - lookback])
                prev = float(df["close"].iloc[i - 1])
                change_pct = (prev / ref - 1) * 100 if ref else None
            sig = strategy.build_signal("SIM", change_pct)
            amount = float(sig.notional_override or 0.0)
            fill = _slip(o, cfg, "BUY")
            fee = _fee(amount, cfg)
            if cash >= amount + fee and amount > 0 and fill > 0:
                cash -= amount + fee
                bought = amount / fill
                qty_held += bought
                invested += amount
                buys.append({"ts": ts, "price": fill, "amount": amount,
                             "qty": bought, "reason": sig.reason})
        curve_ts.append(ts)
        curve_val.append(cash + qty_held * c)

    equity = pd.Series(curve_val, index=curve_ts, dtype=float)
    last_close = float(df["close"].iloc[-1]) if len(df) else 0.0
    avg_cost = invested / qty_held if qty_held else 0.0
    extras = {"warmup": 0, "dca_buys": len(buys), "invested": round(invested, 2),
              "qty_accumulated": round(qty_held, 10),
              "avg_cost": round(avg_cost, 6),
              "unrealized_pnl": round(qty_held * last_close - invested, 4),
              "buys": buys[-200:]}
    return SimResult(equity, [], extras)
