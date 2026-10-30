"""Finds replays in the read-only share (D25) and queues new or changed files. Never writes to the share."""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .db import utcnow
from .models import Replay

log = logging.getLogger(__name__)

EXTENSION = ".echoreplay"


@dataclass
class ScanState:
    reachable: bool | None = None  # None = not scanned yet
    scanning: bool = False
    last_scan_at: str | None = None
    last_scan_s: float | None = None
    files: int = 0
    settling: int = 0  # modified too recently; picked up by a later scan
    added: int = 0
    changed: int = 0
    error: str | None = None


def _walk(root: Path) -> Iterator[os.DirEntry]:
    # os.scandir: on Windows DirEntry.stat() comes from the directory listing (no extra network call).
    stack = [root]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.name.lower().endswith(EXTENSION):
                    yield entry


def scan_once(sessions: sessionmaker, settings: Settings, state: ScanState) -> int:
    """Sync the replays table with the share. Returns the number of replays queued."""
    root = settings.source_dir
    started = time.monotonic()
    state.scanning = True
    try:
        if not root.is_dir():
            state.reachable, state.error = False, f"Replay folder not reachable: {root}"
            return 0
        now = time.time()
        found: dict[str, tuple[int, float]] = {}
        settling = 0
        for entry in _walk(root):
            st = entry.stat()
            if settings.settle_s and now - st.st_mtime < settings.settle_s:
                settling += 1
                continue
            found[Path(entry.path).relative_to(root).as_posix()] = (st.st_size, st.st_mtime)

        added = changed = 0
        with sessions() as db:
            known = {r.source_path: r for r in db.scalars(select(Replay))}
            for rel, (size, mtime) in found.items():
                replay = known.get(rel)
                if replay is None:
                    db.add(Replay(source_path=rel, size_bytes=size, source_mtime=mtime,
                                  discovered_at=utcnow(), status="queued"))
                    added += 1
                elif (replay.size_bytes, replay.source_mtime) != (size, mtime) and replay.status != "processing":
                    replay.size_bytes, replay.source_mtime, replay.status = size, mtime, "queued"
                    changed += 1
            db.commit()

        state.reachable, state.error = True, None
        state.files, state.settling, state.added, state.changed = len(found), settling, added, changed
        return added + changed
    except OSError as e:
        log.warning("Scan of %s failed: %s", root, e)
        state.reachable, state.error = False, f"Scan failed: {e}"
        return 0
    finally:
        state.scanning = False
        state.last_scan_at = utcnow()
        state.last_scan_s = round(time.monotonic() - started, 1)


class Scanner:
    def __init__(self, sessions: sessionmaker, settings: Settings, on_queued: Callable[[], None]):
        self.sessions, self.settings, self.on_queued = sessions, settings, on_queued
        self.state = ScanState()
        self._stop = threading.Event()
        self._now = threading.Event()
        self._thread = threading.Thread(target=self._run, name="replay-scanner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def scan_soon(self) -> None:
        self._now.set()

    def stop(self) -> None:
        self._stop.set()
        self._now.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            if scan_once(self.sessions, self.settings, self.state):
                self.on_queued()
            self._now.wait(self.settings.scan_interval_s)
            self._now.clear()
