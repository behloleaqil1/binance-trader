"""Backtest orchestration: download data → simulate (worker thread) → persist."""
from __future__ import annotations

import asyncio
import logging

from app.backtest import data as data_mod
from app.backtest.metrics import compute_metrics, downsample_curve
from app.backtest.simulator import (SimConfig, run_candle_backtest,
                                    run_dca_backtest, run_grid_backtest)
from app.db import repo
from app.db.models import BacktestRun
from app.risk.models import RiskConfig
from app.strategies.dca import DCAStrategy
from app.strategies.grid import GridStrategy
from app.strategies.registry import build as build_strategy

log = logging.getLogger("backtest")


async def launch_backtest(payload: dict) -> int:
    """Validate, persist a RUNNING row, and simulate in the background.
    Returns the run id immediately."""
    strategy = build_strategy(payload["strategy_id"], payload.get("params") or {})
    risk = RiskConfig(**{**(await repo.get_config("risk")),
                         **(payload.get("risk") or {})})
    timeframe = payload.get("timeframe") or getattr(strategy, "timeframe", "1h")
    run = await repo.save_backtest(BacktestRun(
        label=payload.get("label") or "",
        strategy_id=strategy.id, symbol=payload["symbol"].upper(),
        timeframe=timeframe, start=payload["start"], end=payload["end"],
        initial_equity=float(payload.get("initial_equity") or 10_000),
        fee_bps=float(payload.get("fee_bps") if payload.get("fee_bps") is not None else 10),
        slippage_bps=float(payload.get("slippage_bps")
                           if payload.get("slippage_bps") is not None else 5),
        params=strategy.params, risk=risk.model_dump(), status="RUNNING"))
    asyncio.get_running_loop().create_task(_run(run.id, strategy, risk, run))
    return run.id


async def _run(run_id: int, strategy, risk: RiskConfig, run: BacktestRun) -> None:
    try:
        df = await data_mod.fetch_klines(run.symbol, run.timeframe, run.start, run.end)
        if len(df) < strategy.required_history() + 5:
            raise RuntimeError(f"only {len(df)} candles in range — extend the date "
                               f"range or use a smaller timeframe")
        cfg = SimConfig(initial_equity=run.initial_equity, fee_bps=run.fee_bps,
                        slippage_bps=run.slippage_bps)

        def simulate():
            if isinstance(strategy, GridStrategy):
                return run_grid_backtest(strategy, df, cfg)
            if isinstance(strategy, DCAStrategy):
                return run_dca_backtest(strategy, df, cfg,
                                        data_mod.interval_ms(run.timeframe))
            return run_candle_backtest(strategy, risk, df, cfg, symbol=run.symbol)

        result = await asyncio.to_thread(simulate)
        metrics = compute_metrics(result.equity, result.trades, run.initial_equity,
                                  df, result.extras.get("warmup", 0))
        metrics.update({k: v for k, v in result.extras.items() if k != "buys"})
        await repo.update_backtest(
            run_id, status="DONE", metrics=metrics,
            equity_curve=downsample_curve(result.equity),
            trades=result.trades[-1000:] or result.extras.get("buys", []))
        log.info("backtest %s done: %s %s %s → return %.2f%%, %d trades", run_id,
                 run.strategy_id, run.symbol, run.timeframe,
                 metrics["total_return_pct"], metrics["n_trades"])
    except Exception as e:  # noqa: BLE001 — persist the failure for the UI
        log.exception("backtest %s failed: %s", run_id, e)
        await repo.update_backtest(run_id, status="ERROR", error=str(e))
