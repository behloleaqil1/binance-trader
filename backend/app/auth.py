"""Single-user authentication.

- Credentials: one username + password. Initial values come from .env
  (AUTH_USERNAME / AUTH_PASSWORD); if no password is provided on first boot a
  random one is generated and printed to the console once. After that the
  hash lives in the DB and is changed from the dashboard.
- Passwords: PBKDF2-HMAC-SHA256, 600k iterations, per-install salt (stdlib
  only — no extra dependency).
- Sessions: random bearer tokens; only their SHA-256 lands in the DB. The
  frontend sends the token as `Authorization: Bearer …` (REST) or `?token=`
  (WebSocket).
- Brute force: per-IP throttle — 5 failed logins locks that IP for 60s.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.config import Settings
from app.db.database import session as db_session
from app.db.models import AuthSession
from app.db import repo

log = logging.getLogger("auth")

SESSION_TTL = timedelta(days=7)
_PBKDF2_ITERS = 600_000
_failed: dict[str, list[float]] = {}   # ip -> recent failure timestamps
_LOCK_AFTER, _LOCK_WINDOW = 5, 60.0


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt),
                               _PBKDF2_ITERS).hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected_hash)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; all our stored times are UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def ensure_auth_seed(settings: Settings) -> None:
    """Create the credential record on first boot."""
    auth = await repo.get_config("auth")
    if auth.get("pw_hash"):
        return
    username = settings.auth_username or "admin"
    password = settings.auth_password
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    salt = secrets.token_hex(16)
    await repo.set_config("auth", {"username": username, "salt": salt,
                                   "pw_hash": hash_password(password, salt)})
    if generated:
        log.warning("═" * 62)
        log.warning("  FIRST BOOT — dashboard login created")
        log.warning("    username: %s", username)
        log.warning("    password: %s", password)
        log.warning("  Change it from Settings after logging in.")
        log.warning("  (Set AUTH_PASSWORD in .env before first boot to choose one.)")
        log.warning("═" * 62)
    else:
        log.info("dashboard login seeded for user %r from .env", username)


# ── session store ────────────────────────────────────────────────────────────
async def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    async with db_session() as s:
        s.add(AuthSession(token_hash=_token_hash(token), username=username,
                          created_at=now, expires_at=now + SESSION_TTL))
        # opportunistic cleanup of expired sessions
        await s.execute(delete(AuthSession).where(AuthSession.expires_at < now))
        await s.commit()
    return token


async def validate_session(token: str) -> str | None:
    """Returns the username for a live session, else None."""
    if not token:
        return None
    async with db_session() as s:
        row = (await s.execute(select(AuthSession).where(
            AuthSession.token_hash == _token_hash(token)))).scalar_one_or_none()
        if row is None:
            return None
        if _aware(row.expires_at) < datetime.now(timezone.utc):
            await s.delete(row)
            await s.commit()
            return None
        return row.username


async def destroy_session(token: str) -> None:
    async with db_session() as s:
        await s.execute(delete(AuthSession).where(
            AuthSession.token_hash == _token_hash(token)))
        await s.commit()


async def destroy_other_sessions(keep_token: str) -> None:
    async with db_session() as s:
        await s.execute(delete(AuthSession).where(
            AuthSession.token_hash != _token_hash(keep_token)))
        await s.commit()


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:] if header.startswith("Bearer ") else ""


async def require_session(request: Request) -> str:
    """FastAPI dependency: every protected route runs through this."""
    user = await validate_session(_bearer(request))
    if user is None:
        raise HTTPException(401, "not authenticated")
    return user


# ── throttle ─────────────────────────────────────────────────────────────────
def _locked(ip: str) -> float:
    now = time.monotonic()
    fails = [t for t in _failed.get(ip, []) if now - t < _LOCK_WINDOW]
    _failed[ip] = fails
    if len(fails) >= _LOCK_AFTER:
        return _LOCK_WINDOW - (now - fails[0])
    return 0.0


def _record_failure(ip: str) -> None:
    _failed.setdefault(ip, []).append(time.monotonic())


# ── routes ───────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    new_username: str | None = Field(None, min_length=1, max_length=64)


@router.post("/login")
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "?"
    wait = _locked(ip)
    if wait > 0:
        raise HTTPException(429, f"too many attempts — retry in {int(wait) + 1}s")
    auth = await repo.get_config("auth")
    ok = (auth.get("pw_hash")
          and secrets.compare_digest(body.username, auth.get("username", ""))
          and verify_password(body.password, auth["salt"], auth["pw_hash"]))
    if not ok:
        _record_failure(ip)
        log.warning("failed login for %r from %s", body.username, ip)
        raise HTTPException(401, "invalid username or password")
    token = await create_session(body.username)
    log.info("login ok: %s from %s", body.username, ip)
    return {"token": token, "username": body.username}


@router.post("/logout")
async def logout(request: Request, _user: str = Depends(require_session)):
    await destroy_session(_bearer(request))
    return {"ok": True}


@router.get("/me")
async def me(user: str = Depends(require_session)):
    return {"username": user}


@router.post("/change-password")
async def change_password(body: ChangePasswordBody, request: Request,
                          user: str = Depends(require_session)):
    auth = await repo.get_config("auth")
    if not verify_password(body.current_password, auth["salt"], auth["pw_hash"]):
        raise HTTPException(403, "current password is incorrect")
    salt = secrets.token_hex(16)
    await repo.set_config("auth", {
        "username": body.new_username or auth["username"], "salt": salt,
        "pw_hash": hash_password(body.new_password, salt)})
    await destroy_other_sessions(_bearer(request))  # keep this session alive
    log.info("credentials changed by %s (other sessions revoked)", user)
    return {"ok": True, "username": body.new_username or auth["username"]}
