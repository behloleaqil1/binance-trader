"""Async Binance Spot gateway.

Wraps python-binance with the operational hardening the raw client leaves to
you: bounded retries with exponential backoff + jitter, rate-limit budgeting,
server-clock resync on timestamp errors, and typed errors. WebSocket
reconnection lives in the engine's socket loops (they recreate sockets from
this gateway on failure).

Testnet vs live is decided once, from Settings — there is deliberately no
runtime switch.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from decimal import Decimal

from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException, BinanceRequestException

from app.config import Settings
from app.core.symbol_rules import SymbolRules

log = logging.getLogger("exchange")


class ExchangeError(Exception):
    """Terminal exchange failure (after retries)."""
    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        self.code = code


class InsufficientBalance(ExchangeError):
    pass


# Binance error codes that are safe to retry.
_RETRYABLE = {-1003, -1006, -1007, -1016, -1021}
_MAX_ATTEMPTS = 5


class RateBudget:
    """Approximate client-side request-weight budget (default spot: 6000/min;
    we stay far below it and rely on backoff for anything we miss)."""

    def __init__(self, per_minute: int = 3000):
        self.per_minute = per_minute
        self._window_start = time.monotonic()
        self._used = 0
        self._lock = asyncio.Lock()

    async def acquire(self, weight: int) -> None:
        async with self._lock:
            now = time.monotonic()
            if now - self._window_start >= 60:
                self._window_start, self._used = now, 0
            if self._used + weight > self.per_minute:
                wait = 60 - (now - self._window_start) + 0.05
                log.warning("rate budget exhausted, sleeping %.1fs", wait)
                await asyncio.sleep(max(0.0, wait))
                self._window_start, self._used = time.monotonic(), 0
            self._used += weight


def new_client_order_id(prefix: str) -> str:
    """Bot orders are identifiable by prefix (used for startup reconciliation).
    Binance allows ≤36 chars."""
    return f"bt-{prefix}-{uuid.uuid4().hex[:16]}"[:36]


def is_bot_order_id(client_order_id: str) -> bool:
    return client_order_id.startswith("bt-")


class BinanceGateway:
    def __init__(self, client: AsyncClient, testnet: bool):
        self.client = client
        self.testnet = testnet
        self.budget = RateBudget()
        self.rules: dict[str, SymbolRules] = {}

    @classmethod
    async def create(cls, settings: Settings) -> "BinanceGateway":
        client = await AsyncClient.create(
            api_key=settings.binance_api_key or None,
            api_secret=settings.binance_api_secret or None,
            testnet=settings.testnet,
        )
        gw = cls(client, settings.testnet)
        await gw.sync_clock()
        log.info("Binance gateway ready (%s, key %s)",
                 "TESTNET" if settings.testnet else "LIVE", settings.masked_key())
        return gw

    async def close(self) -> None:
        try:
            await self.client.close_connection()
        except Exception:  # noqa: BLE001 — best-effort shutdown
            pass

    # ── request wrapper: retries, backoff, clock resync ─────────────────────
    async def _call(self, fn, *args, weight: int = 1, **kwargs):
        await self.budget.acquire(weight)
        delay = 0.5
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await fn(*args, **kwargs)
            except BinanceAPIException as e:
                if e.code == -2010:
                    raise InsufficientBalance(e.message, e.code) from e
                retryable = e.code in _RETRYABLE or e.status_code in (418, 429, 500, 502, 503)
                if not retryable or attempt == _MAX_ATTEMPTS:
                    raise ExchangeError(f"{e.code}: {e.message}", e.code) from e
                if e.code == -1021:  # clock drift — resync then retry immediately
                    log.warning("timestamp rejected (clock drift) — resyncing")
                    await self.sync_clock()
                else:
                    retry_after = 0.0
                    try:
                        retry_after = float(e.response.headers.get("Retry-After", 0))
                    except Exception:  # noqa: BLE001
                        pass
                    sleep_for = max(delay, retry_after) + random.uniform(0, 0.3)
                    log.warning("retryable Binance error %s (attempt %d/%d), "
                                "sleeping %.1fs: %s", e.code, attempt, _MAX_ATTEMPTS,
                                sleep_for, e.message)
                    await asyncio.sleep(sleep_for)
                    delay *= 2
            except (BinanceRequestException, asyncio.TimeoutError, OSError) as e:
                if attempt == _MAX_ATTEMPTS:
                    raise ExchangeError(f"network error: {e}") from e
                sleep_for = delay + random.uniform(0, 0.3)
                log.warning("network error (attempt %d/%d), sleeping %.1fs: %s",
                            attempt, _MAX_ATTEMPTS, sleep_for, e)
                await asyncio.sleep(sleep_for)
                delay *= 2

    async def sync_clock(self) -> None:
        """Align the client's timestamp offset with the exchange server clock."""
        try:
            res = await self.client.get_server_time()
            self.client.timestamp_offset = res["serverTime"] - int(time.time() * 1000)
            log.info("clock synced, offset %dms", self.client.timestamp_offset)
        except Exception as e:  # noqa: BLE001
            log.warning("clock sync failed: %s", e)

    # ── market data ─────────────────────────────────────────────────────────
    async def load_exchange_info(self) -> dict[str, SymbolRules]:
        info = await self._call(self.client.get_exchange_info, weight=20)
        self.rules = {s["symbol"]: SymbolRules.from_exchange_info(s)
                      for s in info["symbols"]}
        return self.rules

    async def get_klines(self, symbol: str, interval: str, limit: int = 500,
                         start_ms: int | None = None, end_ms: int | None = None) -> list:
        kwargs: dict = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms:
            kwargs["startTime"] = start_ms
        if end_ms:
            kwargs["endTime"] = end_ms
        return await self._call(self.client.get_klines, weight=2, **kwargs)

    async def get_price(self, symbol: str) -> float:
        t = await self._call(self.client.get_symbol_ticker, symbol=symbol, weight=2)
        return float(t["price"])

    async def get_ticker_24h_all(self) -> list[dict]:
        return await self._call(self.client.get_ticker, weight=80)

    async def get_ticker_24h(self, symbol: str) -> dict:
        return await self._call(self.client.get_ticker, symbol=symbol, weight=2)

    # ── account ─────────────────────────────────────────────────────────────
    async def get_balances(self) -> dict[str, tuple[float, float]]:
        acct = await self._call(self.client.get_account, weight=20)
        out = {}
        for b in acct["balances"]:
            free, locked = float(b["free"]), float(b["locked"])
            if free or locked:
                out[b["asset"]] = (free, locked)
        return out

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        if symbol:
            return await self._call(self.client.get_open_orders, symbol=symbol, weight=6)
        return await self._call(self.client.get_open_orders, weight=80)

    async def get_order(self, symbol: str, client_order_id: str) -> dict:
        return await self._call(self.client.get_order, symbol=symbol,
                                origClientOrderId=client_order_id, weight=4)

    # ── trading ─────────────────────────────────────────────────────────────
    async def market_order(self, symbol: str, side: str, qty: Decimal,
                           client_order_id: str) -> dict:
        rules = self.rules[symbol]
        return await self._call(
            self.client.create_order, weight=1,
            symbol=symbol, side=side, type="MARKET",
            quantity=rules.fmt_qty(qty), newClientOrderId=client_order_id,
            newOrderRespType="FULL",  # include fills for immediate PnL/fee data
        )

    async def limit_order(self, symbol: str, side: str, qty: Decimal, price: Decimal,
                          client_order_id: str) -> dict:
        rules = self.rules[symbol]
        return await self._call(
            self.client.create_order, weight=1,
            symbol=symbol, side=side, type="LIMIT", timeInForce="GTC",
            quantity=rules.fmt_qty(qty), price=rules.fmt_price(price),
            newClientOrderId=client_order_id)

    async def oco_sell(self, symbol: str, qty: Decimal, tp_price: Decimal,
                       sl_trigger: Decimal, sl_limit: Decimal,
                       list_client_order_id: str) -> dict:
        """Protective exit: take-profit limit above, stop-loss(-limit) below.

        Uses the orderList/oco parameter style (aboveType/belowType) — the
        legacy price/stopPrice form is rejected with -1102 on live."""
        rules = self.rules[symbol]
        return await self._call(
            self.client.create_oco_order, weight=2,
            symbol=symbol, side="SELL",
            quantity=rules.fmt_qty(qty),
            aboveType="LIMIT_MAKER",
            abovePrice=rules.fmt_price(tp_price),
            belowType="STOP_LOSS_LIMIT",
            belowStopPrice=rules.fmt_price(sl_trigger),
            belowPrice=rules.fmt_price(sl_limit),
            belowTimeInForce="GTC",
            listClientOrderId=list_client_order_id)

    async def cancel_order(self, symbol: str, order_id: int | None = None,
                           client_order_id: str | None = None) -> dict:
        kwargs: dict = {"symbol": symbol}
        if order_id:
            kwargs["orderId"] = order_id
        else:
            kwargs["origClientOrderId"] = client_order_id
        return await self._call(self.client.cancel_order, weight=1, **kwargs)

    async def cancel_oco_by_leg(self, symbol: str, leg_client_order_ids: list[str]) -> bool:
        """Cancel an OCO list. Binance cancels the whole list when any leg is
        canceled, so this avoids depending on OCO-specific endpoints: try each
        known leg until one cancel succeeds. Returns False if none were open
        (already filled/canceled)."""
        for cid in leg_client_order_ids:
            try:
                await self.cancel_order(symbol, client_order_id=cid)
                return True
            except ExchangeError as e:
                if e.code == -2011:  # unknown/closed order — try the other leg
                    continue
                raise
        return False

    async def cancel_all_orders(self, symbol: str) -> int:
        """Cancel every open order on a symbol, one by one (portable across
        python-binance versions). Returns the number canceled."""
        n = 0
        for o in await self.get_open_orders(symbol):
            try:
                await self.cancel_order(symbol, order_id=o["orderId"])
                n += 1
            except ExchangeError as e:
                if e.code != -2011:  # already gone is fine
                    raise
        return n

    # ── sockets (consumed by the engine's reconnect loops) ──────────────────
    def socket_manager(self) -> BinanceSocketManager:
        return BinanceSocketManager(self.client)
