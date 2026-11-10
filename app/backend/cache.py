"""Caches for answers built from the archive: home page, leaderboard, profiles, heatmaps, match views (D53). Keyed on
the data stamp, so a newly processed replay makes an answer out of date. Lives on the app instance (one cache per
database).

Freshness (user, 2026-11-01): stale-while-revalidate. An out-of-date answer is still sent at once; once it is
`cache_refresh_s` old (ECHOVR_CACHE_REFRESH_S, 300 s on the website) it is rebuilt in the background, at most two at a
time, so pages are at most about that far behind the archive and a visitor never waits for the rebuild of a page that
was built before. Only an answer nobody asked for yet waits for its build, and identical requests arriving meanwhile
wait for that one build. cache_refresh_s = 0 (the tests): an out-of-date answer is rebuilt before answering.

`cached_response` keeps the answer gzipped with an ETag: a repeat costs no JSON encoding or compression, and a browser
(or Cloudflare) that already has it gets 304 Not Modified. The X-EchoVR-Cache header says HIT, MISS (built for this
request) or STALE (a fresher answer is being built: the page asks again shortly, no shared cache keeps it).

Player heatmaps (user, 2026-11-10) are the costliest answers (seconds each, 18 s for a long history) and are cached
more tightly, three ways:
- their own stamp (`stamp=`): the player's matches behind the answer, not the whole archive, so a heatmap is only
  worked out again when that player has a new (or re-read) match, not whenever anybody's replay comes in;
- no day in the key when the period is "all time" (`daily=False`): nothing in it moves at midnight;
- kept on disk too (`persist=True`, class Disk): a restart of the server does not lose them. The idle pass
  (heights_warm.py) writes the long ones of the most active players there ahead of time (`prebuild`)."""

import dataclasses
import gzip
import hashlib
import json
import logging
import os
import struct
import threading
import time
import weakref
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import orjson
from fastapi import Request
from fastapi.responses import Response
from sqlalchemy import func, select

from .errors import ApiError
from .models import Replay

log = logging.getLogger(__name__)

STAMP_TTL_S = 2.0  # data_stamp is re-read at most this often: the admin console (another process) shows within it
MAX_VALUES = 256
MAX_RESPONSES = 4096
MAX_RESPONSE_BYTES = 64 * 1024 * 1024  # gzipped answers kept in RAM (a player heatmap is 70-200 KB)
GZIP_LEVEL = 6  # compressed once per build, sent many times
STATUS_HEADER = "X-EchoVR-Cache"

_generation = 0  # bumped by the worker after every saved replay: processed_at has 1 s resolution


def bump_generation() -> None:
    global _generation
    _generation += 1


def data_stamp(db) -> tuple:
    """Changes whenever a replay finishes processing (count, newest processed_at, save generation)."""
    done = db.execute(select(func.count(), func.max(Replay.processed_at)).where(Replay.status == "done")).one()
    return (*done, _generation)


_stamps: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()  # sessionmaker -> (generation, read at, stamp)


def current_stamp(sessions) -> tuple:
    """data_stamp, remembered for STAMP_TTL_S: the query counts every processed replay (3 ms on the full archive) and
    every cached answer needs it. A replay saved by this process shows at once (the generation changes)."""
    now = time.monotonic()
    memo = _stamps.get(sessions)
    if memo is not None and memo[0] == _generation and now - memo[1] < STAMP_TTL_S:
        return memo[2]
    generation = _generation
    with sessions() as db:
        stamp = data_stamp(db)
    _stamps[sessions] = (generation, now, stamp)
    return stamp


@dataclasses.dataclass
class Entry:
    stamp: tuple  # data stamp the answer was built from
    built_at: float  # time.monotonic() when its build started
    value: object = None  # cached(): the Python value
    gz: bytes = b""  # cached_response(): the JSON, gzipped
    etag: str = ""
    size: int = 0  # bytes counted against the store's limit


