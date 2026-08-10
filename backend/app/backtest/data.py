"""Historical kline download with a SQLite cache.

Uses Binance's public market-data host (data-api.binance.vision) — no API key,
and always *production* market history: backtests should model the real
market even when the bot itself runs against the testnet.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.database import session
from app.db.models import KlineCache

log = logging.getLogger("backtest.data")

PUBLIC_BASE = "https://data-api.binance.vision"

_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000,
                "4h": 14_400_000, "1d": 86_400_000}


def interval_ms(tf: str) -> int:
    return _INTERVAL_MS[tf]


def _to_ms(d: str | datetime) -> int:
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


async def _fetch_remote(symbol: str, tf: str, start_ms: int, end_ms: int) -> list[dict]:
    rows: list[dict] = []
    step = interval_ms(tf)
    cursor = start_ms
    async with httpx.AsyncClient(base_url=PUBLIC_BASE, timeout=30) as client:
        while cursor < end_ms:
            for attempt in range(4):
                try:
                    r = await client.get("/api/v3/klines", params={
                        "symbol": symbol, "interval": tf, "startTime": cursor,
                        "endTime": end_ms, "limit": 1000})
                    r.raise_for_status()
                    batch = r.json()
                    break
                except (httpx.HTTPError, ValueError) as e:
                    if attempt == 3:
                        raise RuntimeError(f"kline download failed for {symbol}: {e}") from e
                    await asyncio.sleep(1.5 * 2 ** attempt)
            if not batch:
                break
            for k in batch:
                rows.append({"symbol": symbol, "timeframe": tf, "open_time": int(k[0]),
                             "open": float(k[1]), "high": float(k[2]),
                             "low": float(k[3]), "close": float(k[4]),
                             "volume": float(k[5]), "close_time": int(k[6])})
            cursor = batch[-1][0] + step
            if len(batch) < 1000:
                break
    return rows


async def fetch_recent_public(symbol: str, tf: str, limit: int = 300) -> list[dict]:
    """Latest `limit` candles from the public data host (no key, single request)."""
    async with httpx.AsyncClient(base_url=PUBLIC_BASE, timeout=30) as client:
        r = await client.get("/api/v3/klines", params={
            "symbol": symbol, "interval": tf, "limit": min(limit, 1000)})
        r.raise_for_status()
        return [{"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                 "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                for k in r.json()]


async def fetch_klines(symbol: str, tf: str, start: str | datetime,
                       end: str | datetime) -> pd.DataFrame:
    """Return a candle DataFrame for [start, end); cache-first, fill from remote."""
    start_ms, end_ms = _to_ms(start), _to_ms(end)
    if end_ms <= start_ms:
        raise ValueError("end must be after start")
    step = interval_ms(tf)
    expected = (end_ms - start_ms) // step

    async with session() as s:
        cached = list((await s.execute(
            select(KlineCache).where(
                KlineCache.symbol == symbol, KlineCache.timeframe == tf,
                KlineCache.open_time >= start_ms, KlineCache.open_time < end_ms)
            .order_by(KlineCache.open_time))).scalars())

    # Tolerate a small shortfall (exchange downtime candles); refetch otherwise.
    if expected == 0 or len(cached) < expected * 0.995:
        log.info("downloading %s %s klines (%d cached / ~%d expected)",
                 symbol, tf, len(cached), expected)
        rows = await _fetch_remote(symbol, tf, start_ms, end_ms)
        if not rows:
            raise RuntimeError(f"no kline data returned for {symbol} {tf} — "
                               f"check the symbol and date range")
        async with session() as s:
            for i in range(0, len(rows), 500):
                await s.execute(sqlite_insert(KlineCache)
                                .values(rows[i:i + 500])
                                .on_conflict_do_nothing())
            await s.commit()
        data = rows
    else:
        data = [{"open_time": c.open_time, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume} for c in cached]

    df = pd.DataFrame(data)[["open_time", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    return df
