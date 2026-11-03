import os
import time

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings, replay_by_path, sync, write

from backend import admin_actions as actions

from backend.models import Replay
from backend.scanner import Scanner, ScanState, Snapshot, dirs_changed, scan_once


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    with app_client(settings) as c:
        yield c


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime) for p in root.rglob("*"))


def test_scan_imports_files_in_map_folders(client, settings):
    write(settings, {
        "surge/a.echoreplay": rf.zipped(rf.lines(5, payload=True)),
        "dyson/B.EchoReplay": rf.plain(rf.lines(5)),
        "images/image.png": b"png",
        "notes.zip": b"PK",
    })
    assert sync(client) == 2
    a, b = replay_by_path(client, "surge/a.echoreplay"), replay_by_path(client, "dyson/B.EchoReplay")
    assert (a["status"], a["container"], b["container"]) == ("done", "zip", "plain")
    assert a["match_id"] and b["match_id"]
    assert client.get("/api/import").json()["counts"] == {"queued": 0, "processing": 0, "done": 2, "failed": 0}
    assert client.app.state.scanner.state.files == 2


def test_share_is_never_modified(client, settings):
    write(settings, {"surge/a.echoreplay": rf.zipped(rf.lines(5)), "fission/bad.echoreplay": b"not a replay"})
    before = snapshot(settings.source_dir)
    sync(client)
    act(client, actions.reprocess, replay_by_path(client, "surge/a.echoreplay")["id"])
    client.app.state.worker.wait_idle()
    assert snapshot(settings.source_dir) == before


def test_rescan_only_queues_new_or_changed(client, settings):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
    first = replay_by_path(client, "dyson/a.echoreplay")
    assert sync(client) == 0  # unchanged

    write(settings, {"dyson/a.echoreplay": rf.plain(rf.lines(8))})  # size changes
    assert sync(client) == 1
    again = replay_by_path(client, "dyson/a.echoreplay")
    assert again["id"] == first["id"] and again["status"] == "done"
    assert client.get(f"/api/matches/{again['match_id']}").json()["duration_s"] == pytest.approx(7 / 20)


def test_recently_modified_files_wait_to_settle(tmp_path):
    settings = make_settings(tmp_path, settle_s=3600)
    write(settings, {"dyson/live.echoreplay": rf.plain(rf.lines(3))})
    with app_client(settings) as client:
        assert sync(client) == 0
        assert client.app.state.scanner.state.settling == 1
        assert client.get("/api/replays").json()["total"] == 0


def test_copied_in_file_waits_to_settle_even_with_old_modified_time(tmp_path):
    # Explorer / robocopy keep the original modified time; the copy (creation / change) time counts too
    settings = make_settings(tmp_path, settle_s=3600)
    write(settings, {"dyson/copied.echoreplay": rf.plain(rf.lines(3))})
    old = time.time() - 86400
    os.utime(settings.source_dir / "dyson" / "copied.echoreplay", (old, old))
    with app_client(settings) as client:
        assert sync(client) == 0
        assert client.app.state.scanner.state.settling == 1


def test_settling_file_sets_when_to_scan_again(tmp_path):
    settings = make_settings(tmp_path, settle_s=60)
    write(settings, {"dyson/live.echoreplay": rf.plain(rf.lines(3))})
    with app_client(settings) as client:
        snapshot = Snapshot()
        scan_once(client.app.state.sessionmaker, settings, ScanState(), snapshot)
        assert snapshot.settle_due == pytest.approx(time.time() + 60, abs=5)


def test_new_file_changes_the_folder_snapshot(client, settings):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(3))})
    snapshot = Snapshot()
    scan_once(client.app.state.sessionmaker, settings, ScanState(), snapshot)
    assert str(settings.source_dir) in snapshot.dirs and str(settings.source_dir / "dyson") in snapshot.dirs
    assert snapshot.settle_due is None and not dirs_changed(snapshot.dirs)
    time.sleep(0.05)  # coarse folder timestamps on some file systems
    write(settings, {"dyson/b.echoreplay": rf.plain(rf.lines(3))})
    assert dirs_changed(snapshot.dirs)


def test_scanner_picks_up_new_file_without_waiting_for_the_interval(tmp_path):
    settings = make_settings(tmp_path, auto_scan=True, scan_interval_s=3600, quick_check_s=0.05)
    write(settings, {"dyson/a.echoreplay": rf.plain(rf.lines(3))})
    with app_client(settings) as client:
        client.app.state.worker.wait_idle()
        time.sleep(0.2)  # first full scan done, scanner now on quick checks
        write(settings, {"surge/b.echoreplay": rf.plain(rf.lines(3))})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and client.get("/api/replays").json()["total"] < 2:
            time.sleep(0.05)
        client.app.state.worker.wait_idle()
        statuses = {r["source_path"]: r["status"] for r in client.get("/api/replays").json()["items"]}
    assert statuses == {"dyson/a.echoreplay": "done", "surge/b.echoreplay": "done"}