class Store:
    """Least recently used entries, bounded by count and bytes, with the builds running for them."""

    def __init__(self, max_entries: int, max_bytes: int | None = None):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.entries: OrderedDict = OrderedDict()
        self.bytes = 0
        self.lock = threading.Lock()
        self.building: dict = {}  # key -> lock held while a visitor waits for its build
        self.refreshing: set = set()  # keys being rebuilt in the background

    def get(self, key) -> Entry | None:
        with self.lock:
            entry = self.entries.get(key)
            if entry is not None:
                self.entries.move_to_end(key)
            return entry

    def put(self, key, entry: Entry) -> None:
        with self.lock:
            if (old := self.entries.pop(key, None)) is not None:
                self.bytes -= old.size
            self.entries[key] = entry
            self.bytes += entry.size
            while self.entries and (len(self.entries) > self.max_entries
                                    or (self.max_bytes is not None and self.bytes > self.max_bytes)):
                self.bytes -= self.entries.popitem(last=False)[1].size

    def drop(self, key) -> None:
        with self.lock:
            if (old := self.entries.pop(key, None)) is not None:
                self.bytes -= old.size


# Answers on disk: data/cache/answers/<hash of the key>.bin = u32 header length, header JSON {stamp, etag, built
# (clock time)}, the gzipped answer. Once the folder is over its limit (Settings.answer_cache_mb) the files not used
# for the longest go first: a file's time is set to now whenever it is read for a request or found current by the
# idle pass (when it was built is in its header), so what people open and what is kept ready stays.
# DISK_FORMAT: another number when the shape of an answer kept here changes, so files from before are not used.
DISK_FORMAT = 1
DISK_PRUNE_EVERY = 100  # saves between two looks at the folder's size
DISK_MAX_AGE_S = 60 * 86400


class Disk:
    def __init__(self, folder: Path, max_bytes: int):
        self.folder, self.max_bytes = folder, max_bytes
        self.saves = 0
        self.lock = threading.Lock()

    def path(self, key) -> Path:
        return self.folder / (hashlib.blake2b(repr((DISK_FORMAT, key)).encode(), digest_size=16).hexdigest() + ".bin")

    def _read(self, key, body: bool):
        try:
            with open(self.path(key), "rb") as f:
                (length,) = struct.unpack("<I", f.read(4))
                header = json.loads(f.read(length))
                return header, (f.read() if body else b"")
        except FileNotFoundError:
            return None
        except (OSError, ValueError, struct.error, KeyError, TypeError):
            log.warning("The saved answer for %s cannot be read; it is built again", key[0])
            return None

    def used(self, key) -> None:
        """Mark the saved answer as used now (prune keeps the most recently used)."""
        try:
            os.utime(self.path(key))
        except OSError:
            pass

    def stamp(self, key) -> tuple | None:
        """The stamp of the saved answer (None = none saved)."""
        found = self._read(key, body=False)
        return None if found is None else _plain(found[0]["stamp"])

    def load(self, key) -> Entry | None:
        found = self._read(key, body=True)
        if found is None or not found[1]:
            return None
        header, gz = found
        self.used(key)
        age = max(0.0, time.time() - float(header["built"]))
        return Entry(_plain(header["stamp"]), time.monotonic() - age, gz=gz, etag=header["etag"], size=len(gz) + 256)

    def save(self, key, entry: Entry) -> None:
        """Never an error: an answer that could not be saved is simply built again after a restart."""
        header = json.dumps({"stamp": entry.stamp, "etag": entry.etag, "name": key[0],
                             "built": time.time() - (time.monotonic() - entry.built_at)}).encode()
        path = self.path(key)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(struct.pack("<I", len(header)) + header + entry.gz)
            os.replace(tmp, path)
        except OSError as e:
            log.warning("The answer for %s was not saved: %s", key[0], e)
            return
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        with self.lock:
            self.saves += 1
            due = self.saves % DISK_PRUNE_EVERY == 1
        if due:
            self.prune()

    def prune(self) -> None:
        """Files not used for DISK_MAX_AGE_S go, then the longest unused until the folder is at 90 % of its limit."""
        try:
            files = [(e.stat().st_mtime, e.stat().st_size, e.path) for e in os.scandir(self.folder) if e.is_file()]
        except OSError:
            return
        files.sort()
        total = sum(size for _, size, _ in files)
        cutoff = time.time() - DISK_MAX_AGE_S
        target = self.max_bytes if total <= self.max_bytes else self.max_bytes * 0.9
        for mtime, size, path in files:  # oldest first
            if mtime >= cutoff and total <= target:
                break
            try:
                os.unlink(path)
                total -= size
            except OSError:
                pass


