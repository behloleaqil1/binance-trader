"""The risk engine — the single gate between strategy signals and the exchange.

Design rules:
  • Pure, synchronous, side-effect-free: takes snapshots in, returns a
    RiskDecision out. That makes it trivially unit-testable and reusable
    verbatim by the backtester.
  • No order reaches the exchange without an approved RiskDecision. The order
    manager takes an OrderPlan, and only this module produces OrderPlans for
    entries.
  • Every check that ran is recorded in decision.checks for the audit log.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.symbol_rules import SymbolRules
from app.core.types import (AccountState, BotStatus, OrderPlan, OrderPurpose,
                            RiskDecision, Signal)
from app.risk.models import RiskConfig


@dataclass(slots=True)
class LimitBreach:
    kind: str          # "DAILY_LOSS" | "DRAWDOWN"
    message: str
    value_pct: float
    limit_pct: float


class RiskEngine:
    def __init__(self, config: RiskConfig):
        self.config = config

    # ── global circuit breakers (evaluated on every equity update) ──────────
    def check_daily_loss(self, acct: AccountState) -> LimitBreach | None:
        loss = acct.daily_loss_pct
        if loss >= self.config.max_daily_loss_pct:
            return LimitBreach(
                "DAILY_LOSS",
                f"daily loss {loss:.2f}% ≥ limit {self.config.max_daily_loss_pct}% — "
                f"halting new entries until next UTC day",
                loss, self.config.max_daily_loss_pct)
        return None

    def check_drawdown(self, acct: AccountState) -> LimitBreach | None:
        if not self.config.kill_switch_enabled:
            return None
        dd = acct.drawdown_pct
        if dd >= self.config.max_drawdown_pct:
            return LimitBreach(
                "DRAWDOWN",
                f"drawdown {dd:.2f}% from peak equity ≥ limit "
                f"{self.config.max_drawdown_pct}% — KILL SWITCH: trading stopped, "
                f"manual reset required",
                dd, self.config.max_drawdown_pct)
        return None

    # ── entry evaluation ────────────────────────────────────────────────────
    def evaluate_entry(self, signal: Signal, price: float, acct: AccountState,
                       rules: SymbolRules,
                       purpose: OrderPurpose = OrderPurpose.ENTRY,
                       order_type: str = "MARKET",
                       limit_price: float | None = None,
                       size_multiplier: float = 1.0) -> RiskDecision:
        cfg = self.config
        checks: list[str] = []

        def reject(reason: str) -> RiskDecision:
            return RiskDecision(False, reason, None, checks)

        # 1) engine state gates
        if acct.status == BotStatus.KILLED:
            return reject("kill switch active — manual reset required")
        if acct.status == BotStatus.DAILY_HALT:
            return reject("daily loss limit reached — entries halted until next UTC day")
        if acct.status not in (BotStatus.RUNNING,):
            return reject(f"bot is {acct.status.value} — entries only while RUNNING")
        checks.append("state=RUNNING")

        if rules.status != "TRADING":
            return reject(f"{signal.symbol} not tradable (status {rules.status})")
        if price <= 0:
            return reject("no valid price for symbol")
        checks.append("symbol tradable")

        # 2) circuit breakers re-checked at order time (belt and suspenders)
        if self.check_daily_loss(acct):
            return reject("daily loss limit breached")
        if self.check_drawdown(acct):
            return reject("drawdown kill limit breached")
        checks.append(f"daily_loss={acct.daily_loss_pct:.2f}%<"
                      f"{cfg.max_daily_loss_pct}%; dd={acct.drawdown_pct:.2f}%<"
                      f"{cfg.max_drawdown_pct}%")

        # 3) position count — grid lots share one slot per symbol so a ladder
        #    doesn't instantly exhaust the global cap.
        distinct = {(p.strategy_id, p.symbol) for p in acct.open_positions}
        already_open = (signal.strategy_id, signal.symbol) in distinct
        effective_count = len(distinct)
        if not already_open and effective_count >= cfg.max_open_positions:
            return reject(f"max open positions reached "
                          f"({effective_count}/{cfg.max_open_positions})")
        checks.append(f"positions={effective_count}/{cfg.max_open_positions}")

        # One position per (strategy, symbol) for signal strategies; grid/DCA stack.
        if purpose == OrderPurpose.ENTRY and already_open:
            return reject(f"{signal.strategy_id} already has an open position on "
                          f"{signal.symbol}")

        if acct.equity <= 0:
            return reject("equity is zero — cannot size a position")

        # 4) sizing: % of equity, or the strategy's fixed quote amount (DCA/grid)
        if signal.notional_override is not None:
            notional = float(signal.notional_override)
            checks.append(f"sizing=fixed {notional:.2f}")
        else:
            notional = acct.equity * cfg.position_size_pct / 100.0
            checks.append(f"sizing={cfg.position_size_pct}% of equity "
                          f"{acct.equity:.2f} → {notional:.2f}")
        if size_multiplier != 1.0:
            notional *= size_multiplier
            checks.append(f"adaptive size ×{size_multiplier:g} → {notional:.2f}")

        # 5) exposure caps (existing positions + open buy orders + this order)
        sym_exposure = sum(p.notional for p in acct.positions_for(signal.symbol))
        sym_exposure += acct.open_buy_notional.get(signal.symbol, 0.0)
        max_asset = acct.equity * cfg.max_exposure_per_asset_pct / 100.0
        if sym_exposure + notional > max_asset:
            headroom = max_asset - sym_exposure
            return reject(
                f"per-asset exposure cap: {signal.symbol} at "
                f"{sym_exposure:.2f} + order {notional:.2f} would exceed "
                f"{cfg.max_exposure_per_asset_pct}% of equity "
                f"({max_asset:.2f}); headroom {max(0.0, headroom):.2f}")
        total_exposure = (sum(p.notional for p in acct.open_positions)
                          + sum(acct.open_buy_notional.values()))
        max_total = acct.equity * cfg.max_total_exposure_pct / 100.0
        if total_exposure + notional > max_total:
            return reject(
                f"total exposure cap: deployed {total_exposure:.2f} + order "
                f"{notional:.2f} would exceed {cfg.max_total_exposure_pct}% "
                f"of equity ({max_total:.2f})")
        checks.append(f"exposure sym={sym_exposure:.2f}/{max_asset:.2f} "
                      f"total={total_exposure:.2f}/{max_total:.2f}")

        # 6) exchange filters
        ref_price = limit_price if (order_type == "LIMIT" and limit_price) else price
        qty = rules.quantize_qty(notional / ref_price)
        if qty <= 0 or not rules.meets_min(qty, ref_price):
            return reject(
                f"order of {notional:.2f} {rules.quote_asset} "
                f"(qty {qty}) is below {signal.symbol} exchange minimums "
                f"(minQty {rules.min_qty}, minNotional {rules.min_notional}) — "
                f"increase position size % or account equity")
        checks.append(f"qty={rules.fmt_qty(qty)} notional≈{float(qty) * ref_price:.2f}")

        # 7) protective exits — mandatory unless explicitly exempted (DCA)
        sl_price = tp_price = None
        dca_exempt = (signal.strategy_id == "dca" and cfg.exempt_dca_from_stops
                      and not signal.wants_protection)
        if purpose in (OrderPurpose.GRID_BUY,):
            # Grid lots exit via their paired sell one level up; the range
            # stop (pause/flatten outside range) is the grid's protection.
            checks.append("protection=grid paired sell")
        elif dca_exempt:
            checks.append("protection=exempt (DCA accumulation, per risk config)")
        else:
            sl_price = float(rules.quantize_price(ref_price * (1 - cfg.stop_loss_pct / 100),
                                                  direction="down"))
            tp_price = float(rules.quantize_price(ref_price * (1 + cfg.take_profit_pct / 100),
                                                  direction="up"))
            if not (sl_price < ref_price < tp_price):
                return reject(f"cannot construct valid SL/TP around price {ref_price} "
                              f"(tick size {rules.tick_size})")
            checks.append(f"SL={sl_price} (−{cfg.stop_loss_pct}%) "
                          f"TP={tp_price} (+{cfg.take_profit_pct}%)")

        plan = OrderPlan(
            symbol=signal.symbol, side="BUY", type=order_type, qty=float(qty),
            purpose=purpose, strategy_id=signal.strategy_id, reason=signal.reason,
            price=float(rules.quantize_price(limit_price, direction="down"))
                  if (order_type == "LIMIT" and limit_price) else None,
            sl_price=sl_price, tp_price=tp_price, tags=dict(signal.tags),
        )
        return RiskDecision(True, "approved: " + "; ".join(checks), plan, checks)

    # ── UI: how close is the bot to each limit ──────────────────────────────
    def usage(self, acct: AccountState) -> dict:
        cfg = self.config
        per_asset: dict[str, float] = {}
        for p in acct.open_positions:
            per_asset[p.symbol] = per_asset.get(p.symbol, 0.0) + p.notional
        for sym, n in acct.open_buy_notional.items():
            per_asset[sym] = per_asset.get(sym, 0.0) + n
        equity = acct.equity or 1.0
        distinct = {(p.strategy_id, p.symbol) for p in acct.open_positions}
        total_exposure = sum(per_asset.values())
        return {
            "daily_loss": {"used_pct": round(acct.daily_loss_pct, 3),
                           "limit_pct": cfg.max_daily_loss_pct},
            "drawdown": {"used_pct": round(acct.drawdown_pct, 3),
                         "limit_pct": cfg.max_drawdown_pct,
                         "kill_switch_enabled": cfg.kill_switch_enabled},
            "open_positions": {"used": len(distinct), "limit": cfg.max_open_positions},
            "total_exposure": {"used_pct": round(total_exposure / equity * 100, 2),
                               "limit_pct": cfg.max_total_exposure_pct},
            "per_asset": [
                {"symbol": s, "used_pct": round(n / equity * 100, 2),
                 "limit_pct": cfg.max_exposure_per_asset_pct}
                for s, n in sorted(per_asset.items())],
        }
