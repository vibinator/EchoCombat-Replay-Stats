"""Response cache for archive-wide aggregates (home page, leaderboard). Keyed on the data stamp, so a newly
processed replay invalidates it; while an import is running a result is reused for up to REUSE_WHILE_IMPORTING_S
instead of being recomputed after every replay. Lives on the app instance (one cache per database)."""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import date

from fastapi import Request
from sqlalchemy import func, select

from .models import Replay

MAX_ENTRIES = 256
REUSE_WHILE_IMPORTING_S = 60


_generation = 0  # bumped by the worker after every saved replay: processed_at has 1 s resolution


def bump_generation() -> None:
    global _generation
    _generation += 1


def data_stamp(db) -> tuple:
    """Changes whenever a replay finishes processing (count, newest processed_at, save generation)."""
    done = db.execute(select(func.count(), func.max(Replay.processed_at)).where(Replay.status == "done")).one()
    return (*done, _generation)


def cached(request: Request, name: str, params: tuple, compute: Callable[[], object]):
    """compute() once per (name, params, data stamp, today) — period filters such as "this week" move daily."""
    state = request.app.state
    if not hasattr(state, "response_cache"):
        state.response_cache, state.response_cache_lock = OrderedDict(), threading.Lock()
    store, lock = state.response_cache, state.response_cache_lock
    with state.sessionmaker() as db:
        stamp = data_stamp(db)
    key = (name, params, date.today().isoformat())
    with lock:
        hit = store.get(key)
    if hit:
        hit_stamp, at, value = hit
        worker = getattr(state, "worker", None)
        if hit_stamp == stamp or (worker is not None and worker.busy and time.monotonic() - at < REUSE_WHILE_IMPORTING_S):
            return value
    value = compute()
    with lock:
        store[key] = (stamp, time.monotonic(), value)
        store.move_to_end(key)
        while len(store) > MAX_ENTRIES:
            store.popitem(last=False)
    return value