def _plain(stamp) -> tuple:
    """A stamp as it comes back from JSON (lists), for comparing: tuples all the way down."""
    return tuple(_plain(v) if isinstance(v, (list, tuple)) else v for v in stamp)


def _disk(state) -> Disk | None:
    """The answers-on-disk store of this app (None = switched off: Settings.answer_cache_mb = 0)."""
    disk = getattr(state, "answer_disk", False)
    if disk is False:
        mb = getattr(state.settings, "answer_cache_mb", 0)
        disk = Disk(state.settings.data_dir / "cache" / "answers", mb * 1024 * 1024) if mb > 0 else None
        state.answer_disk = disk
    return disk


_stores_lock = threading.Lock()


def _store(state, name: str, make: Callable[[], Store]) -> Store:
    store = getattr(state, name, None)
    if store is None:
        with _stores_lock:
            store = getattr(state, name, None)
            if store is None:
                store = make()
                setattr(state, name, store)
    return store


# Background rebuilds: two at a time, so a burst of out-of-date pages cannot take over the server.
_refresher = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache-refresh")
# Builds running in this thread (innermost last): an answer built from another cached answer (the leaderboard page
# from the all-stats aggregate) is only as current as that one, so it takes over its stamp and age.
_frames = threading.local()


def _run(build: Callable[[tuple], Entry], stamp: tuple) -> Entry:
    frames = getattr(_frames, "stack", None)
    if frames is None:
        frames = _frames.stack = []
    frame = {"stamp": stamp, "built_at": time.monotonic()}
    frames.append(frame)
    try:
        entry = build(stamp)
    finally:
        frames.pop()
    entry.stamp, entry.built_at = frame["stamp"], frame["built_at"]
    return entry


def _used(entry: Entry, stamp: tuple) -> Entry:
    """Tell the build this lookup happened in (if any) how old the entry it used is."""
    frames = getattr(_frames, "stack", None)
    if frames:
        outer = frames[-1]
        outer["built_at"] = min(outer["built_at"], entry.built_at)
        if entry.stamp != stamp:
            outer["stamp"] = entry.stamp
    return entry


def _build_now(store: Store, key, build, stamp: tuple, seen: Entry | None) -> Entry:
    """Build while the visitor waits. Identical requests arriving meanwhile wait for this one build."""
    with store.lock:
        lock = store.building.setdefault(key, threading.Lock())
    with lock:
        entry = store.get(key)
        if entry is not None and (entry is not seen or entry.stamp == stamp):
            return entry  # built by the request this one waited for
        try:
            entry = _run(build, stamp)
            store.put(key, entry)
            return entry
        finally:
            with store.lock:
                if store.building.get(key) is lock:
                    del store.building[key]


def _refresh(store: Store, key, build, stamp: tuple) -> None:
    """Rebuild in the background; the old answer is sent meanwhile."""
    with store.lock:
        if key in store.refreshing:
            return
        store.refreshing.add(key)

    def run():
        try:
            store.put(key, _run(build, stamp))
        except ApiError:
            store.drop(key)  # e.g. the player is gone: the next request builds it and reports why
        except Exception:
            log.exception("Rebuilding the cached %s failed; the previous answer stays", key[0])
            if (old := store.get(key)) is not None:  # try again after another interval, not on every request
                store.put(key, dataclasses.replace(old, built_at=time.monotonic()))
        finally:
            with store.lock:
                store.refreshing.discard(key)

    _refresher.submit(run)


def _key(name: str, params: tuple, daily: bool) -> tuple:
    return (name, params, date.today().isoformat() if daily else None)  # period filters such as "this week" move daily


def _saving(disk: Disk, key, build):
    def build_and_save(stamp: tuple) -> Entry:
        entry = build(stamp)
        entry.stamp = stamp
        disk.save(key, entry)
        return entry

    return build_and_save


