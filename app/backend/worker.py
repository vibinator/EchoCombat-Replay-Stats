"""Processes queued replays, newest file first (D25). Parsing + stats run in a process pool;
results are saved by this one thread, because SQLite allows a single writer."""

import json
import logging
import signal
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import sessionmaker

from parser import PARSER_VERSION, ReplayError, open_replay

from .cache import bump_generation
from .config import Settings
from .db import utcnow
from .models import Match, MatchPlayerLoadout, PriorityReplay, RepairRequest, Replay
from . import duplicates, tracks
from .persist import delete_match, save_match
from .stats import STATS_VERSION, compute
from .tracks import TrackRecorder, tracks_path

log = logging.getLogger(__name__)

MAX_CRASHES = 2  # a file in flight during this many pool crashes is marked failed ("crashed")


def _ignore_ctrl_c() -> None:
    # Pool processes share the console: let only the main process handle Ctrl+C, so a stop
    # never kills workers mid-file (their replays are re-queued on the next start instead).
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def analyse(path: str, tracks_file: str | None = None, repair: bool = False) -> tuple:
    """Runs in a pool process. Returns ("ok", meta, stats, warnings, tracks_saved) or ("failed", code, message).
    Also writes the 2 Hz position tracks (for heatmaps / timeline) to `tracks_file`."""
    try:
        parsed = open_replay(Path(path), repair=repair)
        recorder = TrackRecorder(parsed.meta.started_at) if tracks_file else None
        stats = compute(parsed.meta, parsed.frames(), recorder)
        warnings = list(parsed.warnings)
        saved = False
        if recorder is not None:
            try:
                tracks.write(Path(tracks_file), recorder.result())
                saved = True
            except OSError as e:
                warnings.append(f"Position tracks not saved: {e}")
        return "ok", parsed.meta, stats, warnings, saved
    except ReplayError as e:
        return "failed", e.code, str(e)
    except OSError as e:
        return "failed", "unreadable", f"Could not read file: {e}"
    except Exception as e:
        return "failed", "internal", f"Internal error: {e}\n{traceback.format_exc(limit=5)}"


def save_result(sessions: sessionmaker, replay_id: int, result: tuple) -> None:
    try:
        _save_result(sessions, replay_id, result)
    finally:
        bump_generation()  # invalidates cached responses (cache.py)


def _save_result(sessions: sessionmaker, replay_id: int, result: tuple) -> None:
    with sessions() as db:
        replay = db.get(Replay, replay_id)
        if replay is None:
            return
        try:
            had_match = db.scalar(select(func.count()).select_from(Match).where(Match.replay_id == replay_id))
            if result[0] == "failed" and result[1] == "unreadable" and had_match:
                # Share offline / file locked during a reprocess: keep the previous results (no data loss).
                replay.status = "done"
                replay.warnings = json.dumps([f"Re-read failed, previous results kept: {result[2]}"])
                replay.processed_at = utcnow()
                db.commit()
                return
            delete_match(db, replay_id)
            if result[0] == "ok":
                _, meta, stats, warnings, has_tracks = result
                save_match(db, replay_id, meta, stats, has_tracks)
                replay.status, replay.error_code, replay.error_message = "done", None, None
                replay.container = meta.container
                replay.warnings = json.dumps(warnings) if warnings else None
                replay.stats_version = STATS_VERSION
            else:
                _, code, message = result
                if code == "internal":
                    log.error("Replay %s (%s) failed: %s", replay_id, replay.source_path, message)
                replay.status, replay.error_code, replay.error_message = "failed", code, message
                replay.warnings = replay.stats_version = None
            replay.parser_version = PARSER_VERSION
            replay.processed_at = utcnow()
            db.commit()
        except Exception as e:
            db.rollback()
            log.exception("Saving replay %s failed", replay_id)
            delete_match(db, replay_id)
            replay = db.get(Replay, replay_id)
            replay.status, replay.error_code, replay.error_message = "failed", "internal", f"Save failed: {e}"
            replay.parser_version, replay.stats_version, replay.processed_at = PARSER_VERSION, None, utcnow()
            db.commit()


def _with_hex_gear_codes():
    """Replays saved before the parser normalised older-API hex gear symbols (about 500 in the 2026 archive):
    re-read once, after which their codes are plain and they no longer match."""
    hexed = or_(*(column.like("0x%") for column in
                  (MatchPlayerLoadout.weapon, MatchPlayerLoadout.tacmod, MatchPlayerLoadout.ordnance)))
    return (select(Match.replay_id).join(MatchPlayerLoadout, MatchPlayerLoadout.match_id == Match.id)
            .where(hexed).distinct())


def requeue_unfinished_and_outdated(sessions: sessionmaker) -> int:
    """Startup: interrupted rows, and rows processed by an older parser / stats version (D19)."""
    with sessions() as db:
        result = db.execute(
            update(Replay)
            .where(
                or_(
                    Replay.status == "processing",
                    Replay.parser_version.is_(None) & (Replay.status != "queued"),
                    Replay.parser_version != PARSER_VERSION,
                    (Replay.status == "done")
                    & or_(Replay.stats_version.is_(None), Replay.stats_version != STATS_VERSION),
                    Replay.id.in_(_with_hex_gear_codes()),
                )
            )
            .values(status="queued")
        )
        db.commit()
        return result.rowcount


