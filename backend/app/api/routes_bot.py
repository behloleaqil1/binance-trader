"""Bot control, account, and risk endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_engine
from app.api.schemas import EmergencyStopBody
from app.core.engine import TradingEngine
from app.core.exchange import ExchangeError
from app.db import repo
from app.risk.models import RiskConfig, ScannerConfig

router = APIRouter(tags=["bot"])


@router.get("/status")
async def status(engine: TradingEngine = Depends(get_engine)):
    state = await repo.get_bot_state()
    payload = engine.status_payload()
    payload["persisted_status"] = state.status
    payload["persisted_reason"] = state.status_reason
    return payload


@router.post("/bot/start")
async def start(engine: TradingEngine = Depends(get_engine)):
    try:
        await engine.start()
    except (RuntimeError, ExchangeError) as e:
        detail = str(e)
        if "-2015" in detail or "-2014" in detail:
            detail += (" — wrong environment or key type? In TESTNET mode use keys "
                       "from https://testnet.binance.vision, not real-account keys.")
        raise HTTPException(400, detail) from e
    return engine.status_payload()


@router.post("/bot/pause")
async def pause(engine: TradingEngine = Depends(get_engine)):
    await engine.pause()
    return engine.status_payload()


@router.post("/bot/resume")
async def resume(engine: TradingEngine = Depends(get_engine)):
    await engine.resume()
    return engine.status_payload()


@router.post("/bot/stop")
async def stop(engine: TradingEngine = Depends(get_engine)):
    await engine.stop()
    return engine.status_payload()


@router.post("/bot/emergency-stop")
async def emergency_stop(body: EmergencyStopBody,
                         engine: TradingEngine = Depends(get_engine)):
    """Cancel ALL open orders now; optionally market-close every position."""
    try:
        result = await engine.emergency_stop(body.flatten)
    except (RuntimeError, ExchangeError) as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, **result}


@router.post("/bot/reset-kill")
async def reset_kill(engine: TradingEngine = Depends(get_engine)):
    try:
        await engine.reset_kill()
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    return engine.status_payload()


@router.get("/account")
async def account(engine: TradingEngine = Depends(get_engine)):
    acct = await engine._account_state()  # noqa: SLF001 — engine is our own
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                   microsecond=0)
    realized_today = await repo.realized_pnl_since(day_start)
    balances = {a: {"free": f, "locked": l}
                for a, (f, l) in sorted(engine.portfolio.balances.items())
                if a == engine.portfolio.quote
                or a in engine.portfolio.tracked_bases or a == "BNB"}
    return {
        "equity": round(acct.equity, 4),
        "day_start_equity": round(acct.day_start_equity, 4),
        "day_pnl": round(acct.equity - acct.day_start_equity, 4)
                   if acct.day_start_equity else 0.0,
        "realized_pnl_today": round(realized_today, 4),
        "unrealized_pnl": round(sum(p.unrealized_pnl for p in acct.open_positions), 4),
        "peak_equity": round(acct.peak_equity, 4),
        "balances": balances,
        "prices": {s: p for s, p in sorted(engine.portfolio.prices.items())},
    }


@router.get("/risk")
async def get_risk():
    # Merge through the model so configs saved before new fields existed
    # still return every field with its default (the UI binds to all of them).
    return RiskConfig(**(await repo.get_config("risk") or {})).model_dump()


@router.put("/risk")
async def put_risk(body: dict, engine: TradingEngine = Depends(get_engine)):
    try:
        cfg = RiskConfig(**body)  # full-model validation, no partial writes
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    await repo.set_config("risk", cfg.model_dump())
    await engine.on_configs_changed()
    return cfg.model_dump()


@router.get("/risk/usage")
async def risk_usage(engine: TradingEngine = Depends(get_engine)):
    acct = await engine._account_state()  # noqa: SLF001
    return {"usage": engine.risk.usage(acct), "status": engine.status.value}


@router.get("/risk/events")
async def risk_events(limit: int = 50):
    rows = await repo.list_risk_events(min(limit, 200))
    return [{"ts": r.ts.isoformat(), "kind": r.kind, "detail": r.detail} for r in rows]


@router.get("/scanner")
async def get_scanner(engine: TradingEngine = Depends(get_engine)):
    return {"config": await repo.get_config("scanner"), "current": engine.scanned}


@router.put("/scanner")
async def put_scanner(body: dict, engine: TradingEngine = Depends(get_engine)):
    try:
        cfg = ScannerConfig(**body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    await repo.set_config("scanner", cfg.model_dump())
    await engine.on_configs_changed()
    return cfg.model_dump()
