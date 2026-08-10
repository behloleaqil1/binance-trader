"""Order lifecycle: placement, protective OCO exits, fills, trailing stops,
position close-out, startup reconciliation, and the emergency stop.

Invariants:
  • Orders are persisted BEFORE they are sent, so a crash between "sent" and
    "recorded" is detected by reconciliation, never silently lost.
  • Every non-exempt position gets an exchange-side OCO (TP + SL) immediately
    after entry — protection survives a dead bot process. If OCO placement
    fails, the position is flagged unprotected and the engine monitors it
    (and keeps retrying the OCO).
  • Only the risk engine's approved OrderPlans reach place_entry().
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from app.config import Settings
from app.core.events import EventBus
from app.core.exchange import (BinanceGateway, ExchangeError, InsufficientBalance,
                               is_bot_order_id, new_client_order_id)
from app.core.types import EventType, OrderPlan, OrderPurpose
from app.db import repo
from app.db.models import Order, Position, Trade

log = logging.getLogger("orders")

_PREFIX = {OrderPurpose.ENTRY: "en", OrderPurpose.GRID_BUY: "gb",
           OrderPurpose.GRID_SELL: "gs", OrderPurpose.DCA_BUY: "dc",
           OrderPurpose.EXIT: "ex", OrderPurpose.TAKE_PROFIT: "tp",
           OrderPurpose.STOP_LOSS: "sl"}

# Stop-limit price sits slightly below the trigger so the limit leg fills
# through minor gaps instead of resting unfilled in a fast market.
_STOP_LIMIT_GAP = 0.0015


class OrderManager:
    def __init__(self, gateway: BinanceGateway, bus: EventBus, settings: Settings,
                 portfolio):
        self.gw = gateway
        self.bus = bus
        self.settings = settings
        self.portfolio = portfolio
        self._last_trail_update: dict[int, float] = {}   # position id -> monotonic ts
        self._last_protect_retry: dict[int, float] = {}

    # ── fees ────────────────────────────────────────────────────────────────
    def _fee_to_quote(self, fee_qty: float, fee_asset: str, symbol: str,
                      exec_price: float) -> float:
        if fee_qty == 0:
            return 0.0
        rules = self.gw.rules.get(symbol)
        if rules and fee_asset == rules.quote_asset:
            return fee_qty
        if rules and fee_asset == rules.base_asset:
            return fee_qty * exec_price
        converted = self.portfolio.asset_value_quote(fee_asset, fee_qty)
        if converted == 0.0:
            log.warning("cannot value fee %s %s in quote — recorded as 0",
                        fee_qty, fee_asset)
        return converted

    def _fills_summary(self, resp: dict, symbol: str) -> tuple[float, float, float]:
        """(avg_price, filled_qty, fee_quote) from a FULL order response."""
        fills = resp.get("fills") or []
        if not fills:
            qty = float(resp.get("executedQty", 0) or 0)
            quote = float(resp.get("cummulativeQuoteQty", 0) or 0)
            avg = quote / qty if qty else 0.0
            return avg, qty, 0.0
        qty = sum(float(f["qty"]) for f in fills)
        quote = sum(float(f["qty"]) * float(f["price"]) for f in fills)
        avg = quote / qty if qty else 0.0
        fee = sum(self._fee_to_quote(float(f.get("commission", 0)),
                                     f.get("commissionAsset", ""), symbol, avg)
                  for f in fills)
        # Buy fees charged in the base asset reduce what we actually hold.
        rules = self.gw.rules.get(symbol)
        base = rules.base_asset if rules else ""
        base_fee = sum(float(f.get("commission", 0)) for f in fills
                       if f.get("commissionAsset") == base)
        return avg, qty - base_fee, fee

    # ── entries ─────────────────────────────────────────────────────────────
    async def place_entry(self, plan: OrderPlan, trailing_enabled: bool) -> Position | None:
        """Execute an approved entry plan. Returns the Position for market
        entries; limit entries (grid) return None until their fill event."""
        cid = new_client_order_id(_PREFIX[plan.purpose])
        order_row = await repo.save_order(Order(
            client_order_id=cid, symbol=plan.symbol, side=plan.side,
            type=plan.type, purpose=plan.purpose.value, strategy_id=plan.strategy_id,
            price=plan.price, qty=plan.qty, reason=plan.reason,
            grid_level=plan.tags.get("grid_level")))
        try:
            if plan.type == "MARKET":
                resp = await self.gw.market_order(plan.symbol, plan.side,
                                                  Decimal(str(plan.qty)), cid)
            else:
                resp = await self.gw.limit_order(plan.symbol, plan.side,
                                                 Decimal(str(plan.qty)),
                                                 Decimal(str(plan.price)), cid)
        except (ExchangeError, InsufficientBalance) as e:
            await repo.update_order(order_row.id, status="REJECTED",
                                    reason=f"{plan.reason} | REJECTED: {e}")
            self.bus.publish(EventType.ERROR, {"where": "place_entry",
                                               "symbol": plan.symbol, "error": str(e)})
            log.error("entry rejected %s %s: %s", plan.symbol, plan.purpose.value, e)
            return None

        status = resp.get("status", "NEW")
        await repo.update_order(order_row.id, exchange_order_id=str(resp.get("orderId", "")),
                                status=status)
        self.bus.publish(EventType.ORDER, {
            "symbol": plan.symbol, "side": plan.side, "type": plan.type,
            "status": status, "qty": plan.qty, "purpose": plan.purpose.value,
            "strategy": plan.strategy_id, "reason": plan.reason})

        if plan.type != "MARKET" or status != "FILLED":
            return None  # limit order will complete via user-stream fill

        avg, qty, fee = self._fills_summary(resp, plan.symbol)
        pos = await repo.save_position(Position(
            symbol=plan.symbol, strategy_id=plan.strategy_id, qty=qty,
            avg_entry=avg, entry_fee_quote=fee, sl_price=plan.sl_price,
            tp_price=plan.tp_price, trailing_enabled=trailing_enabled,
            high_watermark=avg, entry_reason=plan.reason,
            grid_level=plan.tags.get("grid_level")))
        if not await repo.link_order_position(order_row.id, pos.id):
            # The user-stream fill handler won the race and linked its own
            # position first — drop ours and attach SL/TP to the winner's.
            await repo.delete_position(pos.id)
            row = await repo.get_order_by_client_id(cid)
            pos = await repo.get_position(row.position_id) if row and row.position_id else None
            if pos is None:
                log.error("lost position-link race on %s but no position "
                          "found — manual check needed", cid)
                return None
            await repo.update_position(pos.id, sl_price=plan.sl_price,
                                       tp_price=plan.tp_price,
                                       trailing_enabled=trailing_enabled)
            pos.sl_price, pos.tp_price = plan.sl_price, plan.tp_price
            pos.trailing_enabled = trailing_enabled
            if plan.sl_price and plan.tp_price:
                await self.place_protection(pos)
            return pos
        await repo.update_order(order_row.id, filled_qty=qty,
                                avg_fill_price=avg, fee_quote=fee)
        log.info("ENTRY FILLED %s %s qty=%s @ %s (%s)", plan.symbol,
                 plan.strategy_id, qty, avg, plan.reason[:120])
        self.bus.publish(EventType.POSITION, {"action": "opened", "id": pos.id,
                                              "symbol": pos.symbol, "qty": qty,
                                              "entry": avg,
                                              "strategy": plan.strategy_id})
        self.bus.publish(EventType.ALERT, {
            "kind": "fill", "title": f"Entry filled: {plan.symbol}",
            "body": f"{plan.strategy_id} bought {qty:g} @ {avg:g} — {plan.reason[:200]}"})

        if plan.sl_price and plan.tp_price:
            await self.place_protection(pos)
        return pos

    # ── protective OCO ──────────────────────────────────────────────────────
    async def place_protection(self, pos: Position) -> bool:
        """Attach the exchange-side TP/SL OCO for a position. Falls back to
        engine-side monitoring (protected=False) on failure."""
        # Idempotent: if live protection legs already exist for this position,
        # don't place a duplicate OCO (it fails on locked balance and its
        # failure path used to clobber protected=True back to False).
        if await self._protection_leg_ids(pos.id):
            if not pos.protected:
                await repo.update_position(pos.id, protected=True)
                pos.protected = True
            return True
        rules = self.gw.rules[pos.symbol]
        price = self.portfolio.price_of(pos.symbol) or pos.avg_entry
        sl_trigger = rules.quantize_price(pos.sl_price, direction="down")
        sl_limit = rules.quantize_price(pos.sl_price * (1 - _STOP_LIMIT_GAP),
                                        direction="down")
        tp = rules.quantize_price(pos.tp_price, direction="up")

        # OCO needs TP > market > stop; if price already ran through either
        # side, exit immediately at market instead of placing an invalid OCO.
        if price >= float(tp):
            await self.close_position(pos.id, "price at/above TP before protection "
                                      "could be placed — taking profit", "take_profit")
            return True
        if price <= float(sl_trigger):
            await self.close_position(pos.id, "price at/below SL before protection "
                                      "could be placed — stopping out", "stop_loss")
            return True

        try:  # cache may lag the fill — cap at the exchange's real balance
            bal = (await self.gw.get_balances()).get(rules.base_asset, (0.0, 0.0))
            self.portfolio.update_balance(rules.base_asset, *bal)
            held = bal[0] + bal[1]
        except ExchangeError:
            held = self.portfolio.free(rules.base_asset) or pos.qty
        qty = rules.quantize_qty(min(pos.qty, held) if held > 0 else 0.0)
        if qty <= 0 or not rules.meets_min(qty, price):
            log.warning("position %s too small to protect with OCO (qty=%s)", pos.id, qty)
            await repo.update_position(pos.id, protected=False)
            return False

        list_cid = new_client_order_id("oc")
        try:
            resp = await self.gw.oco_sell(pos.symbol, qty, tp, sl_trigger, sl_limit,
                                          list_cid)
        except (ExchangeError, InsufficientBalance) as e:
            log.error("OCO placement failed for position %s: %s — engine-side "
                      "monitoring active", pos.id, e)
            await repo.update_position(pos.id, protected=False, oco_list_id="")
            self.bus.publish(EventType.ALERT, {
                "kind": "risk", "title": f"OCO failed on {pos.symbol}",
                "body": f"Position {pos.id} is protected by engine monitoring only: {e}"})
            return False

        reports = resp.get("orderReports") or resp.get("orders") or []
        for r in reports:
            purpose = (OrderPurpose.STOP_LOSS if "STOP" in r.get("type", "")
                       else OrderPurpose.TAKE_PROFIT)
            await repo.save_order(Order(
                client_order_id=r.get("clientOrderId", new_client_order_id("xx")),
                exchange_order_id=str(r.get("orderId", "")),
                oco_list_id=str(resp.get("orderListId", "")),
                symbol=pos.symbol, side="SELL", type=r.get("type", "OCO"),
                status=r.get("status", "NEW"), purpose=purpose.value,
                strategy_id=pos.strategy_id, position_id=pos.id,
                price=float(r["price"]) if r.get("price") not in (None, "0", 0) else None,
                stop_price=float(r["stopPrice"]) if r.get("stopPrice") else None,
                qty=float(qty), reason=f"protection for position {pos.id}"))
        await repo.update_position(pos.id, protected=True,
                                   oco_list_id=str(resp.get("orderListId", "")),
                                   sl_price=float(sl_trigger), tp_price=float(tp))
        log.info("protection placed for position %s: SL %s / TP %s", pos.id,
                 sl_trigger, tp)
        return True

    async def _protection_leg_ids(self, position_id: int) -> list[str]:
        rows = await repo.open_orders_db()
        return [o.client_order_id for o in rows
                if o.position_id == position_id
                and o.purpose in (OrderPurpose.STOP_LOSS.value,
                                  OrderPurpose.TAKE_PROFIT.value)]

    async def cancel_protection(self, pos: Position) -> None:
        legs = await self._protection_leg_ids(pos.id)
        if legs:
            try:
                await self.gw.cancel_oco_by_leg(pos.symbol, legs)
            except ExchangeError as e:
                log.warning("cancel protection for %s failed: %s", pos.id, e)
            for cid in legs:
                row = await repo.get_order_by_client_id(cid)
                if row and row.status in ("NEW", "PARTIALLY_FILLED"):
                    await repo.update_order(row.id, status="CANCELED")
        await repo.update_position(pos.id, protected=False, oco_list_id="")

    # ── exits ───────────────────────────────────────────────────────────────
    async def close_position(self, position_id: int, reason: str,
                             exit_kind: str) -> Trade | None:
        pos = await repo.get_position(position_id)
        if not pos or pos.status != "OPEN":
            return None
        await self.cancel_protection(pos)

        rules = self.gw.rules[pos.symbol]
        # The cached balance is stale right after canceling protection (the
        # release arrives via the user stream) — ask the exchange directly.
        try:
            bal = (await self.gw.get_balances()).get(rules.base_asset, (0.0, 0.0))
            self.portfolio.update_balance(rules.base_asset, *bal)
            held = bal[0] + bal[1]
        except ExchangeError:
            held = self.portfolio.free(rules.base_asset) or pos.qty
        sellable = min(pos.qty, held) if held > 0 else 0.0
        qty = rules.quantize_qty(sellable)
        price = self.portfolio.price_of(pos.symbol) or pos.avg_entry
        if qty <= 0 or not rules.meets_min(qty, price):
            # Dust: can't sell on-exchange; close the book entry at mark.
            log.warning("position %s qty %s is dust — closing book entry at mark",
                        pos.id, pos.qty)
            return await self._finalize_close(pos, price, 0.0, reason + " (dust)",
                                              exit_kind)
        cid = new_client_order_id("ex")
        await repo.save_order(Order(client_order_id=cid, symbol=pos.symbol,
                                    side="SELL", type="MARKET",
                                    purpose=OrderPurpose.EXIT.value,
                                    strategy_id=pos.strategy_id, position_id=pos.id,
                                    qty=float(qty), reason=reason))
        try:
            resp = await self.gw.market_order(pos.symbol, "SELL", qty, cid)
        except (ExchangeError, InsufficientBalance) as e:
            log.error("exit order failed for position %s: %s", pos.id, e)
            self.bus.publish(EventType.ERROR, {"where": "close_position",
                                               "position": pos.id, "error": str(e)})
            row = await repo.get_order_by_client_id(cid)
            if row:
                await repo.update_order(row.id, status="REJECTED")
            return None
        avg, filled, fee = self._fills_summary(resp, pos.symbol)
        row = await repo.get_order_by_client_id(cid)
        if row:
            await repo.update_order(row.id, status="FILLED",
                                    exchange_order_id=str(resp.get("orderId", "")),
                                    filled_qty=filled, avg_fill_price=avg,
                                    fee_quote=fee)
        return await self._finalize_close(pos, avg or price, fee, reason, exit_kind)

    async def _finalize_close(self, pos: Position, exit_price: float, exit_fee: float,
                              reason: str, exit_kind: str) -> Trade:
        entry_value = pos.avg_entry * pos.qty
        exit_value = exit_price * pos.qty
        fees = pos.entry_fee_quote + exit_fee
        pnl = exit_value - entry_value - fees
        pnl_pct = pnl / entry_value * 100 if entry_value else 0.0
        trade = await repo.save_trade(Trade(
            position_id=pos.id, symbol=pos.symbol, strategy_id=pos.strategy_id,
            qty=pos.qty, entry_price=pos.avg_entry, exit_price=exit_price,
            pnl_quote=pnl, pnl_pct=pnl_pct, fees_quote=fees,
            entry_reason=pos.entry_reason, exit_reason=f"{exit_kind}: {reason}",
            opened_at=pos.opened_at))
        await repo.update_position(pos.id, status="CLOSED",
                                   closed_at=datetime.now(timezone.utc))
        log.info("POSITION CLOSED %s #%s pnl=%.4f (%s)", pos.symbol, pos.id, pnl,
                 exit_kind)
        self.bus.publish(EventType.TRADE, {
            "id": trade.id, "symbol": pos.symbol, "strategy": pos.strategy_id,
            "qty": pos.qty, "entry": pos.avg_entry, "exit": exit_price,
            "pnl": round(pnl, 6), "pnl_pct": round(pnl_pct, 4),
            "exit_kind": exit_kind})
        self.bus.publish(EventType.POSITION, {"action": "closed", "id": pos.id,
                                              "symbol": pos.symbol})
        alert_kind = "stop_loss" if exit_kind == "stop_loss" else "fill"
        self.bus.publish(EventType.ALERT, {
            "kind": alert_kind,
            "title": f"{pos.symbol} closed ({exit_kind}): {pnl:+.2f} USDT",
            "body": f"{pos.strategy_id}: entry {pos.avg_entry:g} → exit "
                    f"{exit_price:g}, {pnl_pct:+.2f}% net of fees. {reason[:180]}"})
        return trade

    # ── user-stream fills ───────────────────────────────────────────────────
    async def handle_execution_report(self, msg: dict) -> str | None:
        """Process an executionReport. Returns the purpose of a FILLED order
        (so the engine can trigger grid reconciliation), else None."""
        cid = msg.get("c") or ""
        orig = msg.get("C") or ""
        row = (await repo.get_order_by_client_id(cid)
               or (await repo.get_order_by_client_id(orig) if orig else None))
        if row is None:
            return None  # not ours (manual order etc.)

        status = msg.get("X", row.status)
        fields: dict = {"status": status,
                        "exchange_order_id": str(msg.get("i", row.exchange_order_id))}
        last_qty = float(msg.get("l", 0) or 0)
        exec_price = float(msg.get("L", 0) or 0)
        if last_qty and exec_price:
            fee = self._fee_to_quote(float(msg.get("n", 0) or 0), msg.get("N") or "",
                                     row.symbol, exec_price)
            cum = float(msg.get("z", 0) or 0)
            cum_quote = float(msg.get("Z", 0) or 0)
            fields.update(filled_qty=cum,
                          avg_fill_price=(cum_quote / cum) if cum else exec_price,
                          fee_quote=row.fee_quote + fee)
        await repo.update_order(row.id, **fields)
        if status != "FILLED":
            return None

        purpose = row.purpose
        updated = await repo.get_order_by_client_id(row.client_order_id)
        avg = updated.avg_fill_price or exec_price
        fee_total = updated.fee_quote

        if purpose in (OrderPurpose.GRID_BUY.value, OrderPurpose.ENTRY.value,
                       OrderPurpose.DCA_BUY.value) and row.side == "BUY":
            if row.position_id is None:  # limit entry completed → open position now
                pos = await repo.save_position(Position(
                    symbol=row.symbol, strategy_id=row.strategy_id,
                    qty=updated.filled_qty, avg_entry=avg, entry_fee_quote=fee_total,
                    entry_reason=row.reason, grid_level=row.grid_level,
                    high_watermark=avg))
                if not await repo.link_order_position(row.id, pos.id):
                    await repo.delete_position(pos.id)  # place_entry won the race
                    return purpose
                log.info("grid/limit BUY filled %s lvl=%s qty=%s @ %s", row.symbol,
                         row.grid_level, updated.filled_qty, avg)
                self.bus.publish(EventType.POSITION, {
                    "action": "opened", "id": pos.id, "symbol": pos.symbol,
                    "qty": updated.filled_qty, "entry": avg,
                    "strategy": row.strategy_id, "grid_level": row.grid_level})
        elif purpose in (OrderPurpose.TAKE_PROFIT.value, OrderPurpose.STOP_LOSS.value):
            if row.position_id:
                pos = await repo.get_position(row.position_id)
                if pos and pos.status == "OPEN":
                    kind = ("take_profit" if purpose == OrderPurpose.TAKE_PROFIT.value
                            else "stop_loss")
                    await self._finalize_close(pos, avg, fee_total,
                                               f"exchange OCO {kind} leg filled @ {avg:g}",
                                               kind)
        elif purpose == OrderPurpose.GRID_SELL.value and row.position_id:
            pos = await repo.get_position(row.position_id)
            if pos and pos.status == "OPEN":
                await self._finalize_close(pos, avg, fee_total,
                                           f"grid sell filled at level "
                                           f"{row.grid_level} @ {avg:g}", "grid_tp")
        return purpose

    # ── trailing stop + engine-side fallback protection ─────────────────────
    async def manage_position(self, pos: Position, price: float,
                              trailing_pct: float, activation_pct: float) -> None:
        if pos.status != "OPEN" or price <= 0:
            return
        # Engine-side SL/TP when the exchange OCO could not be placed.
        if not pos.protected and pos.sl_price and pos.tp_price:
            if price <= pos.sl_price:
                await self.close_position(pos.id, f"engine-side stop @ {price:g} "
                                          f"(OCO was unavailable)", "stop_loss")
                return
            if price >= pos.tp_price:
                await self.close_position(pos.id, f"engine-side take-profit @ "
                                          f"{price:g} (OCO was unavailable)",
                                          "take_profit")
                return
            now = time.monotonic()
            if now - self._last_protect_retry.get(pos.id, 0) > 60:
                self._last_protect_retry[pos.id] = now
                await self.place_protection(pos)
            return

        if not pos.trailing_enabled or not pos.sl_price:
            return
        hwm = max(pos.high_watermark or pos.avg_entry, price)
        if hwm != pos.high_watermark:
            await repo.update_position(pos.id, high_watermark=hwm)
        armed = hwm >= pos.avg_entry * (1 + activation_pct / 100)
        if not armed:
            return
        new_sl = hwm * (1 - trailing_pct / 100)
        now = time.monotonic()
        if (new_sl > pos.sl_price * 1.001
                and now - self._last_trail_update.get(pos.id, 0) > 15):
            self._last_trail_update[pos.id] = now
            log.info("trailing stop %s #%s: %.6g → %.6g (hwm %.6g)", pos.symbol,
                     pos.id, pos.sl_price, new_sl, hwm)
            await self.cancel_protection(pos)
            await repo.update_position(pos.id, sl_price=new_sl)
            fresh = await repo.get_position(pos.id)
            if fresh and fresh.status == "OPEN":
                await self.place_protection(fresh)

    # ── startup reconciliation ──────────────────────────────────────────────
    async def reconcile(self, sl_tp_pct: tuple[float, float] | None = None) -> dict:
        """Bring DB state and exchange state back in sync after a restart."""
        summary = {"orders_updated": 0, "orphans_canceled": 0,
                   "positions_reprotected": 0, "positions_closed": 0,
                   "positions_adopted": 0}

        # Filled buys that never got a position row (crash between fill and
        # persist) — adopt them so the holding is tracked and protected again.
        for row in await repo.orphan_filled_entries():
            avg = row.avg_fill_price or row.price or 0.0
            qty = row.filled_qty or row.qty
            if not avg or not qty:
                continue
            sl = tp = None
            if sl_tp_pct and row.purpose == OrderPurpose.ENTRY.value:
                sl = avg * (1 - sl_tp_pct[0] / 100.0)
                tp = avg * (1 + sl_tp_pct[1] / 100.0)
            pos = await repo.save_position(Position(
                symbol=row.symbol, strategy_id=row.strategy_id, qty=qty,
                avg_entry=avg, entry_fee_quote=row.fee_quote, sl_price=sl,
                tp_price=tp, high_watermark=avg, grid_level=row.grid_level,
                entry_reason=f"{row.reason} [adopted by reconcile — position "
                             f"row was lost after the fill]"))
            if not await repo.link_order_position(row.id, pos.id):
                await repo.delete_position(pos.id)
                continue
            summary["positions_adopted"] += 1
            log.warning("reconcile: adopted orphan filled %s %s qty=%s @ %s "
                        "(position %s, SL=%s TP=%s)", row.purpose, row.symbol,
                        qty, avg, pos.id, sl, tp)

        for row in await repo.open_orders_db():
            try:
                data = await self.gw.get_order(row.symbol, row.client_order_id)
            except ExchangeError as e:
                if e.code == -2013:  # order does not exist on this account/env
                    await repo.update_order(row.id, status="CANCELED")
                    summary["orders_updated"] += 1
                    log.warning("reconcile: order %s not on exchange — marked "
                                "CANCELED", row.client_order_id)
                else:
                    log.warning("reconcile: order %s lookup failed: %s",
                                row.client_order_id, e)
                continue
            status = data.get("status", row.status)
            if status == row.status:
                continue
            summary["orders_updated"] += 1
            executed = float(data.get("executedQty", 0) or 0)
            cq = float(data.get("cummulativeQuoteQty", 0) or 0)
            avg = cq / executed if executed else None
            await repo.update_order(row.id, status=status, filled_qty=executed,
                                    avg_fill_price=avg)
            if status == "FILLED":  # fill happened while we were down
                fake_report = {"c": row.client_order_id, "X": "FILLED",
                               "i": data.get("orderId"), "l": 0, "L": 0,
                               "z": executed, "Z": cq}
                await self.handle_execution_report(fake_report)

        # Orphans: bot-prefixed open orders on the exchange with no DB row.
        known = {o.client_order_id for o in await repo.open_orders_db()}
        try:
            exchange_open = await self.gw.get_open_orders()
        except ExchangeError as e:
            log.warning("reconcile: open-orders fetch failed: %s", e)
            exchange_open = []
        for o in exchange_open:
            cid = o.get("clientOrderId", "")
            if is_bot_order_id(cid) and cid not in known:
                if self.settings.cancel_orphan_orders:
                    try:
                        await self.gw.cancel_order(o["symbol"], order_id=o["orderId"])
                        summary["orphans_canceled"] += 1
                        log.warning("canceled orphan bot order %s on %s", cid,
                                    o["symbol"])
                    except ExchangeError as e:
                        log.warning("orphan cancel failed %s: %s", cid, e)
                else:
                    log.warning("orphan bot order left in place (config): %s", cid)

        # Positions with no backing base-asset balance no longer exist on this
        # account (e.g. the testnet→live switch) — close them in the DB.
        remaining = {a: f + l for a, (f, l) in self.portfolio.balances.items()}
        # Positions carrying exit prices claim balance first, so if duplicate
        # rows contest the same holding, the protected/monitorable one survives.
        candidates = sorted(await repo.open_positions(),
                            key=lambda p: (p.sl_price is None, p.id))
        for pos in candidates:
            rules = self.gw.rules.get(pos.symbol)
            if not rules:
                continue
            have = remaining.get(rules.base_asset, 0.0)
            if have < pos.qty * 0.9:
                await repo.update_position(pos.id, status="CLOSED",
                                           closed_at=datetime.now(timezone.utc))
                summary["positions_closed"] += 1
                log.warning("reconcile: position %s %s has no backing %s balance "
                            "(%.8f < %.8f) — closed in DB", pos.id, pos.symbol,
                            rules.base_asset, have, pos.qty)
            else:
                remaining[rules.base_asset] = have - pos.qty

        # Positions must end up protected or engine-monitored.
        for pos in await repo.open_positions():
            legs = await self._protection_leg_ids(pos.id)
            if not legs and pos.sl_price and pos.tp_price:
                ok = await self.place_protection(pos)
                summary["positions_reprotected"] += 1 if ok else 0
        log.info("reconciliation: %s", summary)
        return summary

    # ── emergency stop ──────────────────────────────────────────────────────
    async def emergency_stop(self, flatten: bool) -> dict:
        """Cancel every open order immediately; optionally market-close all
        positions. Callable regardless of engine state."""
        canceled = 0
        symbols = {o.symbol for o in await repo.open_orders_db()}
        try:
            symbols |= {o["symbol"] for o in await self.gw.get_open_orders()
                        if is_bot_order_id(o.get("clientOrderId", ""))}
        except ExchangeError as e:
            log.error("emergency: open-orders fetch failed: %s", e)
        for sym in symbols:
            try:
                canceled += await self.gw.cancel_all_orders(sym)
            except ExchangeError as e:
                log.error("emergency: cancel_all(%s) failed: %s", sym, e)
        for row in await repo.open_orders_db():
            await repo.update_order(row.id, status="CANCELED")

        closed = 0
        if flatten:
            for pos in await repo.open_positions():
                t = await self.close_position(pos.id, "emergency stop — flatten all",
                                              "emergency")
                closed += 1 if t else 0
        else:
            for pos in await repo.open_positions():
                await repo.update_position(pos.id, protected=False, oco_list_id="")

        result = {"orders_canceled": canceled, "positions_closed": closed,
                  "flatten": flatten}
        await repo.log_risk_event("EMERGENCY", result)
        self.bus.publish(EventType.RISK, {"kind": "EMERGENCY", **result})
        self.bus.publish(EventType.ALERT, {
            "kind": "kill", "title": "EMERGENCY STOP executed",
            "body": f"Canceled {canceled} orders; "
                    f"{'closed ' + str(closed) + ' positions' if flatten else 'positions kept (unprotected — restart to re-protect)'}"})
        return result