class Worker:
    def __init__(self, sessions: sessionmaker, settings: Settings):
        self.sessions, self.settings = sessions, settings
        self.slots = max(1, settings.workers)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._in_flight: dict[Future, int] = {}
        self._started: dict[int, tuple[str, float]] = {}  # replay_id -> (source_path, monotonic start)
        self._crashes: Counter[int] = Counter()
        self._pool: Executor | None = None
        self._thread = threading.Thread(target=self._run, name="replay-worker", daemon=True)

    def start(self) -> None:
        requeue_unfinished_and_outdated(self.sessions)
        duplicates.refresh_all(self.sessions)
        self._pool = self._new_pool()
        self._thread.start()

    def _new_pool(self) -> Executor:
        if self.settings.workers > 0:
            return ProcessPoolExecutor(self.settings.workers, initializer=_ignore_ctrl_c)
        return ThreadPoolExecutor(1)  # tests: same process, deterministic

    def notify(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join()
        self._pool.shutdown(wait=True, cancel_futures=True)

    @property
    def busy(self) -> int:
        return len(self._in_flight)

    def current(self) -> list[dict]:
        """Files being processed right now."""
        now = time.monotonic()
        running = [(rid, *self._started[rid]) for rid in list(self._in_flight.values()) if rid in self._started]
        return [{"replay_id": rid, "source_path": path, "seconds": round(now - t0, 1)}
                for rid, path, t0 in sorted(running, key=lambda r: r[2])]

    def wait_idle(self, timeout: float = 60.0) -> None:
        """Tests: block until nothing is queued or processing."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.sessions() as db:
                pending = db.scalar(
                    select(func.count()).select_from(Replay).where(Replay.status.in_(("queued", "processing")))
                )
            if not pending and not self._in_flight:
                return
            self.notify()
            time.sleep(0.02)
        raise TimeoutError("worker did not become idle")

    def _claim(self, count: int) -> list[tuple[int, str]]:
        with self.sessions() as db:
            # admin console merges / repairs first (priority_replays), then the backlog, newest file first. Priority
            # replays go newest match first (user, 2026-10-31: a merged player's latest games are right first);
            # ones without a match yet (e.g. repairs) by newest file.
            replays = db.scalars(
                select(Replay).join(PriorityReplay, PriorityReplay.replay_id == Replay.id)
                .outerjoin(Match, Match.replay_id == Replay.id)
                .where(Replay.status == "queued")
                .order_by(Match.started_at.desc().nulls_last(), Replay.source_mtime.desc()).limit(count)
            ).all()
            db.execute(delete(PriorityReplay).where(or_(
                PriorityReplay.replay_id.in_([r.id for r in replays]),
                PriorityReplay.replay_id.not_in(select(Replay.id).where(Replay.status.in_(("queued", "processing")))),
            )))
            if len(replays) < count:
                replays += db.scalars(
                    select(Replay).where(Replay.status == "queued", Replay.id.not_in([r.id for r in replays]))
                    .order_by(Replay.source_mtime.desc()).limit(count - len(replays))
                ).all()
            for r in replays:
                r.status = "processing"
            db.commit()
            for r in replays:
                self._started[r.id] = (r.source_path, time.monotonic())
            repair = set(db.scalars(select(RepairRequest.source_path)
                                    .where(RepairRequest.source_path.in_([r.source_path for r in replays]))))
            return [(r.id, str(self.settings.source_dir / r.source_path), r.source_path in repair) for r in replays]

    def _tracks_file(self, replay_id: int) -> str:
        return str(tracks_path(self.settings.processed_dir, replay_id))

    def _requeue(self, replay_ids: list[int]) -> None:
        with self.sessions() as db:
            db.execute(update(Replay).where(Replay.id.in_(replay_ids)).values(status="queued"))
            db.commit()

    def _recover_from_crash(self) -> None:
        """The pool died: re-queue everything in flight, except files that keep crashing it."""
        crashed = list(self._in_flight.values())
        self._in_flight.clear()
        self._started.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
        if self._stop.is_set():
            return  # stopping: rows stay "processing" and are re-queued on the next start
        log.warning("Worker pool crashed with %d replay(s) in flight; restarting it", len(crashed))
        retry = []
        for replay_id in crashed:
            self._crashes[replay_id] += 1
            if self._crashes[replay_id] >= MAX_CRASHES:
                save_result(self.sessions, replay_id,
                            ("failed", "crashed", "Processing crashed repeatedly (file too large or damaged?)"))
            else:
                retry.append(replay_id)
        self._requeue(retry)
        self._pool = self._new_pool()

    def _run(self) -> None:
        # Rows still "processing" when stopped are re-queued on the next start.
        try:
            while not self._stop.is_set():
                free = self.slots - len(self._in_flight)
                if free > 0:
                    claimed = self._claim(free)
                    try:
                        for replay_id, path, repair in claimed:
                            future = self._pool.submit(analyse, path, self._tracks_file(replay_id), repair)
                            self._in_flight[future] = replay_id
                    except BrokenProcessPool:
                        self._requeue([rid for rid, _, _ in claimed if rid not in self._in_flight.values()])
                        self._recover_from_crash()
                        continue
                if not self._in_flight:
                    self._wake.wait(5)
                    self._wake.clear()
                    continue
                done, _ = wait(list(self._in_flight), timeout=1, return_when=FIRST_COMPLETED)
                if self._stop.is_set():
                    break
                broken = False
                for future in done:
                    try:
                        result = future.result()
                    except BrokenProcessPool:
                        broken = True
                        continue
                    except Exception as e:
                        result = ("failed", "internal", f"Processing error: {e}")
                    replay_id = self._in_flight.pop(future)
                    self._started.pop(replay_id, None)
                    self._crashes.pop(replay_id, None)
                    save_result(self.sessions, replay_id, result)
                if broken:
                    self._recover_from_crash()
        except Exception:
            log.exception("Worker loop stopped")