def test_unreachable_share_keeps_existing_data(client, settings, tmp_path):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
    state = ScanState()
    offline = make_settings(tmp_path, source_dir=tmp_path / "offline")
    assert scan_once(client.app.state.sessionmaker, offline, state) == 0
    assert state.reachable is False and "not reachable" in state.error
    assert client.get("/api/matches").json()["total"] == 1


def test_bad_files_fail_with_reason(client):
    add(client, {
        "dyson/arena.echoreplay": rf.plain(rf.lines(2, match_type="Echo_Arena")),
        "dyson/junk.echoreplay": b"hello world",
        "dyson/short.echoreplay": rf.plain(rf.lines(1)),
    })
    codes = {r["source_path"]: r["error_code"] for r in client.get("/api/replays", params={"status": "failed"}).json()["items"]}
    assert codes == {"dyson/arena.echoreplay": "unsupported", "dyson/junk.echoreplay": "corrupt",
                     "dyson/short.echoreplay": "incomplete"}


def test_newest_files_are_processed_first(client, settings):
    write(settings, {f"dyson/{n}.echoreplay": rf.plain(rf.lines(3)) for n in ("old", "new", "mid")})
    now = time.time()
    for name, age in (("old", 300), ("mid", 200), ("new", 100)):
        os.utime(settings.source_dir / "dyson" / f"{name}.echoreplay", (now - age, now - age))
    scan_once(client.app.state.sessionmaker, settings, client.app.state.scanner.state)
    claimed = client.app.state.worker._claim(3)
    assert [p.rsplit(os.sep, 1)[-1] for _, p, _ in claimed] == ["new.echoreplay", "mid.echoreplay", "old.echoreplay"]


BACKLOG = 20_000  # any large number: the newest file goes next however many are queued


def test_new_match_jumps_a_large_backlog(client, settings):
    """A large historic backlog is queued and being worked through; a match recorded now is the very next file
    claimed, whatever the backlog size."""
    from sqlalchemy import insert

    old = time.time() - 365 * 86400
    with client.app.state.sessionmaker() as db:
        db.execute(insert(Replay), [
            {"source_path": f"dyson/hist{i}.echoreplay", "size_bytes": 1, "source_mtime": old + i,
             "discovered_at": "x", "status": "queued"} for i in range(BACKLOG)])
        db.commit()
    worker = client.app.state.worker
    first = [p.rsplit(os.sep, 1)[-1] for _, p, _ in worker._claim(8)][0]
    assert first == f"hist{BACKLOG - 1}.echoreplay"  # backlog under way, newest of it first

    write(settings, {"fission/live.echoreplay": rf.plain(rf.lines(3))})  # just recorded
    assert scan_once(client.app.state.sessionmaker, settings, client.app.state.scanner.state) == 1
    started = time.perf_counter()
    claimed = worker._claim(1)
    assert claimed[0][1].rsplit(os.sep, 1)[-1] == "live.echoreplay"
    assert time.perf_counter() - started < 1  # picking from a large queue uses the (status, mtime) index


def test_priority_replays_newest_match_first(client, settings):
    """Merge / undo re-reads (priority_replays) go newest match first, whatever the file dates."""
    from datetime import timedelta

    from sqlalchemy import select, update

    from backend.admin_actions import prioritise
    from backend.models import Replay

    add(client, {f"dyson/{name}.echoreplay": rf.plain(rf.lines(3, start=rf.START + timedelta(days=days)))
                 for name, days in (("early", 0), ("late", 2), ("middle", 1))})
    now = time.time()
    for name, age in (("early", 100), ("middle", 200), ("late", 300)):  # files dated the other way round
        os.utime(settings.source_dir / "dyson" / f"{name}.echoreplay", (now - age, now - age))
    with client.app.state.sessionmaker() as db:
        ids = list(db.scalars(select(Replay.id)))
        db.execute(update(Replay).values(status="queued"))
        prioritise(db, ids)
        db.commit()
    claimed = client.app.state.worker._claim(3)
    assert [p.rsplit(os.sep, 1)[-1] for _, p, _ in claimed] == ["late.echoreplay", "middle.echoreplay", "early.echoreplay"]


def test_no_download(client):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(3))})
    assert client.get("/api/replays/1/file").status_code == 404


def test_no_upload_or_delete(client):
    assert client.post("/api/replays", files=[("files", ("a.echoreplay", b"x"))]).status_code == 405
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(3))})
    assert client.delete("/api/replays/1").status_code == 405


