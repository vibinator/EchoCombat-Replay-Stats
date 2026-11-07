"""Remote processing (user, 2026-11-02): reading replays is slow on the NAS, so another PC can do it.

The PC (app/remote_worker.py) asks the website for queued replays (POST /api/worker/claim), reads them from the replay
share itself, and sends the finished result back (POST /api/worker/result/<id>). The website saves it exactly as if its
own worker had read the file. While "remote processing" is on (Console: "Process replays on another PC"), the NAS's own
worker takes no new replays, so the NAS stays free for visitors; a replay the PC claimed but never answered goes back
into the queue after CLAIM_TIMEOUT_S, or at once when the setting is turned off.

Safety: the endpoints exist only when ECHOVR_REMOTE_WORKER_SECRET is set, and need it. A result is an object, so it is read
with a whitelist (loads()): the result classes and plain data only, never other code. The PC must run the same parser
and stats versions as the NAS, otherwise its results would be wrong for this database."""

import io
import logging
import pickle
import struct
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from .db import utcnow
from .models import AppSetting, Replay

log = logging.getLogger(__name__)

KEY = "remote_processing"  # "1" = the PC only, "2" = this server and the PC both, anything else = this server only
MODE_VALUES = {"server": None, "remote": "1", "both": "2"}
SEEN_KEY = "remote_worker_seen"  # when the PC last asked for work (UTC ISO)
CLAIM_TIMEOUT_S = 30 * 60  # a claimed replay with no answer for this long is queued again
SEEN_WRITE_EVERY_S = 30
MAX_BODY_BYTES = 64 * 1024 * 1024
MAGIC = b"ER1"

# replay id -> time.monotonic() of the claim, for replays now being read on the PC. In memory only: a restart of the
# website queues every "processing" row again (worker.requeue_unfinished_and_outdated).
_claims: dict[int, float] = {}
_lock = threading.Lock()
_seen_written = 0.0


def mode(db: Session) -> str:
    """Who reads the replays: "server" (this server only), "remote" (the PC only) or "both" (this server and the PC,
    each taking replays from the same queue: a replay is handed to one of them only)."""
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == KEY))
    return "remote" if value == "1" else "both" if value == "2" else "server"


def set_mode(db: Session, new: str) -> None:
    db.merge(AppSetting(key=KEY, value=MODE_VALUES[new], updated_at=utcnow()))
    db.commit()


def enabled(db: Session) -> bool:
    """The PC is given replays (PC only, or both)."""
    return mode(db) != "server"


def server_works(db: Session) -> bool:
    """This server's own worker reads replays (this server only, or both)."""
    return mode(db) != "remote"


def set_enabled(db: Session, on: bool) -> None:
    set_mode(db, "remote" if on else "server")


def last_seen(db: Session) -> datetime | None:
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == SEEN_KEY))
    return datetime.fromisoformat(value) if value else None


def mark_seen(sessions: sessionmaker) -> None:
    """The PC asked for work: remembered (at most every SEEN_WRITE_EVERY_S) so the Console can say whether it is there."""
    global _seen_written
    now = time.monotonic()
    if now - _seen_written < SEEN_WRITE_EVERY_S:
        return
    _seen_written = now
    with sessions() as db:
        db.merge(AppSetting(key=SEEN_KEY, value=utcnow(), updated_at=utcnow()))
        db.commit()


def describe(db: Session) -> str:
    """One line for the Console status."""
    current = mode(db)
    if current == "server":
        return "on this server (remote processing is off)"
    seen = last_seen(db)
    who = "on another PC" if current == "remote" else "on this server and another PC, both at once"
    if seen is None:
        return f"{who} (remote processing is on, but no PC has asked for work yet)"
    ago = (datetime.now(timezone.utc) - seen).total_seconds()
    when = f"{ago / 60:.0f} min ago" if ago >= 90 else "just now"
    if ago < 300:
        state = ""
    elif current == "remote":
        state = "  ** not seen for a while: nothing is being processed **"
    else:
        state = "  ** the PC has not been seen for a while: only this server is processing **"
    return f"{who} (remote processing is on; the PC last asked for work {when}){state}"


# ---- claims -----------------------------------------------------------------------------------------------------------

def claimed(replay_id: int) -> bool:
    with _lock:
        return replay_id in _claims


def add_claims(replay_ids: list[int]) -> None:
    now = time.monotonic()
    with _lock:
        for rid in replay_ids:
            _claims[rid] = now


def forget(replay_id: int) -> None:
    with _lock:
        _claims.pop(replay_id, None)


def requeue(sessions: sessionmaker, replay_ids: list[int]) -> int:
    """Back into the queue (only rows still 'processing': an answer that arrived meanwhile is not undone)."""
    if not replay_ids:
        return 0
    with sessions() as db:
        done = db.execute(update(Replay).where(Replay.id.in_(replay_ids), Replay.status == "processing")
                          .values(status="queued")).rowcount
        db.commit()
    for rid in replay_ids:
        forget(rid)
    return done


def requeue_abandoned(sessions: sessionmaker, everything: bool = False, before: float | None = None) -> int:
    """Replays the PC claimed and never answered (or all of them: remote processing was turned off). `before` (a
    time.monotonic() value) limits "all of them" to claims made before the caller read the setting."""
    now = time.monotonic()
    with _lock:
        stale = [rid for rid, at in _claims.items()
                 if (everything and (before is None or at < before)) or now - at > CLAIM_TIMEOUT_S]
    if stale:
        log.warning("Queueing %d replay(s) claimed by the remote PC again (%s)", len(stale),
                    "remote processing is off" if everything else "no answer")
    return requeue(sessions, stale)


# ---- what travels -----------------------------------------------------------------------------------------------------

# Everything a result holds: the parsed header, the match statistics and plain values. Anything else is refused.
_ALLOWED = {
    ("parser.models", "ReplayMeta"),
    ("backend.stats.results", "MatchStats"), ("backend.stats.results", "PlayerStats"), ("backend.stats.results", "EventRecord"),
    ("datetime", "datetime"), ("datetime", "timedelta"), ("datetime", "timezone"), ("datetime", "date"),
    ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "complex"),
    ("collections", "OrderedDict"), ("collections", "defaultdict"), ("collections", "Counter"),
}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in _ALLOWED:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"{module}.{name} is not allowed in a result")


def loads(data: bytes):
    return _Unpickler(io.BytesIO(data)).load()


def dumps(result: tuple) -> bytes:
    return pickle.dumps(result, protocol=4)


def pack(result: tuple, tracks: bytes, tracks3d: bytes) -> bytes:
    """The PC's answer: MAGIC, then (length, bytes) for the result, tracks.bin and tracks3d.bin (empty = none)."""
    parts = [dumps(result), tracks, tracks3d]
    return MAGIC + b"".join(struct.pack("<I", len(p)) + p for p in parts)


def unpack(body: bytes) -> tuple[tuple, bytes, bytes]:
    if not body.startswith(MAGIC):
        raise ValueError("not a result")
    offset, parts = len(MAGIC), []
    for _ in range(3):
        (length,) = struct.unpack_from("<I", body, offset)
        offset += 4
        if offset + length > len(body):
            raise ValueError("cut off")
        parts.append(body[offset:offset + length])
        offset += length
    return loads(parts[0]), parts[1], parts[2]
