import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

from backend.db import open_db
from backend.models import Replay
from backend.stats import STATS_VERSION
from backend.worker import analyse, clock_warning, requeue_unfinished_and_outdated
from parser import PARSER_VERSION


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


def test_valid_replay_is_processed(settings):
    with app_client(settings) as client:
        add(client, {"dyson/a.echoreplay": rf.zipped(rf.lines(5))})
        replay = replay_by_path(client, "dyson/a.echoreplay")
    assert replay["status"] == "done"
    assert replay["parser_version"] == PARSER_VERSION and replay["stats_version"] == STATS_VERSION
    assert replay["processed_at"] and replay["error_code"] is None and replay["warnings"] == []


def test_warnings_are_stored(settings):
    lines = rf.lines(4)
    lines[-1] = lines[-1][:30]
    with app_client(settings) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(lines)})
        replay = replay_by_path(client, "dyson/a.echoreplay")
    assert replay["status"] == "done" and len(replay["warnings"]) == 1


def test_analyse_reports_unreadable_file(tmp_path):
    assert analyse(str(tmp_path / "missing.echoreplay"))[:2] == ("failed", "unreadable")


def test_startup_requeues_unfinished_and_outdated(settings):
    engine, sessions = open_db(settings.db_path)
    rows = [
        ("a", "processing", None, None),
        ("b", "done", "0", STATS_VERSION),  # old parser
        ("c", "done", PARSER_VERSION, "0"),  # old stats
        ("d", "done", PARSER_VERSION, STATS_VERSION),  # current: kept
        ("e", "failed", PARSER_VERSION, None),  # failed with current parser: kept
        ("f", "queued", None, None),  # already queued
    ]
    with sessions() as db:
        for name, status, parser_version, stats_version in rows:
            db.add(Replay(source_path=f"dyson/{name}.echoreplay", size_bytes=1, source_mtime=1.0,
                          discovered_at="2026-10-30T00:00:00+00:00", status=status,
                          parser_version=parser_version, stats_version=stats_version))
        db.commit()
    assert requeue_unfinished_and_outdated(sessions) == 3
    with sessions() as db:
        statuses = {r.source_path[6]: r.status for r in db.query(Replay)}
    engine.dispose()
    assert statuses == {"a": "queued", "b": "queued", "c": "queued", "d": "done", "e": "failed", "f": "queued"}


def test_startup_requeues_bone_data_failures_once(settings):
    from backend.worker import BONE_DATA_SINCE

    engine, sessions = open_db(settings.db_path)
    old_message = "Too many unreadable lines (11 of 14)"  # the parser before bone data, on a bone-data replay
    rows = [
        ("a", BONE_DATA_SINCE + 60, old_message),  # re-read
        ("b", BONE_DATA_SINCE - 60, old_message),  # older file: really damaged, kept
        ("c", BONE_DATA_SINCE + 60, "Too many unreadable frame lines (11 of 14)"),  # current parser: kept
        ("d", BONE_DATA_SINCE + 60, "First frame is unreadable"),  # another failure: kept
    ]
    with sessions() as db:
        for name, mtime, message in rows:
            db.add(Replay(source_path=f"dyson/{name}.echoreplay", size_bytes=1, source_mtime=mtime,
                          discovered_at="2026-11-19T00:00:00+00:00", status="failed", error_code="corrupt",
                          error_message=message, parser_version=PARSER_VERSION))
        db.commit()
    assert requeue_unfinished_and_outdated(sessions) == 1
    with sessions() as db:
        statuses = {r.source_path[6]: r.status for r in db.query(Replay)}
    engine.dispose()
    assert statuses == {"a": "queued", "b": "failed", "c": "failed", "d": "failed"}


def test_pool_crash_requeues_then_fails_repeat_offender(settings):
    from concurrent.futures import Future

    from backend.worker import MAX_CRASHES, Worker

    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        db.add(Replay(source_path="dyson/a.echoreplay", size_bytes=1, source_mtime=1.0,
                      discovered_at="x", status="processing"))
        db.commit()
    worker = Worker(sessions, settings)
    worker._pool = worker._new_pool()
    for attempt in range(1, MAX_CRASHES + 1):
        worker._in_flight = {Future(): 1}
        worker._recover_from_crash()
        with sessions() as db:
            replay = db.get(Replay, 1)
            expected = "queued" if attempt < MAX_CRASHES else "failed"
            assert replay.status == expected
            if expected == "failed":
                assert replay.error_code == "crashed"
            replay.status = "processing"
            db.commit()
    worker._pool.shutdown()
    engine.dispose()


