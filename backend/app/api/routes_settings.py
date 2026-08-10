"""General settings endpoints (everything UI-configurable that isn't risk,
scanner or strategy config). Secrets are write-only: they can be set or
cleared, never read back — GET returns fingerprints/flags only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import settings_store
from app.api.deps import get_engine
from app.config import Settings, get_settings
from app.core.engine import TradingEngine
from app.core.types import BotStatus
from app.db import repo

router = APIRouter(tags=["settings"])


class SettingsUpdate(BaseModel):
    """None = leave unchanged; empty string = clear (secrets only)."""
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    alert_webhook_url: str | None = None
    whatsapp_phone: str | None = None
    whatsapp_apikey: str | None = None
    meta_wa_token: str | None = None
    meta_wa_phone_id: str | None = None
    meta_wa_template: str | None = None
    ntfy_topic: str | None = None
    auto_start: bool | None = None
    cancel_orphan_orders: bool | None = None
    quote_asset: str | None = Field(None, min_length=3, max_length=10)


@router.get("/settings")
async def get_settings_view(settings: Settings = Depends(get_settings)):
    auth = await repo.get_config("auth")
    return {
        # read-only facts (the live/testnet switch is .env-only by design)
        "testnet": settings.testnet,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        # editable
        "quote_asset": settings.quote_asset,
        "auto_start": settings.auto_start,
        "cancel_orphan_orders": settings.cancel_orphan_orders,
        "telegram_chat_id": settings.telegram_chat_id,
        "alert_webhook_url": settings.alert_webhook_url,
        "whatsapp_phone": settings.whatsapp_phone,
        "meta_wa_phone_id": settings.meta_wa_phone_id,
        "meta_wa_template": settings.meta_wa_template,
        "ntfy_topic": settings.ntfy_topic,
        # secrets: presence + fingerprint only, never the value
        "api_key_fingerprint": settings.masked_key(),
        "api_secret_set": bool(settings.binance_api_secret),
        "telegram_token_set": bool(settings.telegram_bot_token),
        "whatsapp_apikey_set": bool(settings.whatsapp_apikey),
        "meta_wa_token_set": bool(settings.meta_wa_token),
        "username": auth.get("username", "admin"),
    }


@router.put("/settings")
async def update_settings(body: SettingsUpdate,
                          settings: Settings = Depends(get_settings),
                          engine: TradingEngine = Depends(get_engine)):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(422, "nothing to update")
    if changes.get("quote_asset"):
        changes["quote_asset"] = changes["quote_asset"].upper()

    critical = settings_store.REQUIRE_STOPPED & changes.keys()
    if critical and engine.status not in (BotStatus.STOPPED, BotStatus.KILLED):
        raise HTTPException(
            400, f"stop the bot before changing: {', '.join(sorted(critical))}")

    await settings_store.save_overrides(settings, changes)

    if critical:
        # Drop the gateway so the next Start reconnects with new credentials.
        await engine.shutdown()
        engine.portfolio.quote = settings.quote_asset
    return await get_settings_view(settings)
