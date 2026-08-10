"""UI-editable settings, persisted in the DB and applied onto the process-wide
Settings singleton (every component holds a reference to that same object, so
changes take effect immediately).

Deliberately NOT editable from the UI:
  - testnet: flipping to live trading stays a manual .env edit + restart, so a
    stolen dashboard password can never switch the bot onto real funds.
  - api_host/api_port/db_path/log_level: process-level, need a restart anyway.
"""
from __future__ import annotations

from app.config import Settings
from app.db import repo

# Fields the UI may override; secrets are write-only through the API.
OVERRIDABLE = ("binance_api_key", "binance_api_secret", "telegram_bot_token",
               "telegram_chat_id", "alert_webhook_url", "whatsapp_phone",
               "whatsapp_apikey", "meta_wa_token", "meta_wa_phone_id",
               "meta_wa_template", "auto_start", "cancel_orphan_orders",
               "quote_asset")
SECRET_FIELDS = {"binance_api_key", "binance_api_secret", "telegram_bot_token",
                 "whatsapp_apikey", "meta_wa_token"}
# Changing these while the engine trades would desync it — require STOPPED.
REQUIRE_STOPPED = {"binance_api_key", "binance_api_secret", "quote_asset"}


async def apply_overrides(settings: Settings) -> None:
    """Boot-time: layer stored UI overrides over the .env values."""
    stored = await repo.get_config("settings")
    for key in OVERRIDABLE:
        if key in stored:
            setattr(settings, key, stored[key])


async def save_overrides(settings: Settings, changes: dict) -> None:
    stored = await repo.get_config("settings")
    for key, value in changes.items():
        if key not in OVERRIDABLE:
            continue
        stored[key] = value
        setattr(settings, key, value)
    await repo.set_config("settings", stored)
