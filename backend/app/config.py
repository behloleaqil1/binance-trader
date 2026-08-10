"""Process-level configuration loaded from environment / .env file.

Only deployment-level settings live here. Everything the user edits from the
dashboard (risk limits, strategy parameters, scanner config) is stored in the
database so it survives restarts and is auditable.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads the project-root .env when run from backend/ (run.sh) and a local
    # backend/.env if present (the local file wins). In Docker, compose injects
    # real env vars, which take priority over any file.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"),
                                      env_file_encoding="utf-8", extra="ignore")

    # Safety default: the bot starts on the Spot Testnet unless explicitly
    # flipped to live in .env. There is no API or UI toggle for this on purpose.
    testnet: bool = True

    binance_api_key: str = ""
    binance_api_secret: str = ""

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Initial dashboard login, used ONLY on first boot to seed the DB record.
    # If auth_password is empty, a random one is generated and printed to the
    # console once. Afterwards credentials are managed from the Settings page.
    auth_username: str = "admin"
    auth_password: str = ""

    db_path: str = "data/bot.db"
    log_level: str = "INFO"
    # Comma-separated extra CORS origins for a hosted dashboard on another host.
    cors_origins: str = ""
    # ntfy.sh push notifications: install the ntfy app, subscribe to this topic.
    # Anyone who knows the topic can send you messages, so keep it unguessable.
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_webhook_url: str = ""
    # WhatsApp via CallMeBot (free personal gateway): the user activates it by
    # WhatsApp-messaging "I allow callmebot to send me messages" to the
    # CallMeBot number, which replies with the personal API key.
    whatsapp_phone: str = ""
    whatsapp_apikey: str = ""
    # WhatsApp via Meta's official Cloud API (developer test mode: free,
    # messages only pre-verified recipients). whatsapp_phone doubles as the
    # recipient. Template used as fallback outside the 24h reply window.
    meta_wa_token: str = ""
    meta_wa_phone_id: str = ""
    meta_wa_template: str = ""

    # Cancel unknown bot-prefixed orders found on the exchange at startup
    # (orders we placed but lost track of, e.g. after a crash).
    cancel_orphan_orders: bool = True

    # Start trading automatically when the server boots. Off by default:
    # the user presses Start in the dashboard.
    auto_start: bool = False

    quote_asset: str = "USDT"

    @property
    def has_keys(self) -> bool:
        return bool(self.binance_api_key and self.binance_api_secret)

    def masked_key(self) -> str:
        """Key fingerprint safe for logs/UI — never log the full key or secret."""
        k = self.binance_api_key
        return f"{k[:4]}…{k[-4:]}" if len(k) >= 12 else ("(set)" if k else "(not set)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
