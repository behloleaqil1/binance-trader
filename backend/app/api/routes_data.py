"""Read endpoints: positions, trades, orders, signals, equity, chart klines."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_engine
from app.backtest import data as public_data
from app.core.engine import TradingEngine
from app.db import repo

router = APIRouter(tags=["data"])


@router.get("/positions")
async def positions(engine: TradingEngine = Depends(get_engine)):
    out = []
    for p in await repo.open_positions():
        mark = engine.portfolio.price_of(p.symbol) or p.avg_entry
        upnl = (mark - p.avg_entry) * p.qty
        entry_value = p.avg_entry * p.qty
        out.append({
            "id": p.id, "symbol": p.symbol, "strategy": p.strategy_id,
            "qty": p.qty, "avg_entry": p.avg_entry, "mark": mark,
            "value": round(mark * p.qty, 4),
            "unrealized_pnl": round(upnl, 4),
            "unrealized_pnl_pct": round(upnl / entry_value * 100, 3) if entry_value else 0,
            "sl": p.sl_price, "tp": p.tp_price, "protected": p.protected,
            "trailing": p.trailing_enabled, "grid_level": p.grid_level,
            "opened_at": p.opened_at.isoformat(), "entry_reason": p.entry_reason})
    return out


@router.get("/trades")
async def trades(limit: int = 50, offset: int = 0, symbol: str | None = None,
                 strategy: str | None = None):
    rows, total = await repo.list_trades(min(limit, 200), offset, symbol, strategy)
    return {"total": total, "items": [{
        "id": t.id, "symbol": t.symbol, "strategy": t.strategy_id, "qty": t.qty,
        "entry_price": t.entry_price, "exit_price": t.exit_price,
        "pnl": round(t.pnl_quote, 6), "pnl_pct": round(t.pnl_pct, 4),
        "fees": round(t.fees_quote, 6),
        "entry_reason": t.entry_reason, "exit_reason": t.exit_reason,
        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    } for t in rows]}


@router.get("/orders")
async def orders(limit: int = 100, symbol: str | None = None):
    rows = await repo.list_orders(min(limit, 500), symbol)
    return [{
        "id": o.id, "client_order_id": o.client_order_id, "symbol": o.symbol,
        "side": o.side, "type": o.type, "status": o.status, "purpose": o.purpose,
        "strategy": o.strategy_id, "price": o.price, "stop_price": o.stop_price,
        "qty": o.qty, "filled_qty": o.filled_qty, "avg_fill_price": o.avg_fill_price,
        "fee_quote": o.fee_quote, "reason": o.reason, "grid_level": o.grid_level,
        "created_at": o.created_at.isoformat(),
    } for o in rows]


@router.get("/signals")
async def signals(limit: int = 100):
    rows = await repo.list_signals(min(limit, 300))
    return [{
        "ts": s.ts.isoformat(), "strategy": s.strategy_id, "symbol": s.symbol,
        "action": s.action, "price": s.price, "reason": s.reason,
        "executed": s.executed, "reject_reason": s.reject_reason,
    } for s in rows]


@router.get("/equity-history")
async def equity_history(hours: int = 168):
    rows = await repo.equity_history(min(hours, 24 * 90))
    return [{"ts": r.ts.isoformat(), "equity": r.equity,
             "unrealized": r.unrealized_pnl,
             "realized_today": r.realized_pnl_today} for r in rows]


@router.get("/klines")
async def klines(symbol: str, tf: str = "1h", limit: int = 300,
                 engine: TradingEngine = Depends(get_engine)):
    """Chart data. Prefers the engine's live store (same feed the strategies
    see), then the gateway, then the public data host (works with no keys)."""
    symbol, limit = symbol.upper(), min(limit, 1000)
    if tf not in ("1m", "5m", "15m", "1h", "4h", "1d"):
        raise HTTPException(422, "unsupported timeframe")
    if engine.candles.has(symbol, tf):
        df = engine.candles.df(symbol, tf).tail(limit)
        return df.to_dict(orient="records")
    if engine.gateway:
        try:
            raw = await engine.gateway.get_klines(symbol, tf, limit=limit)
            return [{"open_time": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                     "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                    for k in raw]
        except Exception:  # noqa: BLE001 — fall through to public data
            pass
    try:
        return await public_data.fetch_recent_public(symbol, tf, limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"kline fetch failed: {e}") from e


@router.get("/events/recent")
async def recent_events(engine: TradingEngine = Depends(get_engine)):
    return list(engine.bus.recent)
