"""Finds replays in the read-only share (D25) and queues new or changed files. Never writes to the share.

A full scan lists every file (~8 s for 29k files over SMB), so it runs every `scan_interval_s`. In between, the
scanner only stats the folders (a handful of calls) every `quick_check_s`: adding, removing or renaming a file changes
its folder's modified time, which starts a full scan straight away. Files still settling get a scan of their own as
soon as they are old enough, instead of waiting for the next interval."""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
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


@dataclass
class Snapshot:
    """What the last full scan saw, to decide when the next one is needed (scanner thread only)."""
    dirs: dict[str, int] = field(default_factory=dict)  # folder -> st_mtime_ns
    settle_due: float | None = None  # wall time the first settling file is old enough


def _walk(root: Path, dirs: dict[str, int]) -> Iterator[os.DirEntry]:
    # os.scandir: on Windows DirEntry.stat() comes from the directory listing (no extra network call).
    # A folder that vanishes or cannot be read while walking (a temporary folder, a permission problem) is skipped:
    # it must not stop the scan, or no new replay would be found at all. Only the root failing is an error.
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            dirs[str(folder)] = os.stat(folder).st_mtime_ns  # before listing: a file added meanwhile still shows as a change
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.name.lower().endswith(EXTENSION):
                        yield entry
        except (FileNotFoundError, PermissionError, NotADirectoryError) as e:
            if folder == root:
                raise
            log.warning("Skipped %s while scanning: %s", folder, e)


def _written_at(st: os.stat_result) -> float:
    """Latest write to the file. A copy keeps the original modified time, so also count when it was created
    (Windows: st_birthtime) / last changed (Linux: st_ctime): a replay still being copied in is not read half-written."""
    return max(st.st_mtime, getattr(st, "st_birthtime", st.st_ctime))


def dirs_changed(dirs: dict[str, int]) -> bool:
    for folder, mtime in dirs.items():
        try:
            if os.stat(folder).st_mtime_ns != mtime:
                return True
        except OSError:
            return True  # folder gone or share offline: a full scan sorts it out
    return False


def scan_once(sessions: sessionmaker, settings: Settings, state: ScanState, snapshot: Snapshot | None = None) -> int:
    """Sync the replays table with the share. Returns the number of replays queued."""
    root = settings.source_dir
    snapshot = snapshot if snapshot is not None else Snapshot()
    started = time.monotonic()
    state.scanning = True
    try:
        if not root.is_dir():
            state.reachable, state.error = False, f"Replay folder not reachable: {root}"
            return 0
        now = time.time()
        found: dict[str, tuple[int, float]] = {}
        settling = 0
        dirs: dict[str, int] = {}
        settle_due = None
        for entry in _walk(root, dirs):
            try:
                st = entry.stat()
            except FileNotFoundError:  # removed since it was listed
                continue
            ready_at = _written_at(st) + settings.settle_s
            if settings.settle_s and now < ready_at:
                settling += 1
                settle_due = ready_at if settle_due is None else min(settle_due, ready_at)
                continue
            found[Path(entry.path).relative_to(root).as_posix()] = (st.st_size, st.st_mtime)

        added = changed = 0
        with sessions() as db:
            # columns only: loading every full row on each scan would cost more than the folder listing
            known = {path: (rid, size, mtime, status) for rid, path, size, mtime, status in db.execute(
                select(Replay.id, Replay.source_path, Replay.size_bytes, Replay.source_mtime, Replay.status))}
            for rel, (size, mtime) in found.items():
                row = known.get(rel)
                if row is None:
                    db.add(Replay(source_path=rel, size_bytes=size, source_mtime=mtime,
                                  discovered_at=utcnow(), status="queued"))
                    added += 1
                elif (row[1], row[2]) != (size, mtime) and row[3] != "processing":
                    replay = db.get(Replay, row[0])
                    replay.size_bytes, replay.source_mtime, replay.status = size, mtime, "queued"
                    changed += 1
            db.commit()

        snapshot.dirs, snapshot.settle_due = dirs, settle_due
        state.reachable, state.error = True, None
        state.files, state.settling, state.added, state.changed = len(found), settling, added, changed
        return added + changed
    except OSError as e:
        snapshot.dirs, snapshot.settle_due = {}, None  # retry on the normal interval
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
            snapshot = Snapshot()
            if scan_once(self.sessions, self.settings, self.state, snapshot):
                self.on_queued()
            self._wait_for_change(snapshot)

    def _wait_for_change(self, snapshot: Snapshot) -> None:
        """Return when a full scan is due: interval over, a folder changed, a settling file is ready, or scan_soon()."""
        full_at = time.monotonic() + self.settings.scan_interval_s
        quick = self.settings.quick_check_s or float("inf")
        while not self._stop.is_set():
            timeout = min(quick, full_at - time.monotonic())
            if snapshot.settle_due is not None:
                timeout = min(timeout, snapshot.settle_due + 1 - time.time())
            if self._now.wait(max(timeout, 0)):
                self._now.clear()
                return
            if time.monotonic() >= full_at:
                return
            if snapshot.settle_due is not None and time.time() >= snapshot.settle_due + 1:
                return
            if dirs_changed(snapshot.dirs):
                return