def _lookup(request: Request, store: Store, name: str, params: tuple, build, stamp=None, daily: bool = True,
            disk: Disk | None = None) -> tuple[Entry, str]:
    """(entry, "HIT" | "STALE" | "MISS"), see the module docstring. `stamp`: a function giving the answer's own
    stamp instead of the archive's; `daily=False`: the same answer on every day; `disk`: kept there too."""
    state = request.app.state
    stamp = current_stamp(state.sessionmaker) if stamp is None else _plain(stamp())
    key = _key(name, params, daily)
    refresh_s = state.settings.cache_refresh_s
    entry = store.get(key)
    if disk is not None:
        if entry is None and (entry := disk.load(key)) is not None:
            store.put(key, entry)  # from before a restart, or written ahead by the idle pass
        build = _saving(disk, key, build)
    if entry is not None:
        if entry.stamp == stamp:
            return _used(entry, stamp), "HIT"
        if refresh_s > 0:
            if time.monotonic() - entry.built_at < refresh_s:
                return _used(entry, stamp), "HIT"
            _refresh(store, key, build, stamp)
            return _used(entry, stamp), "STALE"
    return _used(_build_now(store, key, build, stamp, entry), stamp), "MISS"


def cached(request: Request, name: str, params: tuple, compute: Callable[[], object]):
    """compute() once per (name, params, data stamp, day); out of date: see the module docstring."""
    store = _store(request.app.state, "value_cache", lambda: Store(MAX_VALUES))
    return _lookup(request, store, name, params, lambda stamp: Entry(stamp, time.monotonic(), value=compute()))[0].value


def _response_entry(compute: Callable[[], object], stamp: tuple) -> Entry:
    started = time.monotonic()
    body = orjson.dumps(compute(), option=orjson.OPT_NON_STR_KEYS)
    gz = gzip.compress(body, GZIP_LEVEL, mtime=0)
    etag = f'W/"{hashlib.blake2b(body, digest_size=12).hexdigest()}"'
    return Entry(stamp, started, gz=gz, etag=etag, size=len(gz) + 256)


def cached_response(request: Request, name: str, params: tuple, compute: Callable[[], object], stamp=None,
                    daily: bool = True, persist: bool = False) -> Response:
    """The JSON answer compute() returns, cached like cached(), kept gzipped with an ETag. `stamp`, `daily`,
    `persist`: see the module docstring (player heatmaps)."""
    store = _store(request.app.state, "response_cache", lambda: Store(MAX_RESPONSES, MAX_RESPONSE_BYTES))
    entry, status = _lookup(request, store, name, params, lambda s: _response_entry(compute, s), stamp, daily,
                            _disk(request.app.state) if persist else None)
    return reply(request, entry, status)


def prebuild(app, name: str, params: tuple, compute: Callable[[], object], stamp, daily: bool = True) -> bool:
    """Builds an answer ahead of time and keeps it on disk only (memory stays for what people are looking at); the
    request that asks for it finds it there. False = the saved one is still current, or nothing is kept on disk."""
    disk = _disk(app.state)
    if disk is None:
        return False
    key, now = _key(name, params, daily), _plain(stamp())
    if disk.stamp(key) == now:
        disk.used(key)  # kept ready on purpose: not the first to go when the folder is full
        return False
    disk.save(key, _response_entry(compute, now))
    return True


def etag_matches(header: str | None, etag: str) -> bool:
    """If-None-Match, weak comparison (RFC 9110 13.1.2): Cloudflare may hand on W/ versions of our tags."""
    if not header or not etag:
        return False
    tag = etag.removeprefix("W/")
    return any(t.strip() == "*" or t.strip().removeprefix("W/") == tag for t in header.split(","))


def reply(request: Request, entry: Entry, status: str) -> Response:
    headers = {"ETag": entry.etag, "Vary": "Accept-Encoding", STATUS_HEADER: status}
    if etag_matches(request.headers.get("if-none-match"), entry.etag):
        return Response(status_code=304, headers=headers)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(entry.gz, media_type="application/json", headers=headers | {"Content-Encoding": "gzip"})
    return Response(gzip.decompress(entry.gz), media_type="application/json", headers=headers)
