"""Trading engine: owns the event loops, wires market data → strategies → risk
gate → order manager, and enforces the global circuit breakers.

State machine (persisted in bot_state so restarts are safe):
  STOPPED → RUNNING ⇄ PAUSED
  RUNNING → DAILY_HALT (auto-clears next UTC day)
  any     → KILLED (drawdown kill switch; only reset_kill() leaves it)
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

from app.config import Settings
from app.core.events import EventBus
from app.core.exchange import BinanceGateway, ExchangeError, new_client_order_id
from app.core.order_manager import OrderManager
from app.core.portfolio import Portfolio
from app.core.types import (AccountState, BotStatus, Candle, EventType, OrderPurpose,
                            PositionView, Signal, SignalAction)
from app.db import repo
from app.db.models import Order
from app.risk import adaptive as adaptive_mod
from app.risk.models import RiskConfig, ScannerConfig
from app.risk.risk_engine import RiskEngine
from app.strategies import scanner as scanner_mod
from app.strategies.base import Strategy
from app.strategies.grid import GridOrderView, GridStrategy
from app.strategies.registry import build as build_strategy

log = logging.getLogger("engine")

EQUITY_SNAPSHOT_SECS = 30
SCHEDULER_TICK_SECS = 5


class CandleStore:
    def __init__(self, maxlen: int = 1000):
        self._data: dict[tuple[str, str], deque[Candle]] = {}
        self.maxlen = maxlen

    def seed(self, symbol: str, tf: str, candles: list[Candle]) -> None:
        self._data[(symbol, tf)] = deque(candles, maxlen=self.maxlen)

    def upsert(self, symbol: str, tf: str, candle: Candle) -> None:
        dq = self._data.setdefault((symbol, tf), deque(maxlen=self.maxlen))
        if dq and dq[-1].open_time == candle.open_time:
            dq[-1] = candle
        else:
            dq.append(candle)

    def has(self, symbol: str, tf: str) -> bool:
        return (symbol, tf) in self._data

    def df(self, symbol: str, tf: str) -> pd.DataFrame:
        dq = self._data.get((symbol, tf), deque())
        closed = [c for c in dq if c.closed]
        return pd.DataFrame(
            {"open_time": [c.open_time for c in closed],
             "open": [c.open for c in closed], "high": [c.high for c in closed],
             "low": [c.low for c in closed], "close": [c.close for c in closed],
             "volume": [c.volume for c in closed]})


class TradingEngine:
    def __init__(self, settings: Settings, bus: EventBus):
        self.settings = settings
        self.bus = bus
        bus.subscribe(self._on_own_event)  # track closed trades for adaptive sizing
        self.portfolio = Portfolio(settings.quote_asset)
        self.gateway: BinanceGateway | None = None
        self.orders: OrderManager | None = None
        self.risk = RiskEngine(RiskConfig())
        self.scanner_cfg = ScannerConfig()
        self.strategies: dict[str, Strategy] = {}
        self.strategy_meta: dict[str, dict] = {}   # id -> {enabled, symbols, use_scanner}
        self.status = BotStatus.STOPPED
        self.status_reason = ""
        self.candles = CandleStore()
        self.scanned: list[dict] = []
        self.invalid_symbols: list[str] = []
        self.evaluations: dict[str, deque] = {}    # strategy id -> recent signals (incl HOLD)
        self._tasks: list[asyncio.Task] = []
        self._market_task: asyncio.Task | None = None
        self._trade_pnls: dict[str, deque] = {}   # strategy id -> recent trade PnLs
        self._held_symbols: dict[str, set[str]] = {}  # strategy id -> open-position symbols
        self._stream_generation = 0
        self._grid_lock = asyncio.Lock()
        self._started_at: datetime | None = None
        self._last_kline_at: datetime | None = None
        self._day_start_equity = 0.0
        self._peak_equity = 0.0
        self._lock = asyncio.Lock()

    # ══ lifecycle ════════════════════════════════════════════════════════════
    async def ensure_gateway(self) -> BinanceGateway:
        if self.gateway is None:
            if not self.settings.has_keys:
                raise RuntimeError(
                    "Binance API keys are not configured — set BINANCE_API_KEY / "
                    "BINANCE_API_SECRET in .env (testnet keys: "
                    "https://testnet.binance.vision)")
            self.gateway = await BinanceGateway.create(self.settings)
            await self.gateway.load_exchange_info()
            self.orders = OrderManager(self.gateway, self.bus, self.settings,
                                       self.portfolio)
        return self.gateway

    async def start(self) -> None:
        async with self._lock:
            state = await repo.get_bot_state()
            if state.status == "KILLED":
                raise RuntimeError("kill switch is engaged — reset it from the Risk "
                                   "page before restarting")
            if self.status in (BotStatus.RUNNING, BotStatus.DAILY_HALT):
                return
            await self.reload_configs()
            await self.ensure_gateway()
            await self._bootstrap()
            await self._set_status(BotStatus.RUNNING, "started by user")
            self._started_at = datetime.now(timezone.utc)
            self._spawn_tasks()
            log.info("engine RUNNING (%s)",
                     "TESTNET" if self.settings.testnet else "LIVE")

    async def _bootstrap(self) -> None:
        gw = self.gateway
        assert gw and self.orders
        self.portfolio.set_balances(await gw.get_balances())
        symbols = self._all_active_symbols()
        self.portfolio.track_symbols(symbols, gw.rules)
        # Prime prices via REST so equity/risk work before WS warms up.
        # Held assets outside the watchlist need a price too, or their value
        # silently drops out of equity and trips the loss limits.
        held = [f"{a}{self.settings.quote_asset}"
                for a, (f, l) in self.portfolio.balances.items()
                if f + l > 0 and a != self.settings.quote_asset]
        for sym in symbols + held + [f"BNB{self.settings.quote_asset}"]:
            if sym in gw.rules and self.portfolio.price_of(sym) is None:
                try:
                    self.portfolio.update_price(sym, await gw.get_price(sym))
                except ExchangeError as e:
                    log.warning("price prime failed %s: %s", sym, e)
        await self.orders.reconcile(sl_tp_pct=(self.risk.config.stop_loss_pct,
                                               self.risk.config.take_profit_pct))
        await self._rollover_day(force_if_unset=True)
        await self._seed_candles()

    def _spawn_tasks(self) -> None:
        """Engine start: spawn everything. The user-data stream and scheduler
        live for the whole session; only the market stream is generation-scoped
        (it restarts whenever the symbol/timeframe set changes — restarting the
        user stream would double-subscribe and flap with -2035)."""
        self._cancel_tasks()
        self._stream_generation += 1
        self._market_task = asyncio.create_task(
            self._market_ws_loop(self._stream_generation), name="market-ws")
        self._tasks = [
            asyncio.create_task(self._user_ws_loop(), name="user-ws"),
            asyncio.create_task(self._scheduler_loop(), name="scheduler"),
        ]

    def _restart_market_stream(self) -> None:
        self._stream_generation += 1
        if self._market_task:
            self._market_task.cancel()
        self._market_task = asyncio.create_task(
            self._market_ws_loop(self._stream_generation), name="market-ws")

    def _cancel_tasks(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._market_task:
            self._market_task.cancel()
        self._tasks = []
        self._market_task = None

    async def pause(self) -> None:
        if self.status == BotStatus.RUNNING:
            await self._set_status(BotStatus.PAUSED, "paused by user — no new "
                                   "entries; exits still managed")

    async def resume(self) -> None:
        if self.status == BotStatus.PAUSED:
            await self._set_status(BotStatus.RUNNING, "resumed by user")

    async def stop(self) -> None:
        """Stop evaluation loops. Exchange-side OCO protection stays live, so
        open positions keep their SL/TP even with the engine offline."""
        async with self._lock:
            self._cancel_tasks()
            if self.status != BotStatus.KILLED:
                await self._set_status(BotStatus.STOPPED,
                                       "stopped by user — open positions remain "
                                       "protected by exchange-side OCO orders")

    async def emergency_stop(self, flatten: bool) -> dict:
        await self.ensure_gateway()
        self._cancel_tasks()
        result = await self.orders.emergency_stop(flatten)
        await self._set_status(BotStatus.STOPPED,
                               f"EMERGENCY STOP (flatten={flatten})")
        return result

    async def reset_kill(self) -> None:
        state = await repo.get_bot_state()
        if state.status != "KILLED" and self.status != BotStatus.KILLED:
            raise RuntimeError("kill switch is not engaged")
        equity = self.portfolio.equity() or state.peak_equity
        # Reset the peak so the same drawdown doesn't instantly re-trip.
        self._peak_equity = equity
        await repo.update_bot_state(peak_equity=equity, killed_at=None)
        await self._set_status(BotStatus.STOPPED, "kill switch manually reset — "
                               "press Start to resume trading")
        await repo.log_risk_event("KILL_RESET", {"new_peak_equity": equity})

    async def shutdown(self) -> None:
        self._cancel_tasks()
        if self.gateway:
            await self.gateway.close()
            self.gateway = None

    async def _set_status(self, status: BotStatus, reason: str) -> None:
        self.status = status
        self.status_reason = reason
        await repo.update_bot_state(status=status.value, status_reason=reason,
                                    **({"killed_at": datetime.now(timezone.utc)}
                                       if status == BotStatus.KILLED else {}))
        self.bus.publish(EventType.STATUS, self.status_payload())
        log.info("status → %s (%s)", status.value, reason)

    async def _refresh_held_symbols(self) -> None:
        """Symbols with open positions stay watched (streams + strategy exits)
        even after the scanner rotates them out of the watchlist."""
        held: dict[str, set[str]] = {}
        for p in await repo.open_positions():
            held.setdefault(p.strategy_id, set()).add(p.symbol)
        self._held_symbols = held

    async def _on_own_event(self, event: dict) -> None:
        if event.get("type") == EventType.POSITION.value:
            await self._refresh_held_symbols()
            return
        if event.get("type") != EventType.TRADE.value:
            return
        d = event.get("data", {})
        sid, pnl = d.get("strategy"), d.get("pnl")
        if sid is None or pnl is None:
            return
        self._trade_pnls.setdefault(sid, deque(maxlen=100)).append(float(pnl))
        state = adaptive_mod.evaluate_adaptive(list(self._trade_pnls[sid]),
                                               self.risk.config)
        if state.paused:  # probation just became (or stays) active — surface it
            note = f"⚠ adaptive probation: {state.reason}"
            if self.strategy_meta.get(sid, {}).get("note") != note:
                await repo.update_strategy_config(sid, note=note)
                self.strategy_meta.setdefault(sid, {})["note"] = note
                await repo.log_risk_event("ADAPTIVE_PAUSE",
                                          {"strategy": sid, **state.to_dict()})
                self.bus.publish(EventType.ALERT, {
                    "kind": "risk", "title": f"Strategy paused: {sid}",
                    "body": state.reason})

    def adaptive_state_for(self, strategy_id: str) -> "adaptive_mod.AdaptiveState":
        return adaptive_mod.evaluate_adaptive(
            list(self._trade_pnls.get(strategy_id, [])), self.risk.config)

    # ══ config / strategy wiring ═════════════════════════════════════════════
    async def reload_configs(self) -> None:
        self.risk = RiskEngine(RiskConfig(**(await repo.get_config("risk") or {})))
        self.scanner_cfg = ScannerConfig(**(await repo.get_config("scanner") or {}))
        self.strategies, self.strategy_meta = {}, {}
        for row in await repo.list_strategy_configs():
            try:
                self.strategies[row.id] = build_strategy(row.id, row.params)
            except (KeyError, ValueError) as e:
                log.error("strategy %s config invalid: %s", row.id, e)
                continue
            self.strategy_meta[row.id] = {"enabled": row.enabled,
                                          "symbols": list(row.symbols or []),
                                          "use_scanner": row.use_scanner,
                                          "note": row.note}
            self.evaluations.setdefault(row.id, deque(maxlen=80))
            if row.id not in self._trade_pnls:  # seed adaptive history from DB
                self._trade_pnls[row.id] = deque(
                    await repo.recent_trade_pnls(row.id), maxlen=100)
        await self._refresh_held_symbols()
        if self.gateway:
            self._validate_symbols()
            self.portfolio.track_symbols(self._all_active_symbols(), self.gateway.rules)

    async def on_configs_changed(self) -> None:
        """Called by the API after any dashboard config save."""
        old_streams = self._needed_streams()
        await self.reload_configs()
        if self.status in (BotStatus.RUNNING, BotStatus.PAUSED, BotStatus.DAILY_HALT):
            await self._seed_candles()
            if self._needed_streams() != old_streams:
                log.info("stream set changed — restarting market data socket")
                self._restart_market_stream()

    def _validate_symbols(self) -> None:
        assert self.gateway
        self.invalid_symbols = []
        for sid, meta in self.strategy_meta.items():
            valid = []
            for sym in meta["symbols"]:
                r = self.gateway.rules.get(sym)
                if r and r.status == "TRADING" and r.quote_asset == self.settings.quote_asset:
                    valid.append(sym)
                else:
                    self.invalid_symbols.append(sym)
            meta["symbols_valid"] = valid
        if self.invalid_symbols:
            log.warning("symbols not tradable here (testnet has a limited set): %s",
                        sorted(set(self.invalid_symbols)))

    def effective_symbols(self, strategy_id: str) -> list[str]:
        meta = self.strategy_meta.get(strategy_id) or {}
        syms = list(meta.get("symbols_valid", meta.get("symbols", [])))
        if meta.get("use_scanner") and self.scanner_cfg.enabled:
            for s in self.scanned:
                if s["symbol"] not in syms:
                    syms.append(s["symbol"])
        syms = syms[:self.scanner_cfg.max_symbols_total]
        for s in self._held_symbols.get(strategy_id, ()):
            if s not in syms:
                syms.append(s)  # held coins stay managed until closed
        return syms

    def _all_active_symbols(self) -> list[str]:
        out: list[str] = []
        for sid, meta in self.strategy_meta.items():
            if meta.get("enabled"):
                for s in self.effective_symbols(sid):
                    if s not in out:
                        out.append(s)
        capped = out[:self.scanner_cfg.max_symbols_total]
        held = {s for ss in self._held_symbols.values() for s in ss}
        for s in held:
            if s in out and s not in capped:
                capped.append(s)
        return capped

    def _needed_streams(self) -> set[tuple[str, str]]:
        """(symbol, timeframe) kline streams: 1m everywhere for price/grid/DCA
        plus each candle strategy's own timeframe."""
        streams: set[tuple[str, str]] = set()
        for sym in self._all_active_symbols():
            streams.add((sym, "1m"))
        for sid, strat in self.strategies.items():
            meta = self.strategy_meta.get(sid, {})
            if meta.get("enabled") and strat.kind == "candle":
                for sym in self.effective_symbols(sid):
                    streams.add((sym, strat.timeframe))
        bnb = f"BNB{self.settings.quote_asset}"
        if self.gateway and bnb in self.gateway.rules:
            streams.add((bnb, "1m"))  # keep BNB fee-asset valuation fresh
        return streams

    async def _seed_candles(self) -> None:
        if not self.gateway:
            return
        need = max((s.required_history() for s in self.strategies.values()),
                   default=100) + 50
        for sym, tf in self._needed_streams():
            if self.candles.has(sym, tf):
                continue
            try:
                raw = await self.gateway.get_klines(sym, tf, limit=min(need, 1000))
                self.candles.seed(sym, tf, [
                    Candle(int(k[0]), float(k[1]), float(k[2]), float(k[3]),
                           float(k[4]), float(k[5]), int(k[6])) for k in raw[:-1]])
            except ExchangeError as e:
                log.warning("candle seed failed %s %s: %s", sym, tf, e)

    # ══ websocket loops (reconnect with backoff) ═════════════════════════════
    async def _market_ws_loop(self, generation: int) -> None:
        assert self.gateway
        backoff = 1.0
        while generation == self._stream_generation:
            streams = [f"{s.lower()}@kline_{tf}" for s, tf in sorted(self._needed_streams())]
            if not streams:
                await asyncio.sleep(5)
                continue
            try:
                bsm = self.gateway.socket_manager()
                async with bsm.multiplex_socket(streams) as sock:
                    log.info("market stream connected (%d streams)", len(streams))
                    backoff = 1.0
                    while generation == self._stream_generation:
                        msg = await asyncio.wait_for(sock.recv(), timeout=60)
                        if msg and msg.get("data", {}).get("e") == "kline":
                            await self._on_kline(msg["data"])
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001 — reconnect on anything
                log.warning("market stream dropped (%s) — reconnecting in %.0fs",
                            e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _user_ws_loop(self) -> None:
        """User-data stream via python-binance's user_socket (the WS-API
        subscription — the classic listen-key endpoint returns 410 Gone on the
        testnet). This loop is spawned once per engine start and never
        restarted on config changes; if Binance still reports a stale
        subscription (-2035, e.g. after a stop→start cycle on the same client),
        we reset the underlying connection and resubscribe cleanly."""
        assert self.gateway
        backoff = 1.0
        while True:
            try:
                bsm = self.gateway.socket_manager()
                async with bsm.user_socket() as sock:
                    log.info("user data stream connected")
                    backoff = 1.0
                    while True:
                        msg = await sock.recv()
                        if not msg:
                            continue
                        if msg.get("e") == "error":
                            raise ConnectionError(msg.get("m", "stream error"))
                        await self._on_user_event(msg)
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001
                txt = str(e)
                if "-2035" in txt or "already active" in txt.lower():
                    log.warning("stale user-stream subscription — resetting "
                                "client connection and resubscribing")
                    with contextlib.suppress(Exception):
                        await self.gateway.client.close_connection()
                    await asyncio.sleep(2)
                    continue
                log.warning("user stream dropped (%s) — reconnecting in %.0fs",
                            e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _on_kline(self, data: dict) -> None:
        k = data["k"]
        sym, tf = k["s"], k["i"]
        candle = Candle(int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]),
                        float(k["c"]), float(k["v"]), int(k["T"]), closed=bool(k["x"]))
        self._last_kline_at = datetime.now(timezone.utc)
        self.candles.upsert(sym, tf, candle)
        self.portfolio.update_price(sym, candle.close)
        if tf == "1m":
            self.bus.publish(EventType.TICK, {"symbol": sym, "price": candle.close})
        if candle.closed:
            self.bus.publish(EventType.CANDLE, {"symbol": sym, "tf": tf,
                                                "t": candle.open_time,
                                                "o": candle.open, "h": candle.high,
                                                "l": candle.low, "c": candle.close,
                                                "v": candle.volume})
            await self._evaluate_candle_strategies(sym, tf)
            if tf == "1m":
                await self._reconcile_grids(sym)

    async def _on_user_event(self, msg: dict) -> None:
        et = msg.get("e")
        if et == "executionReport":
            assert self.orders
            purpose = await self.orders.handle_execution_report(msg)
            if purpose in (OrderPurpose.GRID_BUY.value, OrderPurpose.GRID_SELL.value):
                await self._reconcile_grids(msg.get("s", ""))
        elif et == "outboundAccountPosition":
            for b in msg.get("B", []):
                self.portfolio.update_balance(b["a"], float(b["f"]), float(b["l"]))

    # ══ strategy evaluation (candle close) ═══════════════════════════════════
    async def _position_view(self, strategy_id: str, symbol: str) -> PositionView | None:
        for p in await repo.open_positions():
            if p.strategy_id == strategy_id and p.symbol == symbol:
                mark = self.portfolio.price_of(symbol) or p.avg_entry
                return PositionView(p.id, p.symbol, p.strategy_id, p.qty,
                                    p.avg_entry, mark)
        return None

    async def _account_state(self) -> AccountState:
        views = []
        for p in await repo.open_positions():
            mark = self.portfolio.price_of(p.symbol) or p.avg_entry
            views.append(PositionView(p.id, p.symbol, p.strategy_id, p.qty,
                                      p.avg_entry, mark))
        open_buys: dict[str, float] = {}
        for o in await repo.open_orders_db():
            if o.side == "BUY":
                ref = o.price or self.portfolio.price_of(o.symbol) or 0.0
                open_buys[o.symbol] = open_buys.get(o.symbol, 0.0) + o.qty * ref
        return AccountState(equity=self.portfolio.equity(),
                            day_start_equity=self._day_start_equity,
                            peak_equity=self._peak_equity, status=self.status,
                            open_positions=views, open_buy_notional=open_buys)

    def _record_evaluation(self, signal: Signal) -> None:
        self.evaluations.setdefault(signal.strategy_id, deque(maxlen=80)).append({
            "ts": datetime.now(timezone.utc).isoformat(), "symbol": signal.symbol,
            "action": signal.action.value, "reason": signal.reason})
        self.bus.publish(EventType.SIGNAL, {
            "strategy": signal.strategy_id, "symbol": signal.symbol,
            "action": signal.action.value, "price": signal.price,
            "reason": signal.reason})

    async def _evaluate_candle_strategies(self, symbol: str, tf: str) -> None:
        for sid, strat in self.strategies.items():
            meta = self.strategy_meta.get(sid, {})
            if (strat.kind != "candle" or not meta.get("enabled")
                    or strat.timeframe != tf
                    or symbol not in self.effective_symbols(sid)):
                continue
            df = self.candles.df(symbol, tf)
            pos = await self._position_view(sid, symbol)
            try:
                signal = strat.evaluate(symbol, df, pos)
            except Exception as e:  # noqa: BLE001 — one bad strategy can't stop the loop
                log.exception("strategy %s crashed on %s: %s", sid, symbol, e)
                continue
            self._record_evaluation(signal)
            if signal.action == SignalAction.BUY and pos is None:
                await self._execute_entry(signal, OrderPurpose.ENTRY)
            elif signal.action == SignalAction.SELL and pos is not None:
                assert self.orders
                await repo.log_signal(strategy_id=sid, symbol=symbol, action="SELL",
                                      price=signal.price, reason=signal.reason,
                                      executed=True)
                await self.orders.close_position(pos.id, signal.reason, "signal_exit")

    async def _execute_entry(self, signal: Signal, purpose: OrderPurpose,
                             order_type: str = "MARKET",
                             limit_price: float | None = None) -> bool:
        assert self.gateway and self.orders
        rules = self.gateway.rules.get(signal.symbol)
        price = self.portfolio.price_of(signal.symbol) or signal.price or 0.0
        if rules is None:
            log.warning("no exchange rules for %s — skipping", signal.symbol)
            return False

        # Adaptive layer: probation blocks new signal entries; losing streaks
        # shrink their size. Grid ladders / DCA schedules are exempt by design.
        size_multiplier = 1.0
        if purpose == OrderPurpose.ENTRY:
            adaptive = self.adaptive_state_for(signal.strategy_id)
            if adaptive.paused:
                log.info("adaptive probation blocks %s %s: %s",
                         signal.strategy_id, signal.symbol, adaptive.reason)
                await repo.log_signal(strategy_id=signal.strategy_id,
                                      symbol=signal.symbol,
                                      action=signal.action.value, price=price,
                                      reason=signal.reason, executed=False,
                                      reject_reason=adaptive.reason)
                self.bus.publish(EventType.RISK, {"kind": "ADAPTIVE_PAUSE",
                                                  "strategy": signal.strategy_id,
                                                  "symbol": signal.symbol,
                                                  "reason": adaptive.reason})
                return False
            size_multiplier = adaptive.size_multiplier

        acct = await self._account_state()
        decision = self.risk.evaluate_entry(signal, price, acct, rules,
                                            purpose=purpose, order_type=order_type,
                                            limit_price=limit_price,
                                            size_multiplier=size_multiplier)
        await repo.log_signal(strategy_id=signal.strategy_id, symbol=signal.symbol,
                              action=signal.action.value, price=price,
                              reason=signal.reason, executed=decision.approved,
                              reject_reason="" if decision.approved else decision.reason)
        if not decision.approved:
            log.info("risk REJECTED %s %s: %s", signal.strategy_id, signal.symbol,
                     decision.reason)
            await repo.log_risk_event("REJECT", {
                "strategy": signal.strategy_id, "symbol": signal.symbol,
                "signal_reason": signal.reason, "reject_reason": decision.reason})
            self.bus.publish(EventType.RISK, {"kind": "REJECT",
                                              "symbol": signal.symbol,
                                              "strategy": signal.strategy_id,
                                              "reason": decision.reason})
            return False
        log.info("risk APPROVED %s %s: %s", signal.strategy_id, signal.symbol,
                 decision.reason)
        pos = await self.orders.place_entry(
            decision.plan, trailing_enabled=self.risk.config.trailing_stop_enabled)
        return pos is not None or order_type == "LIMIT"

    # ══ grid ═════════════════════════════════════════════════════════════════
    async def _grid_state(self, symbol: str) -> dict:
        return await repo.get_config(f"grid:{symbol}")

    async def _reconcile_grids(self, symbol: str) -> None:
        sid = "grid"
        strat = self.strategies.get(sid)
        meta = self.strategy_meta.get(sid, {})
        if (not isinstance(strat, GridStrategy) or not meta.get("enabled")
                or symbol not in self.effective_symbols(sid)
                or self.status != BotStatus.RUNNING):
            return
        price = self.portfolio.price_of(symbol)
        if not price:
            return
        async with self._grid_lock:
            state = await self._grid_state(symbol)
            if state.get("paused"):
                return
            levels = state.get("levels")
            if not levels:
                levels = strat.levels(price)
                await repo.set_config(f"grid:{symbol}", {"levels": levels,
                                                         "paused": False})
                log.info("grid %s activated: %d levels %.6g → %.6g", symbol,
                         len(levels), levels[0], levels[-1])

            if strat.params["stop_outside_range"] and not strat.in_range(price, levels):
                await self._pause_grid(symbol, price, levels, strat)
                return

            open_grid, inventory = [], []
            for o in await repo.open_orders_db():
                if (o.symbol == symbol and o.grid_level is not None and o.purpose in
                        (OrderPurpose.GRID_BUY.value, OrderPurpose.GRID_SELL.value)):
                    open_grid.append(GridOrderView(o.side, o.grid_level,
                                                   o.client_order_id))
            for p in await repo.open_positions():
                if p.strategy_id == sid and p.symbol == symbol:
                    inventory.append(SimpleNamespace(id=p.id, qty=p.qty,
                                                     grid_level=p.grid_level))
            # Cancel buy orders stranded above the current price.
            for o in open_grid:
                if o.side == "BUY" and o.level < len(levels) and levels[o.level] > price:
                    row = await repo.get_order_by_client_id(o.client_order_id)
                    if row:
                        try:
                            await self.gateway.cancel_order(symbol,
                                                            client_order_id=o.client_order_id)
                            await repo.update_order(row.id, status="CANCELED")
                        except ExchangeError as e:
                            log.warning("grid cancel failed %s: %s",
                                        o.client_order_id, e)
            open_grid = [o for o in open_grid
                         if not (o.side == "BUY" and o.level < len(levels)
                                 and levels[o.level] > price)]

            for plan in strat.desired_orders(price, levels, open_grid, inventory):
                if plan.side == "BUY":
                    sig = Signal(SignalAction.BUY, symbol, sid,
                                 f"grid buy at level {plan.level} ({plan.price:.6g})",
                                 price=price, notional_override=plan.quote_amount,
                                 tags={"grid_level": plan.level})
                    await self._execute_entry(sig, OrderPurpose.GRID_BUY,
                                              order_type="LIMIT",
                                              limit_price=plan.price)
                else:
                    lot = next((l for l in inventory
                                if l.grid_level is not None
                                and l.grid_level + 1 == plan.level), None)
                    if lot:
                        await self._place_grid_sell(symbol, lot, plan.level,
                                                    plan.price)

    async def _place_grid_sell(self, symbol: str, lot, level: int,
                               price: float) -> None:
        assert self.gateway
        rules = self.gateway.rules[symbol]
        qty = rules.quantize_qty(lot.qty)
        px = rules.quantize_price(price, direction="up")
        if qty <= 0 or not rules.meets_min(qty, float(px)):
            log.warning("grid sell for lot %s below minimums — held", lot.id)
            return
        cid = new_client_order_id("gs")
        await repo.save_order(Order(client_order_id=cid, symbol=symbol, side="SELL",
                                    type="LIMIT", purpose=OrderPurpose.GRID_SELL.value,
                                    strategy_id="grid", position_id=lot.id,
                                    price=float(px), qty=float(qty),
                                    reason=f"grid sell level {level}",
                                    grid_level=level))
        try:
            resp = await self.gateway.limit_order(symbol, "SELL", qty, px, cid)
            row = await repo.get_order_by_client_id(cid)
            if row:
                await repo.update_order(row.id, status=resp.get("status", "NEW"),
                                        exchange_order_id=str(resp.get("orderId", "")))
        except ExchangeError as e:
            log.error("grid sell failed %s lvl %s: %s", symbol, level, e)
            row = await repo.get_order_by_client_id(cid)
            if row:
                await repo.update_order(row.id, status="REJECTED")

    async def _pause_grid(self, symbol: str, price: float, levels: list[float],
                          strat: GridStrategy) -> None:
        state = await self._grid_state(symbol)
        state["paused"] = True
        await repo.set_config(f"grid:{symbol}", state)
        n = 0
        for o in await repo.open_orders_db():
            if o.symbol == symbol and o.grid_level is not None:
                try:
                    await self.gateway.cancel_order(symbol,
                                                    client_order_id=o.client_order_id)
                    await repo.update_order(o.id, status="CANCELED")
                    n += 1
                except ExchangeError:
                    pass
        flattened = 0
        if strat.params["flatten_on_stop"]:
            for p in await repo.open_positions():
                if p.strategy_id == "grid" and p.symbol == symbol:
                    await self.orders.close_position(p.id, "grid range exit — flatten",
                                                     "grid_stop")
                    flattened += 1
        note = (f"grid paused on {symbol}: price {price:.6g} left range "
                f"[{levels[0]:.6g}, {levels[-1]:.6g}]. Re-enable the strategy to "
                f"rebuild the ladder.")
        await repo.update_strategy_config("grid", note=note)
        self.strategy_meta.setdefault("grid", {})["note"] = note
        await repo.log_risk_event("GRID_PAUSE", {"symbol": symbol, "price": price,
                                                 "canceled": n,
                                                 "flattened": flattened})
        self.bus.publish(EventType.ALERT, {"kind": "risk",
                                           "title": f"Grid paused: {symbol}",
                                           "body": note})

    async def clear_grid_state(self) -> None:
        """Called when the grid strategy config changes: rebuild ladders fresh."""
        for row in await repo.list_strategy_configs():
            if row.id == "grid":
                for sym in row.symbols or []:
                    await repo.set_config(f"grid:{sym}", {})
        await repo.update_strategy_config("grid", note="")

    # ══ DCA ══════════════════════════════════════════════════════════════════
    async def _check_dca(self) -> None:
        sid = "dca"
        strat = self.strategies.get(sid)
        meta = self.strategy_meta.get(sid, {})
        if (strat is None or strat.kind != "schedule" or not meta.get("enabled")
                or self.status != BotStatus.RUNNING):
            return
        state = await repo.get_config("dca_state")
        now = datetime.now(timezone.utc)
        changed = False
        for symbol in self.effective_symbols(sid):
            last_iso = state.get(symbol)
            last = datetime.fromisoformat(last_iso) if last_iso else None
            if not strat.is_due(last, now):
                continue
            change_pct = None
            try:
                t = await self.gateway.get_ticker_24h(symbol)
                change_pct = float(t.get("priceChangePercent", 0.0))
                # Prime the price cache so a symbol whose kline stream hasn't
                # delivered yet doesn't get its DCA buy rejected for no price.
                last = float(t.get("lastPrice", 0.0) or 0.0)
                if last > 0:
                    self.portfolio.update_price(symbol, last)
            except ExchangeError as e:
                log.warning("DCA ticker fetch failed %s: %s", symbol, e)
            signal = strat.build_signal(symbol, change_pct)
            self._record_evaluation(signal)
            await self._execute_entry(signal, OrderPurpose.DCA_BUY)
            state[symbol] = now.isoformat()  # schedule consumed even if rejected
            changed = True
        if changed:
            await repo.set_config("dca_state", state)

    # ══ scheduler: equity, breakers, scanner, DCA, trailing ══════════════════
    async def _scheduler_loop(self) -> None:
        last_snapshot = 0.0
        last_scan = 0.0
        loop = asyncio.get_running_loop()
        while True:
            try:
                await asyncio.sleep(SCHEDULER_TICK_SECS)
                now = loop.time()
                await self._rollover_day()
                if now - last_snapshot >= EQUITY_SNAPSHOT_SECS:
                    last_snapshot = now
                    await self._equity_tick()
                if (self.scanner_cfg.enabled
                        and now - last_scan >= self.scanner_cfg.refresh_minutes * 60):
                    last_scan = now
                    await self._refresh_scanner()
                await self._check_dca()
                await self._manage_positions()
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001 — scheduler must survive
                log.exception("scheduler tick failed: %s", e)

    async def _manage_positions(self) -> None:
        assert self.orders
        cfg = self.risk.config
        for pos in await repo.open_positions():
            price = self.portfolio.price_of(pos.symbol)
            if price:
                await self.orders.manage_position(pos, price, cfg.trailing_stop_pct,
                                                  cfg.trailing_activation_pct)

    async def _equity_tick(self) -> None:
        equity = self.portfolio.equity()
        if equity <= 0:
            return
        if equity > self._peak_equity:
            self._peak_equity = equity
            await repo.update_bot_state(peak_equity=equity)
        acct = await self._account_state()
        upnl = sum(p.unrealized_pnl for p in acct.open_positions)
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                       microsecond=0)
        realized_today = await repo.realized_pnl_since(day_start)
        await repo.add_equity_snapshot(equity, upnl, realized_today)
        self.bus.publish(EventType.EQUITY, {"equity": round(equity, 4),
                                            "unrealized": round(upnl, 4),
                                            "realized_today": round(realized_today, 4)})
        self.bus.publish(EventType.RISK, {"kind": "USAGE",
                                          "usage": self.risk.usage(acct)})

        if self.status in (BotStatus.RUNNING, BotStatus.DAILY_HALT):
            breach = self.risk.check_drawdown(acct)
            if breach:
                await self._trip_kill(breach)
                return
        if self.status == BotStatus.RUNNING:
            breach = self.risk.check_daily_loss(acct)
            if breach:
                await repo.log_risk_event("DAILY_HALT", dataclasses.asdict(breach))
                await self._set_status(BotStatus.DAILY_HALT, breach.message)
                self.bus.publish(EventType.ALERT, {"kind": "risk",
                                                   "title": "Daily loss limit hit",
                                                   "body": breach.message})

    async def _trip_kill(self, breach) -> None:
        await repo.log_risk_event("KILL", dataclasses.asdict(breach))
        await self._set_status(BotStatus.KILLED, breach.message)
        self.bus.publish(EventType.ALERT, {"kind": "kill",
                                           "title": "KILL SWITCH TRIPPED",
                                           "body": breach.message})
        assert self.orders
        # Stop all entry orders; optionally flatten. Protective OCOs stay unless
        # flattening (close cancels them per position).
        for row in await repo.open_orders_db():
            if row.side == "BUY":
                try:
                    await self.gateway.cancel_order(row.symbol,
                                                    client_order_id=row.client_order_id)
                    await repo.update_order(row.id, status="CANCELED")
                except ExchangeError:
                    pass
        if self.risk.config.flatten_on_kill:
            for pos in await repo.open_positions():
                await self.orders.close_position(pos.id, "kill switch — flatten",
                                                 "kill_switch")

    async def _rollover_day(self, force_if_unset: bool = False) -> None:
        state = await repo.get_bot_state()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        equity = self.portfolio.equity()
        self._peak_equity = max(state.peak_equity or 0.0, equity)
        if state.day_start_date != today or (force_if_unset and not state.day_start_equity):
            if state.day_start_date != today and equity > 0:
                await repo.update_bot_state(day_start_date=today,
                                            day_start_equity=equity,
                                            peak_equity=self._peak_equity)
                self._day_start_equity = equity
                if self.status == BotStatus.DAILY_HALT:
                    await self._set_status(BotStatus.RUNNING,
                                           "new UTC day — daily halt cleared")
            elif equity > 0:
                await repo.update_bot_state(day_start_equity=equity,
                                            day_start_date=today)
                self._day_start_equity = equity
        else:
            self._day_start_equity = state.day_start_equity or equity

    async def _refresh_scanner(self) -> None:
        assert self.gateway
        try:
            tickers = await self.gateway.get_ticker_24h_all()
        except ExchangeError as e:
            log.warning("scanner refresh failed: %s", e)
            return
        tradable = {s: r.base_asset for s, r in self.gateway.rules.items()
                    if r.status == "TRADING"
                    and r.quote_asset == self.settings.quote_asset}
        min_vol = 0.0 if self.settings.testnet else self.scanner_cfg.min_quote_volume_24h
        picks = scanner_mod.select_symbols(
            tickers, tradable, quote_asset=self.settings.quote_asset,
            top_n=self.scanner_cfg.top_n, min_quote_volume=min_vol,
            rank_by=self.scanner_cfg.rank_by)
        old = [s["symbol"] for s in self.scanned]
        self.scanned = [{"symbol": p.symbol, "change_pct": p.price_change_pct,
                         "quote_volume": p.quote_volume, "price": p.last_price}
                        for p in picks]
        self.bus.publish(EventType.SCANNER, {"symbols": self.scanned})
        if [s["symbol"] for s in self.scanned] != old:
            log.info("scanner update: %s", [s["symbol"] for s in self.scanned])
            await self._seed_candles()
            self._restart_market_stream()

    # ══ status for API/UI ════════════════════════════════════════════════════
    def status_payload(self) -> dict:
        last_kline_age = ((datetime.now(timezone.utc) - self._last_kline_at)
                          .total_seconds() if self._last_kline_at else None)
        return {
            "status": self.status.value,
            "status_reason": self.status_reason,
            "testnet": self.settings.testnet,
            "has_keys": self.settings.has_keys,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "equity": round(self.portfolio.equity(), 4),
            "day_start_equity": round(self._day_start_equity, 4),
            "peak_equity": round(self._peak_equity, 4),
            "active_symbols": self._all_active_symbols(),
            "invalid_symbols": sorted(set(self.invalid_symbols)),
            "scanner": self.scanned,
            "market_stream_age_secs": last_kline_age,
        }