def test_crash_while_stopping_leaves_rows_for_next_start(settings):
    from concurrent.futures import Future

    from backend.worker import Worker

    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        db.add(Replay(source_path="dyson/a.echoreplay", size_bytes=1, source_mtime=1.0,
                      discovered_at="x", status="processing"))
        db.commit()
    worker = Worker(sessions, settings)
    worker._pool = worker._new_pool()
    worker._stop.set()
    worker._in_flight = {Future(): 1}
    worker._recover_from_crash()
    with sessions() as db:
        assert db.get(Replay, 1).status == "processing"  # not failed
    assert requeue_unfinished_and_outdated(sessions) == 1
    engine.dispose()


def test_worker_loop_survives_an_error_and_carries_on(settings, monkeypatch):
    """2026-11-16 and 2026-11-18: one error (a damaged index, then unknown) ended the loop and the queue sat until a
    restart. Now it is logged, the claimed-but-not-started replay goes back into the queue, and the loop carries on."""
    from sqlalchemy.exc import OperationalError

    from backend import worker as worker_module

    monkeypatch.setattr(worker_module, "LOOP_RETRY_MAX_S", 0)
    real_claim, calls = worker_module.claim_queued, []

    def flaky_claim(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("UPDATE replays", {}, Exception("database is locked"))
        return real_claim(*args, **kwargs)

    monkeypatch.setattr(worker_module, "claim_queued", flaky_claim)
    with app_client(settings) as client:
        add(client, {"dyson/a.echoreplay": rf.zipped(rf.lines(5))})
        replay = replay_by_path(client, "dyson/a.echoreplay")
        status = client.get("/api/import").json()
    assert len(calls) >= 2 and replay["status"] == "done"
    assert status["worker_running"] is True and "database is locked" in status["worker_error"]


def test_failed_save_puts_the_replay_back_in_the_queue(settings, monkeypatch):
    from concurrent.futures import Future

    from backend import worker as worker_module
    from backend.worker import Worker

    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        db.add(Replay(source_path="dyson/a.echoreplay", size_bytes=1, source_mtime=1.0,
                      discovered_at="x", status="processing"))
        db.commit()
    worker = Worker(sessions, settings)
    worker._pool = worker._new_pool()
    future = Future()
    future.set_result(("failed", "damaged", "x"))
    worker._in_flight, worker._started = {future: 1}, {1: ("dyson/a.echoreplay", 0.0)}
    monkeypatch.setattr(worker_module, "save_result", lambda *a: (_ for _ in ()).throw(RuntimeError("disk full")))
    with pytest.raises(RuntimeError):
        worker._step()
    worker._after_error()
    with sessions() as db:
        assert db.get(Replay, 1).status == "queued"
    assert not worker._started and not worker._in_flight
    worker._pool.shutdown()
    engine.dispose()


def test_side_jobs_run_apart_from_the_replay_pool(settings):
    """3D builds (run_side) have their own pool: not behind queued replays, and not shared with their crashes."""
    from backend.worker import Worker

    worker = Worker(None, settings)  # workers=0 in the tests: threads
    assert worker.run_side(pow, 2, 5).result(timeout=10) == 32
    assert worker._pool is None and worker._sides.get("side") is not None  # the replay pool was not used (nor created)
    worker._stop.set()
    with pytest.raises(RuntimeError):  # stopping: no new jobs
        worker.run_side(pow, 2, 5)
    worker._sides["side"].shutdown()


def test_side_pool_that_crashed_is_replaced_and_leaves_the_replay_pool_alone(settings):
    import dataclasses
    import os
    from concurrent.futures.process import BrokenProcessPool

    from backend.worker import Worker

    worker = Worker(None, dataclasses.replace(settings, workers=2))  # real processes: a job can kill its process
    worker._pool = main = worker._new_pool()
    try:
        with pytest.raises(BrokenProcessPool):
            worker.run_side(os._exit, 1).result(timeout=60)
        assert worker.run_side(pow, 2, 5).result(timeout=60) == 32  # a fresh pool took the next job
        assert worker._pool is main and main.submit(pow, 2, 3).result(timeout=60) == 8  # replay processing never noticed
        assert not worker._in_flight  # and no replay was blamed for the crash
    finally:
        main.shutdown()
        worker._sides["side"].shutdown()


class _Stats:
    def __init__(self, duration_s, *play_times):
        self.duration_s = duration_s
        self.players = [type("P", (), {"play_time_s": t})() for t in play_times]


@pytest.mark.parametrize("duration, plays, flagged", [
    (480, (470, 300), False),       # an ordinary match
    (900, (420,), False),           # someone arrived late and left: 8 min slack is fine
    (4015, (415, 300), True),       # an hour too long (clocks forward, match 213393)
    (-3029, (566,), True),          # an hour too short (clocks back)
    (0, (0,), True),
])
def test_clock_warning(duration, plays, flagged):
    note = clock_warning(_Stats(duration, *plays))
    assert (note is not None) == flagged
    assert note is None or "clock probably jumped" in note
