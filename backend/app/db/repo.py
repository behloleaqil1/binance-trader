"""Thin async repository helpers. Each function opens its own short session,
which keeps call sites simple and avoids long-lived transactions on SQLite."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, func, select, update

from app.db.database import session
from app.db.models import (BacktestRun, BotState, EquitySnapshot, KVConfig, Order,
                           Position, RiskEvent, SignalLog, StrategyConfig, Trade)


# ── bot state ────────────────────────────────────────────────────────────────
async def get_bot_state() -> BotState:
    async with session() as s:
        return (await s.execute(select(BotState).where(BotState.id == 1))).scalar_one()


async def update_bot_state(**fields) -> None:
    async with session() as s:
        await s.execute(update(BotState).where(BotState.id == 1).values(**fields))
        await s.commit()


# ── kv configs ───────────────────────────────────────────────────────────────
async def get_config(key: str) -> dict:
    async with session() as s:
        row = await s.get(KVConfig, key)
        return dict(row.value) if row else {}


async def set_config(key: str, value: dict) -> None:
    async with session() as s:
        row = await s.get(KVConfig, key)
        if row:
            row.value = value
        else:
            s.add(KVConfig(key=key, value=value))
        await s.commit()


# ── strategy configs ─────────────────────────────────────────────────────────
async def list_strategy_configs() -> list[StrategyConfig]:
    async with session() as s:
        return list((await s.execute(select(StrategyConfig))).scalars())


async def get_strategy_config(strategy_id: str) -> StrategyConfig | None:
    async with session() as s:
        return await s.get(StrategyConfig, strategy_id)


async def update_strategy_config(strategy_id: str, **fields) -> None:
    async with session() as s:
        await s.execute(update(StrategyConfig)
                        .where(StrategyConfig.id == strategy_id).values(**fields))
        await s.commit()


# ── orders / positions / trades ──────────────────────────────────────────────
async def add(obj) -> None:
    async with session() as s:
        s.add(obj)
        await s.commit()


async def save_order(order: Order) -> Order:
    async with session() as s:
        s.add(order)
        await s.commit()
        await s.refresh(order)
        return order


async def get_order_by_client_id(client_order_id: str) -> Order | None:
    async with session() as s:
        return (await s.execute(select(Order)
                .where(Order.client_order_id == client_order_id))).scalar_one_or_none()


async def update_order(order_id: int, **fields) -> None:
    async with session() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(**fields))
        await s.commit()


async def link_order_position(order_id: int, position_id: int) -> bool:
    """Atomically link a filled order to a position — succeeds for exactly one
    caller. Both place_entry and the user-stream fill handler can observe the
    same fill: each creates a Position row and tries to link it; the loser
    deletes its row and attaches to the winner's. Prevents duplicates without
    violating the FK (a real position id is linked, never a sentinel)."""
    async with session() as s:
        res = await s.execute(update(Order)
                              .where(Order.id == order_id,
                                     Order.position_id.is_(None))
                              .values(position_id=position_id))
        await s.commit()
        return res.rowcount == 1


async def delete_position(position_id: int) -> None:
    """Hard-delete a just-created position row that lost the link race."""
    async with session() as s:
        await s.execute(delete(Position).where(Position.id == position_id))
        await s.commit()


async def orphan_filled_entries() -> list[Order]:
    """FILLED buy orders never linked to a position (e.g. a crash between
    fill and persist) — reconcile adopts these as positions."""
    async with session() as s:
        return list((await s.execute(select(Order).where(
            Order.status == "FILLED", Order.side == "BUY",
            Order.position_id.is_(None),
            Order.purpose.in_(("ENTRY", "DCA_BUY", "GRID_BUY"))))).scalars())


async def open_orders_db() -> list[Order]:
    async with session() as s:
        return list((await s.execute(select(Order).where(
            Order.status.in_(("NEW", "PARTIALLY_FILLED"))))).scalars())


async def list_orders(limit: int = 200, symbol: str | None = None) -> list[Order]:
    async with session() as s:
        q = select(Order).order_by(desc(Order.created_at)).limit(limit)
        if symbol:
            q = q.where(Order.symbol == symbol)
        return list((await s.execute(q)).scalars())


async def save_position(pos: Position) -> Position:
    async with session() as s:
        s.add(pos)
        await s.commit()
        await s.refresh(pos)
        return pos


async def get_position(position_id: int) -> Position | None:
    async with session() as s:
        return await s.get(Position, position_id)


async def update_position(position_id: int, **fields) -> None:
    async with session() as s:
        await s.execute(update(Position).where(Position.id == position_id).values(**fields))
        await s.commit()


async def open_positions() -> list[Position]:
    async with session() as s:
        return list((await s.execute(select(Position)
                    .where(Position.status == "OPEN"))).scalars())


async def save_trade(trade: Trade) -> Trade:
    async with session() as s:
        s.add(trade)
        await s.commit()
        await s.refresh(trade)
        return trade


async def list_trades(limit: int = 100, offset: int = 0, symbol: str | None = None,
                      strategy_id: str | None = None) -> tuple[list[Trade], int]:
    async with session() as s:
        q = select(Trade)
        if symbol:
            q = q.where(Trade.symbol == symbol)
        if strategy_id:
            q = q.where(Trade.strategy_id == strategy_id)
        total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        rows = list((await s.execute(
            q.order_by(desc(Trade.closed_at)).limit(limit).offset(offset))).scalars())
        return rows, total


async def recent_trade_pnls(strategy_id: str, limit: int = 100) -> list[float]:
    """Closed-trade PnLs for one strategy, oldest → newest (adaptive input)."""
    async with session() as s:
        rows = (await s.execute(select(Trade.pnl_quote)
                                .where(Trade.strategy_id == strategy_id)
                                .order_by(desc(Trade.closed_at))
                                .limit(limit))).scalars()
        return list(rows)[::-1]


async def realized_pnl_since(since: datetime) -> float:
    async with session() as s:
        val = (await s.execute(select(func.coalesce(func.sum(Trade.pnl_quote), 0.0))
                               .where(Trade.closed_at >= since))).scalar_one()
        return float(val)


# ── signals / equity / risk events ───────────────────────────────────────────
async def log_signal(**kw) -> None:
    async with session() as s:
        s.add(SignalLog(**kw))
        await s.commit()


async def list_signals(limit: int = 100) -> list[SignalLog]:
    async with session() as s:
        return list((await s.execute(select(SignalLog)
                    .order_by(desc(SignalLog.ts)).limit(limit))).scalars())


async def add_equity_snapshot(equity: float, upnl: float, realized_today: float) -> None:
    async with session() as s:
        s.add(EquitySnapshot(equity=equity, unrealized_pnl=upnl,
                             realized_pnl_today=realized_today))
        await s.commit()


async def equity_history(hours: int = 168, max_points: int = 1500) -> list[EquitySnapshot]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with session() as s:
        rows = list((await s.execute(select(EquitySnapshot)
                    .where(EquitySnapshot.ts >= since)
                    .order_by(EquitySnapshot.ts))).scalars())
    if len(rows) > max_points:  # downsample for the chart payload
        step = len(rows) / max_points
        rows = [rows[int(i * step)] for i in range(max_points)]
    return rows


async def log_risk_event(kind: str, detail: dict) -> None:
    async with session() as s:
        s.add(RiskEvent(kind=kind, detail=detail))
        await s.commit()


async def list_risk_events(limit: int = 50) -> list[RiskEvent]:
    async with session() as s:
        return list((await s.execute(select(RiskEvent)
                    .order_by(desc(RiskEvent.ts)).limit(limit))).scalars())


# ── backtests ────────────────────────────────────────────────────────────────
async def save_backtest(run: BacktestRun) -> BacktestRun:
    async with session() as s:
        s.add(run)
        await s.commit()
        await s.refresh(run)
        return run


async def update_backtest(run_id: int, **fields) -> None:
    async with session() as s:
        await s.execute(update(BacktestRun).where(BacktestRun.id == run_id).values(**fields))
        await s.commit()


async def get_backtest(run_id: int) -> BacktestRun | None:
    async with session() as s:
        return await s.get(BacktestRun, run_id)


async def list_backtests(limit: int = 50) -> list[BacktestRun]:
    async with session() as s:
        return list((await s.execute(select(BacktestRun)
                    .order_by(desc(BacktestRun.created_at)).limit(limit))).scalars())


async def delete_backtest(run_id: int) -> None:
    async with session() as s:
        await s.execute(delete(BacktestRun).where(BacktestRun.id == run_id))
        await s.commit()
