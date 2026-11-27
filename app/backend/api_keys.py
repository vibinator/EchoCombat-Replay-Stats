"""Keys for the public player-stats API (/api/v1, api/public.py; user, 2026-11-27: "open up an API for player stats",
with API keys, profile stats only, an admin gets a key and its URL from the Console).

A key looks like ecs_<id>_<secret>. Only a SHA-256 of it is kept (app_settings row "api_key:<id>"), so a copy of the
database or the audit log cannot be used to call the API: the key is shown once, when it is made, and never again.
Revoking deletes the row. The admin console (admin.bat / the Console page) makes, lists and revokes keys; the server
reads them with a short memory (another process may have just made or revoked one)."""

import hashlib
import hmac
import json
import re
import secrets
import time

from sqlalchemy import select

from .guard import RateLimiter
from .models import AppSetting
from .db import utcnow

ROW = "api_key:"  # app_settings key prefix
PREFIX = "ecs_"
NAME_MAX = 60
MEMORY_S = 10.0  # a key made or revoked in admin.bat works / stops within this
TOUCH_EVERY_S = 600  # "last used" is written at most this often per key (a write per request would be wasteful)
PER_MIN, PER_HOUR = 30, 1000  # per key: 30 requests a minute (bursts up to 60), 1,000 an hour
KEY = re.compile(r"ecs_[0-9a-f]{8}_[A-Za-z0-9_-]{20,}")

_memory: dict = {"at": 0.0, "keys": {}, "sessions": None}
_touched: dict[str, float] = {}
minute = RateLimiter(PER_MIN, 2 * PER_MIN)
hourly = RateLimiter(PER_HOUR / 60, PER_HOUR)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def redact(text: str | None) -> str | None:
    """Keys blacked out, for the audit log (it keeps each command's output)."""
    return KEY.sub(lambda m: m.group(0)[:13] + "_(hidden)", text) if text else text


def _load(db) -> dict[str, dict]:
    rows = db.execute(select(AppSetting.key, AppSetting.value).where(AppSetting.key.like(ROW + "%"))).all()
    keys = {}
    for row_key, value in rows:
        try:
            keys[row_key.removeprefix(ROW)] = json.loads(value or "{}")
        except ValueError:
            continue
    return keys


def create(db, name: str, by: str) -> tuple[str, str]:
    """(id, key) of a new key. The key itself is not stored: show it now."""
    name = " ".join(name.split())[:NAME_MAX]
    if not name:
        raise ValueError("Give the key a name (who or what uses it)")
    key_id = secrets.token_hex(4)
    while db.get(AppSetting, ROW + key_id) is not None:
        key_id = secrets.token_hex(4)
    key = f"{PREFIX}{key_id}_{secrets.token_urlsafe(24)}"
    now = utcnow()
    entry = {"name": name, "hash": _hash(key), "created_at": now, "created_by": by, "last_used_at": None}
    db.add(AppSetting(key=ROW + key_id, value=json.dumps(entry), updated_at=now))
    db.commit()
    forget()
    return key_id, key


def listing(db) -> list[dict]:
    """Every key (no secrets), newest first."""
    keys = [{"id": k, **{f: v.get(f) for f in ("name", "created_at", "created_by", "last_used_at")}} for k, v in _load(db).items()]
    return sorted(keys, key=lambda k: k["created_at"] or "", reverse=True)


def revoke(db, key_id: str) -> dict | None:
    """Delete a key by its id (or the whole key); the removed key's details, None if there was none."""
    key_id = key_id.strip()
    if key_id.startswith(PREFIX):
        key_id = key_id.split("_")[1] if key_id.count("_") >= 2 else ""
    row = db.get(AppSetting, ROW + key_id) if key_id else None
    if row is None:
        return None
    entry = json.loads(row.value or "{}")
    db.delete(row)
    db.commit()
    forget()
    return {"id": key_id, "name": entry.get("name")}


def forget() -> None:
    _memory["at"] = 0.0


def find(sessions, presented: str) -> dict | None:
    """The key's details if `presented` is a live key, else None."""
    parts = presented.strip().split("_", 2)
    if len(parts) != 3 or parts[0] + "_" != PREFIX:
        return None
    now = time.monotonic()
    if now - _memory["at"] > MEMORY_S or _memory["sessions"] is not sessions:
        with sessions() as db:
            _memory.update(at=now, keys=_load(db), sessions=sessions)
    entry = _memory["keys"].get(parts[1])
    if entry is None or not hmac.compare_digest(entry.get("hash", ""), _hash(presented.strip())):
        return None
    return {"id": parts[1], **entry}


def touch(sessions, key_id: str) -> None:
    """Remember when the key was last used (at most every TOUCH_EVERY_S); never makes a request fail."""
    now = time.monotonic()
    if now - _touched.get(key_id, -TOUCH_EVERY_S) < TOUCH_EVERY_S:
        return
    _touched[key_id] = now
    try:
        with sessions() as db:
            row = db.get(AppSetting, ROW + key_id)
            if row is not None:
                entry = json.loads(row.value or "{}")
                entry["last_used_at"] = utcnow()
                row.value = json.dumps(entry)
                db.commit()
    except Exception:
        pass


def wait_for(key_id: str) -> float:
    """0 = allowed; otherwise seconds until this key may ask again."""
    return max(minute.take(key_id), hourly.take(key_id))