def test_reprocess_and_busy(client):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(3))})
    with client.app.state.sessionmaker() as db:
        db.get(Replay, 1).status = "queued"
        db.commit()
    with pytest.raises(actions.AdminError, match="already queued"):
        act(client, actions.reprocess, 1)
    client.app.state.worker.wait_idle()
    act(client, actions.reprocess, 1)
    client.app.state.worker.wait_idle()
    assert client.get("/api/replays/1").json()["status"] == "done"


def test_get_missing_uses_error_format(client):
    r = client.get("/api/replays/999")
    assert r.status_code == 404
    assert r.json() == {"error_code": "not_found", "message": "Replay 999 not found"}


def test_process_pool_mode(tmp_path):
    settings = make_settings(tmp_path, workers=2)
    write(settings, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(3)})
    with app_client(settings) as client:
        sync(client)
        assert client.get("/api/import").json()["counts"]["done"] == 3


def test_restart_does_not_reprocess(tmp_path):
    settings = make_settings(tmp_path)
    write(settings, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(10)) for i in range(5)})
    write(settings, {"dyson/bad.echoreplay": b"not a replay"})
    with app_client(settings) as client:
        sync(client)
        before = {r["source_path"]: (r["status"], r["processed_at"], r["match_id"])
                  for r in client.get("/api/replays").json()["items"]}

    import backend.worker as worker_module

    calls = []
    original = worker_module.analyse
    worker_module.analyse = lambda *args: calls.append(args) or original(*args)
    try:
        with app_client(settings) as client:  # restart on the same database
            assert sync(client) == 0  # scan finds nothing new or changed
            after = {r["source_path"]: (r["status"], r["processed_at"], r["match_id"])
                     for r in client.get("/api/replays").json()["items"]}
    finally:
        worker_module.analyse = original
    assert calls == []  # no file was read again
    assert after == before  # same results, same processed_at, same matches (incl. the failed file)


def test_import_status_breaks_down_processing(client):
    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(10)), "surge/b.echoreplay": rf.plain(rf.lines(10, payload=True)),
                 "dyson/bad.echoreplay": b"junk"})
    status = client.get("/api/import").json()
    stages = {s["key"]: s for s in status["stages"]}
    assert list(stages) == ["files", "replays", "matches", "players", "events", "tracks", "heatmaps", "leaderboard", "achievements"]
    assert (stages["replays"]["done"], stages["replays"]["total"]) == (3, 3)
    assert stages["matches"]["done"] == 2 and stages["tracks"]["done"] == 2 and stages["tracks"]["total"] == 2
    assert stages["players"]["done"] == 2 and "1 failed" in stages["replays"]["detail"]
    assert status["current"] == [] and status["redo"] == 0
    assert status["matches_by_map"] == {"dyson": 1, "surge": 1}
    assert status["rate_per_min"] > 0 and status["eta_min"] is None  # nothing waiting


def test_indexes_added_to_an_existing_database(tmp_path):
    """create_all skips existing tables: open_db adds indexes that came with a newer model."""
    import sqlite3

    from backend.db import open_db

    path = make_settings(tmp_path).db_path
    open_db(path)[0].dispose()
    con = sqlite3.connect(path)
    con.execute("DROP INDEX ix_players_last_seen_at")
    con.commit()
    con.close()
    engine, _ = open_db(path)
    with engine.connect() as conn:
        names = {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'index'")}
    engine.dispose()
    assert {"ix_players_last_seen_at", "ix_replays_status_processed"} <= names


def test_replays_with_hex_gear_codes_are_reread_once(client):
    """Rows saved before the parser normalised older-API hex symbols are re-read at startup."""
    from sqlalchemy import update

    from backend.models import MatchPlayerLoadout
    from backend.worker import requeue_unfinished_and_outdated

    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
    sessions = client.app.state.sessionmaker
    assert requeue_unfinished_and_outdated(sessions) == 0
    with sessions() as db:
        db.execute(update(MatchPlayerLoadout).values(tacmod="0xC8C33E4832761FBC"))  # as an old import stored it
        db.commit()
    assert requeue_unfinished_and_outdated(sessions) == 1
    client.app.state.worker.wait_idle()
    assert requeue_unfinished_and_outdated(sessions) == 0  # re-read: codes are plain now


def test_import_status_shows_redo_progress(client):
    """A queued redo keeps the old match on the website, but the stages that depend on it must not read as complete."""
    from sqlalchemy import update

    from backend.models import Replay

    add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(10)), "surge/b.echoreplay": rf.plain(rf.lines(10, payload=True))})
    with client.app.state.sessionmaker() as db:
        db.execute(update(Replay).where(Replay.source_path.like("surge/%")).values(status="queued"))
        db.commit()
    stages = {s["key"]: s for s in client.get("/api/import").json()["stages"]}
    for key in ("matches", "leaderboard", "achievements"):
        assert (stages[key]["done"], stages[key]["total"]) == (1, 2), key
    assert stages["tracks"]["done"] == 1 and stages["tracks"]["total"] == 2
