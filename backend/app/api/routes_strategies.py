"""Strategy configuration endpoints (list, edit, recent evaluations)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_engine
from app.api.schemas import StrategyUpdateBody
from app.core.engine import TradingEngine
from app.db import repo
from app.strategies.registry import STRATEGY_CLASSES

router = APIRouter(tags=["strategies"])


@router.get("/strategies")
async def list_strategies(engine: TradingEngine = Depends(get_engine)):
    rows = {r.id: r for r in await repo.list_strategy_configs()}
    out = []
    for sid, cls in STRATEGY_CLASSES.items():
        row = rows.get(sid)
        out.append({
            "id": sid, "name": cls.name, "description": cls.description,
            "kind": cls.kind,
            "enabled": row.enabled if row else False,
            "params": row.params if row else cls.default_params(),
            "symbols": list(row.symbols) if row else [],
            "use_scanner": row.use_scanner if row else False,
            "note": row.note if row else "",
            "param_specs": [p.to_dict() for p in cls.param_specs()],
            "effective_symbols": engine.effective_symbols(sid),
            "adaptive": engine.adaptive_state_for(sid).to_dict(),
        })
    return out


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, body: StrategyUpdateBody,
                          engine: TradingEngine = Depends(get_engine)):
    cls = STRATEGY_CLASSES.get(strategy_id)
    if cls is None:
        raise HTTPException(404, f"unknown strategy {strategy_id}")
    fields: dict = {}
    if body.params is not None:
        try:
            fields["params"] = cls.validate_params(body.params)
        except (ValueError, TypeError) as e:
            raise HTTPException(422, f"invalid params: {e}") from e
    if body.symbols is not None:
        fields["symbols"] = [s.upper().strip() for s in body.symbols if s.strip()]
    if body.enabled is not None:
        fields["enabled"] = body.enabled
    if body.use_scanner is not None:
        fields["use_scanner"] = body.use_scanner
    if not fields:
        raise HTTPException(422, "nothing to update")
    fields["note"] = ""  # config change clears stale notes (e.g. grid pause)
    await repo.update_strategy_config(strategy_id, **fields)
    if strategy_id == "grid":
        await engine.clear_grid_state()  # ladder rebuilds from fresh params
    await engine.on_configs_changed()
    return {"ok": True}


@router.get("/strategies/{strategy_id}/evaluations")
async def evaluations(strategy_id: str, engine: TradingEngine = Depends(get_engine)):
    """Recent signals including HOLDs — answers 'why isn't it trading?'."""
    if strategy_id not in STRATEGY_CLASSES:
        raise HTTPException(404, f"unknown strategy {strategy_id}")
    return list(engine.evaluations.get(strategy_id, []))[::-1]
