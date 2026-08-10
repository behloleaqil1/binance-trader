"""Async SQLite engine/session plus first-run seeding of default configs."""
from __future__ import annotations

import os

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Base, BotState, KVConfig, StrategyConfig

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings):
    global _engine, _session_factory
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    _engine = create_async_engine(f"sqlite+aiosqlite:///{settings.db_path}")

    @event.listens_for(_engine.sync_engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session() -> AsyncSession:
    assert _session_factory is not None, "init_engine() not called"
    return _session_factory()


async def create_all_and_seed(settings: Settings) -> None:
    from app.risk.models import RiskConfig, ScannerConfig  # local import: avoid cycle
    from app.strategies.registry import STRATEGY_CLASSES

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session() as s:
        if (await s.execute(select(BotState).where(BotState.id == 1))).scalar_one_or_none() is None:
            s.add(BotState(id=1, status="STOPPED", status_reason="initial state"))

        for key, default in (("risk", RiskConfig().model_dump()),
                             ("scanner", ScannerConfig().model_dump())):
            if (await s.get(KVConfig, key)) is None:
                s.add(KVConfig(key=key, value=default))

        # Default pairs chosen at setup; all editable in the dashboard.
        default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        for cls in STRATEGY_CLASSES.values():
            if (await s.get(StrategyConfig, cls.id)) is None:
                s.add(StrategyConfig(
                    id=cls.id,
                    enabled=False,  # safe default: user enables per strategy in the UI
                    params=cls.default_params(),
                    symbols=default_symbols if cls.id != "grid" else ["BTCUSDT"],
                    use_scanner=False,
                ))
        await s.commit()


async def dispose() -> None:
    if _engine is not None:
        await _engine.dispose()
