"""Structured logging: human-readable console + JSON-lines file for auditing.

Every signal, order, fill, risk decision and error flows through here (and is
additionally persisted to the DB by the event bus).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

SECRET_KEYS = ("api_key", "api_secret", "secret", "token", "signature", "listenkey")


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = _redact(extra)
        if record.exc_info and record.exc_info[0]:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _redact(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if any(s in k.lower() for s in SECRET_KEYS):
            out[k] = "«redacted»"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


def setup_logging(level: str = "INFO", log_dir: str = "data") -> None:
    os.makedirs(log_dir, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-24s %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(console)

    jsonl = RotatingFileHandler(
        os.path.join(log_dir, "events.jsonl"), maxBytes=20_000_000, backupCount=5)
    jsonl.setFormatter(JsonLineFormatter())
    root.addHandler(jsonl)

    # Binance client is chatty at DEBUG; keep third-party noise down.
    for noisy in ("websockets", "aiohttp", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log_event(logger: logging.Logger, msg: str, **data) -> None:
    """Log with structured extras that the JSON handler serializes."""
    logger.info(msg, extra={"data": data})
