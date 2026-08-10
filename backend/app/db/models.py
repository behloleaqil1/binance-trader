"""SQLAlchemy models. SQLite in WAL mode — a single local file under data/."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class BotState(Base):
    """Singleton row (id=1) persisting engine state across restarts.

    The kill switch lives here on purpose: a restart must NOT resurrect
    trading after a drawdown kill.
    """
    __tablename__ = "bot_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(16), default="STOPPED")
    status_reason: Mapped[str] = mapped_column(Text, default="")
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    day_start_equity: Mapped[float] = mapped_column(Float, default=0.0)
    day_start_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD UTC
    killed_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class KVConfig(Base):
    """JSON config blobs editable from the dashboard: 'risk', 'scanner', 'engine'."""
    __tablename__ = "kv_configs"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # strategy slug
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    symbols: Mapped[list] = mapped_column(JSON, default=list)
    use_scanner: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")  # e.g. "grid paused: out of range"
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    exchange_order_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    oco_list_id: Mapped[str] = mapped_column(String(32), default="")
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(4))
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="NEW", index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    strategy_id: Mapped[str] = mapped_column(String(32), default="")
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), default=None)
    price: Mapped[float | None] = mapped_column(Float, default=None)
    stop_price: Mapped[float | None] = mapped_column(Float, default=None)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    filled_qty: Mapped[float] = mapped_column(Float, default=0.0)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, default=None)
    fee_quote: Mapped[float] = mapped_column(Float, default=0.0)  # fees converted to quote
    reason: Mapped[str] = mapped_column(Text, default="")
    grid_level: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(8), default="OPEN", index=True)  # OPEN/CLOSED
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry: Mapped[float] = mapped_column(Float, default=0.0)
    entry_fee_quote: Mapped[float] = mapped_column(Float, default=0.0)
    sl_price: Mapped[float | None] = mapped_column(Float, default=None)
    tp_price: Mapped[float | None] = mapped_column(Float, default=None)
    trailing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    high_watermark: Mapped[float] = mapped_column(Float, default=0.0)
    oco_list_id: Mapped[str] = mapped_column(String(32), default="")
    protected: Mapped[bool] = mapped_column(Boolean, default=False)  # OCO live on exchange
    entry_reason: Mapped[str] = mapped_column(Text, default="")
    grid_level: Mapped[int | None] = mapped_column(Integer, default=None)
    opened_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)


class Trade(Base):
    """A completed round-trip (position opened and fully closed)."""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    pnl_quote: Mapped[float] = mapped_column(Float)     # net of fees
    pnl_pct: Mapped[float] = mapped_column(Float)
    fees_quote: Mapped[float] = mapped_column(Float, default=0.0)
    entry_reason: Mapped[str] = mapped_column(Text, default="")
    exit_reason: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(index=True)
    closed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class SignalLog(Base):
    """BUY/SELL signals and risk rejections. HOLDs stay in an in-memory ring."""
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    strategy_id: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(4))
    price: Mapped[float | None] = mapped_column(Float, default=None)
    reason: Mapped[str] = mapped_column(Text, default="")
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_reason: Mapped[str] = mapped_column(Text, default="")


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    equity: Mapped[float] = mapped_column(Float)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_today: Mapped[float] = mapped_column(Float, default=0.0)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # DAILY_HALT/KILL/EMERGENCY/REJECT
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class BacktestRun(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    label: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(10), default="RUNNING")  # RUNNING/DONE/ERROR
    error: Mapped[str] = mapped_column(Text, default="")
    strategy_id: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(4))
    start: Mapped[str] = mapped_column(String(10))
    end: Mapped[str] = mapped_column(String(10))
    initial_equity: Mapped[float] = mapped_column(Float, default=10_000.0)
    fee_bps: Mapped[float] = mapped_column(Float, default=10.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=5.0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    equity_curve: Mapped[list] = mapped_column(JSON, default=list)  # [[ts_ms, equity], …]
    trades: Mapped[list] = mapped_column(JSON, default=list)        # capped at 1000


class AuthSession(Base):
    """Dashboard login sessions — only the SHA-256 of the token is stored."""
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(index=True)


class KlineCache(Base):
    __tablename__ = "klines_cache"
    __table_args__ = (Index("ix_kline_lookup", "symbol", "timeframe", "open_time"),)

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(4), primary_key=True)
    open_time: Mapped[int] = mapped_column(Integer, primary_key=True)  # ms epoch
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    close_time: Mapped[int] = mapped_column(Integer)
