"""Shared datatypes used across strategies, risk engine, engine and backtester.

Kept dependency-light (dataclasses + enums only) so every layer can import
them without circular imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class BotStatus(str, Enum):
    STOPPED = "STOPPED"          # engine not evaluating; exchange-side OCO protection stays
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"            # exits managed, no new entries
    DAILY_HALT = "DAILY_HALT"    # daily loss limit breached; auto-clears next UTC day
    KILLED = "KILLED"            # drawdown kill switch; requires manual reset


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderPurpose(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    GRID_BUY = "GRID_BUY"
    GRID_SELL = "GRID_SELL"
    DCA_BUY = "DCA_BUY"
    EMERGENCY = "EMERGENCY"


class EventType(str, Enum):
    STATUS = "status"
    TICK = "tick"
    CANDLE = "candle"
    SIGNAL = "signal"
    ORDER = "order"
    TRADE = "trade"
    POSITION = "position"
    EQUITY = "equity"
    RISK = "risk"
    SCANNER = "scanner"
    ERROR = "error"
    ALERT = "alert"


@dataclass(slots=True)
class Candle:
    open_time: int  # ms epoch
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    closed: bool = True

    @property
    def open_dt(self) -> datetime:
        return datetime.fromtimestamp(self.open_time / 1000, tz=timezone.utc)


@dataclass(slots=True)
class Signal:
    action: SignalAction
    symbol: str
    strategy_id: str
    reason: str
    price: float | None = None
    # DCA/grid propose a fixed quote amount instead of %-of-equity sizing.
    notional_override: float | None = None
    # DCA accumulation may opt out of stops (see RiskConfig.exempt_dca_from_stops).
    wants_protection: bool = True
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PositionView:
    """Read-only snapshot of an open position, as the risk engine sees it."""
    id: int
    symbol: str
    strategy_id: str
    qty: float
    avg_entry: float
    mark_price: float

    @property
    def notional(self) -> float:
        return self.qty * self.mark_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.mark_price - self.avg_entry) * self.qty


@dataclass(slots=True)
class AccountState:
    """Snapshot handed to the risk engine for every decision."""
    equity: float
    day_start_equity: float
    peak_equity: float
    status: BotStatus
    open_positions: list[PositionView] = field(default_factory=list)
    # Notional of open (unfilled) BUY orders per symbol — counts toward exposure.
    open_buy_notional: dict[str, float] = field(default_factory=dict)

    def positions_for(self, symbol: str) -> list[PositionView]:
        return [p for p in self.open_positions if p.symbol == symbol]

    @property
    def daily_loss_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return max(0.0, (self.day_start_equity - self.equity) / self.day_start_equity * 100)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100)


@dataclass(slots=True)
class OrderPlan:
    """A fully-specified order approved by the risk engine."""
    symbol: str
    side: str                    # BUY / SELL
    type: str                    # MARKET / LIMIT
    qty: float
    purpose: OrderPurpose
    strategy_id: str
    reason: str
    price: float | None = None   # for LIMIT
    sl_price: float | None = None
    tp_price: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str                          # human-readable rationale (logged always)
    plan: OrderPlan | None = None
    checks: list[str] = field(default_factory=list)  # every check that ran, for audit
