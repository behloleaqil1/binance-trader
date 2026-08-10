"""Backtesting endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import BacktestCreateBody
from app.backtest.runner import launch_backtest
from app.db import repo

router = APIRouter(tags=["backtest"])


def _row_summary(r) -> dict:
    return {"id": r.id, "created_at": r.created_at.isoformat(), "label": r.label,
            "status": r.status, "error": r.error, "strategy_id": r.strategy_id,
            "symbol": r.symbol, "timeframe": r.timeframe, "start": r.start,
            "end": r.end, "initial_equity": r.initial_equity,
            "fee_bps": r.fee_bps, "slippage_bps": r.slippage_bps,
            "params": r.params, "metrics": r.metrics}


@router.post("/backtests")
async def create_backtest(body: BacktestCreateBody):
    try:
        run_id = await launch_backtest(body.model_dump())
    except (KeyError, ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e)) from e
    return {"id": run_id, "status": "RUNNING"}


@router.get("/backtests")
async def list_backtests(limit: int = 50):
    return [_row_summary(r) for r in await repo.list_backtests(min(limit, 100))]


@router.get("/backtests/{run_id}")
async def get_backtest(run_id: int):
    r = await repo.get_backtest(run_id)
    if r is None:
        raise HTTPException(404, "backtest not found")
    return {**_row_summary(r), "risk": r.risk, "equity_curve": r.equity_curve,
            "trades": r.trades}


@router.delete("/backtests/{run_id}")
async def remove_backtest(run_id: int):
    await repo.delete_backtest(run_id)
    return {"ok": True}
