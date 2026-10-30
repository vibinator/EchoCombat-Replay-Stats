import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

from backend.db import open_db
from backend.models import Replay
from backend.stats import STATS_VERSION
from backend.worker import analyse, requeue_unfinished_and_outdated
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
