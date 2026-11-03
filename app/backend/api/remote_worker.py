"""The remote PC's side of "Process replays on another PC" (remote.py): claim queued replays, send results, give back what
it cannot finish. Needs ECHOVR_REMOTE_WORKER_SECRET (Authorization: Bearer ...); without it these endpoints do not exist.
Not for browsers: no X-EchoVR header, no rate limit (the secret is the protection), never kept by a cache."""

import hmac
import logging
import os
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import remote, tracks, tracks3d
from ..errors import ApiError
from ..stats import STATS_VERSION
from ..worker import claim_queued, save_result
from parser import PARSER_VERSION

router = APIRouter(prefix="/api/worker", tags=["remote-worker"])
log = logging.getLogger("uvicorn.error")
MAX_CLAIM = 32
_write_lock = threading.Lock()  # one result saved at a time, like the local worker (SQLite has one writer)


def _require(request: Request) -> None:
    secret = request.app.state.settings.remote_worker_secret
    if not secret:
        raise ApiError(404, "remote_worker_disabled", "Remote processing is not set up (ECHOVR_REMOTE_WORKER_SECRET)")
    given = request.headers.get("authorization", "")
    if not hmac.compare_digest(given.encode(), f"Bearer {secret}".encode()):
        raise ApiError(401, "bad_worker_secret", "Wrong or missing secret")


def _same_versions(parser_version: str, stats_version: str) -> None:
    if (parser_version, stats_version) != (PARSER_VERSION, STATS_VERSION):
        raise ApiError(409, "version_mismatch",
                       f"This PC reads replays with parser {parser_version} / stats {stats_version}, the website with "
                       f"{PARSER_VERSION} / {STATS_VERSION}. Update the app on this PC to the same version (git pull).")


class Claim(BaseModel):
    count: int = Field(1, ge=1, le=MAX_CLAIM)
    parser_version: str
    stats_version: str


class Release(BaseModel):
    ids: list[int] = Field(max_length=500)


@router.post("/claim")
def claim(request: Request, body: Claim):
    """Up to `count` queued replays for the PC: {"enabled", "jobs": [{id, path, repair}]}. Nothing while remote
    processing is off (the NAS reads them itself); the PC waits and asks again."""
    _require(request)
    _same_versions(body.parser_version, body.stats_version)
    sessions = request.app.state.sessionmaker
    remote.mark_seen(sessions)
    with sessions() as db:
        on = remote.enabled(db)
    if not on:
        return {"enabled": False, "jobs": []}
    remote.requeue_abandoned(sessions)
    jobs = claim_queued(sessions, body.count)
    remote.add_claims([rid for rid, _, _ in jobs])
    return {"enabled": True, "jobs": [{"id": rid, "path": path, "repair": repair} for rid, path, repair in jobs]}


@router.post("/release")
def release(request: Request, body: Release):
    """The PC is stopping (or cannot see a file): these go back into the queue."""
    _require(request)
    return {"queued": remote.requeue(request.app.state.sessionmaker, [i for i in body.ids if remote.claimed(i)])}


def _write_tracks(path: Path, data: bytes, valid) -> bool:
    """Writes a track file the PC sent, if it reads back; one temp file per writer, like tracks3d.write."""
    if not data:
        return False
    try:
        valid(data)
    except Exception:  # noqa: BLE001 - anything wrong with it: the replay is saved without it
        log.warning("A track file from the remote PC for %s is damaged and was left out", path)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return True


@router.post("/result/{replay_id}")
async def result(request: Request, replay_id: int):
    """The PC's finished replay (remote.pack): saved as the NAS's own worker would, plus its two track files."""
    _require(request)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > remote.MAX_BODY_BYTES:
        raise ApiError(413, "too_big", "Result too big")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > remote.MAX_BODY_BYTES:
            raise ApiError(413, "too_big", "Result too big")
        chunks.append(chunk)
    body = b"".join(chunks)
    if not remote.claimed(replay_id):
        # taken back already (no answer for too long, or remote processing was turned off): the NAS has it queued again
        raise ApiError(409, "not_claimed", "This replay is not claimed by the remote PC (any more); its result is dropped")
    settings = request.app.state.settings
    sessions = request.app.state.sessionmaker

    def save() -> None:
        # everything slow (unpickling, checking and writing the track files) runs in parallel with other results;
        # only the database write is one at a time
        try:
            outcome, tracks_bytes, tracks3d_bytes = remote.unpack(body)
            if not (isinstance(outcome, tuple) and outcome and outcome[0] in ("ok", "failed")):
                raise ValueError("not a result")
        except Exception as e:  # noqa: BLE001 - cut off, wrong or not allowed content
            raise ApiError(400, "bad_result", f"The result could not be read: {e}") from e
        if outcome[0] == "ok":
            saved = _write_tracks(tracks.tracks_path(settings.processed_dir, replay_id), tracks_bytes, tracks.decode)
            _write_tracks(tracks3d.tracks3d_path(settings.processed_dir, replay_id), tracks3d_bytes, tracks3d.decode)
            outcome = (*outcome[:4], saved)  # has_tracks = the file really is here now
        with _write_lock:
            save_result(sessions, replay_id, outcome)

    await run_in_threadpool(save)  # database and disk work: not on the event loop
    remote.forget(replay_id)
    worker = getattr(request.app.state, "worker", None)
    if worker is not None:
        worker.notify()
    return {"saved": True}
