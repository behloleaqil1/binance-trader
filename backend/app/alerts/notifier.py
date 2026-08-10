"""Optional alerting: Telegram and/or a generic JSON webhook.

Subscribes to the event bus and forwards ALERT events (fills, stop-losses,
kill-switch, emergencies). Failures are logged and never affect trading.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import Settings
from app.core.events import EventBus

log = logging.getLogger("alerts")

_MIN_INTERVAL_PER_KIND = 3.0   # seconds; collapses alert storms
_IMPORTANT = {"kill", "risk"}  # never rate-limited


class Notifier:
    def __init__(self, settings: Settings, bus: EventBus):
        self.s = settings
        self._last_sent: dict[str, float] = {}
        # Always subscribe: channels are checked per send, so alerting starts
        # working the moment credentials are added on the Settings page.
        bus.subscribe(self._on_event)
        if self.enabled:
            log.info("alerting enabled (%s)", ", ".join(self.channels))

    @property
    def channels(self) -> list[str]:
        out = []
        if self.s.telegram_bot_token and self.s.telegram_chat_id:
            out.append("telegram")
        if self.s.alert_webhook_url:
            out.append("webhook")
        if self.s.whatsapp_phone and self.s.whatsapp_apikey:
            out.append("whatsapp")
        if self.s.whatsapp_phone and self.s.meta_wa_token and self.s.meta_wa_phone_id:
            out.append("meta-whatsapp")
        if self.s.ntfy_topic:
            out.append("ntfy")
        return out

    @property
    def enabled(self) -> bool:
        return bool(self.channels)

    async def _on_event(self, event: dict) -> None:
        if event.get("type") != "alert" or not self.enabled:
            return
        data = event.get("data", {})
        kind = data.get("kind", "info")
        now = time.monotonic()
        if kind not in _IMPORTANT and now - self._last_sent.get(kind, 0) < _MIN_INTERVAL_PER_KIND:
            return
        self._last_sent[kind] = now
        title, body = data.get("title", "Bot alert"), data.get("body", "")
        env = "TESTNET" if self.s.testnet else "LIVE"
        text = f"[{env}] {title}\n{body}"
        await asyncio.gather(self._send_telegram(text),
                             self._send_whatsapp(text),
                             self._send_meta_whatsapp(text),
                             self._send_ntfy(kind, f"[{env}] {title}", body),
                             self._send_webhook({"env": env, "kind": kind,
                                                 "title": title, "body": body,
                                                 "ts": event.get("ts")}),
                             return_exceptions=True)

    async def _send_ntfy(self, kind: str, title: str, body: str) -> None:
        """Push to the ntfy.sh app. Free, no account; the user subscribes to
        the topic on their phone."""
        if not self.s.ntfy_topic:
            return
        # kill/risk alerts ring through even on silent; fills stay default.
        priority = "urgent" if kind == "kill" else ("high" if kind in _IMPORTANT
                                                     else "default")
        tags = {"kill": "rotating_light", "risk": "warning",
                "stop_loss": "chart_with_downwards_trend",
                "fill": "moneybag"}.get(kind, "robot")
        url = f"{self.s.ntfy_server.rstrip('/')}/{self.s.ntfy_topic}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, content=(body or title)[:1500].encode(),
                                      headers={"Title": title[:200],
                                               "Priority": priority, "Tags": tags})
                if r.status_code >= 300:
                    log.warning("ntfy alert failed: %s %s", r.status_code, r.text[:200])
        except httpx.HTTPError as e:
            log.warning("ntfy alert error: %s", e)

    async def _send_telegram(self, text: str) -> None:
        if not (self.s.telegram_bot_token and self.s.telegram_chat_id):
            return
        url = f"https://api.telegram.org/bot{self.s.telegram_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json={"chat_id": self.s.telegram_chat_id,
                                                 "text": text[:4000]})
                if r.status_code != 200:
                    log.warning("telegram alert failed: %s %s", r.status_code, r.text[:200])
        except httpx.HTTPError as e:
            log.warning("telegram alert error: %s", e)

    async def _send_webhook(self, payload: dict) -> None:
        if not self.s.alert_webhook_url:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self.s.alert_webhook_url, json=payload)
        except httpx.HTTPError as e:
            log.warning("webhook alert error: %s", e)

    async def _send_meta_whatsapp(self, text: str) -> None:
        """WhatsApp via Meta's official Cloud API. Free-form text works inside
        the 24h service window (opened whenever the user messages the test
        number); outside it, falls back to the configured template."""
        if not (self.s.whatsapp_phone and self.s.meta_wa_token
                and self.s.meta_wa_phone_id):
            return
        url = (f"https://graph.facebook.com/v21.0/"
               f"{self.s.meta_wa_phone_id}/messages")
        headers = {"Authorization": f"Bearer {self.s.meta_wa_token}"}
        to = self.s.whatsapp_phone.lstrip("+")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, headers=headers, json={
                    "messaging_product": "whatsapp", "to": to,
                    "type": "text", "text": {"body": text[:3500]}})
                if r.status_code == 200:
                    return
                if self.s.meta_wa_template:  # outside 24h window → template
                    r2 = await client.post(url, headers=headers, json={
                        "messaging_product": "whatsapp", "to": to,
                        "type": "template", "template": {
                            "name": self.s.meta_wa_template,
                            "language": {"code": "en_US"},
                            "components": [{"type": "body", "parameters": [
                                {"type": "text", "text": text[:1000]}]}]}})
                    if r2.status_code == 200:
                        return
                    log.warning("meta whatsapp template failed: %s %s",
                                r2.status_code, r2.text[:200])
                else:
                    log.warning("meta whatsapp alert failed: %s %s",
                                r.status_code, r.text[:200])
        except httpx.HTTPError as e:
            log.warning("meta whatsapp alert error: %s", e)

    async def _send_whatsapp(self, text: str) -> None:
        """Personal WhatsApp via CallMeBot's free gateway."""
        if not (self.s.whatsapp_phone and self.s.whatsapp_apikey):
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get("https://api.callmebot.com/whatsapp.php",
                                     params={"phone": self.s.whatsapp_phone,
                                             "apikey": self.s.whatsapp_apikey,
                                             "text": text[:1000]})
                if r.status_code != 200:
                    log.warning("whatsapp alert failed: %s %s", r.status_code,
                                r.text[:200])
        except httpx.HTTPError as e:
            log.warning("whatsapp alert error: %s", e)
