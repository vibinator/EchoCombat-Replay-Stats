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
request) or STALE (a fresher answer is being built: the page asks again shortly, no shared cache keeps it)."""

import dataclasses
import gzip
import hashlib
import logging
import threading
import time
import weakref
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date

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


def _lookup(request: Request, store: Store, name: str, params: tuple, build) -> tuple[Entry, str]:
    """(entry, "HIT" | "STALE" | "MISS"), see the module docstring."""
    state = request.app.state
    stamp = current_stamp(state.sessionmaker)
    key = (name, params, date.today().isoformat())  # period filters such as "this week" move daily
    refresh_s = state.settings.cache_refresh_s
    entry = store.get(key)
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


def cached_response(request: Request, name: str, params: tuple, compute: Callable[[], object]) -> Response:
    """The JSON answer compute() returns, cached like cached(), kept gzipped with an ETag."""
    store = _store(request.app.state, "response_cache", lambda: Store(MAX_RESPONSES, MAX_RESPONSE_BYTES))

    def build(stamp: tuple) -> Entry:
        started = time.monotonic()
        body = orjson.dumps(compute(), option=orjson.OPT_NON_STR_KEYS)
        gz = gzip.compress(body, GZIP_LEVEL, mtime=0)
        etag = f'W/"{hashlib.blake2b(body, digest_size=12).hexdigest()}"'
        return Entry(stamp, started, gz=gz, etag=etag, size=len(gz) + 256)

    entry, status = _lookup(request, store, name, params, build)
    return reply(request, entry, status)


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
