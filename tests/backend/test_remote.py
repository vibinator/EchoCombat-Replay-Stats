"""Remote processing: another PC reads the replays (backend/remote.py, api/remote_worker.py, app/remote_worker.py)."""

import json
import pickle
import time

import pytest
import replay_factory as rf
from app_helpers import app_client, make_settings, write
from sqlalchemy import select

from backend import remote
from backend.models import Match, Replay
from backend.scanner import scan_once
from backend.stats import STATS_VERSION
from backend.worker import analyse
from parser import PARSER_VERSION

SECRET = "s3cret-for-the-tests"
AUTH = {"Authorization": f"Bearer {SECRET}"}
VERSIONS = {"parser_version": PARSER_VERSION, "stats_version": STATS_VERSION}


def _pose(x, z):
    return {"position": [x, 0.0, z], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}


def a_match(n=40):
    frames = []
    for i in range(n):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        blue["head"] = _pose(-10 + i * 0.25, 0.0)
        orange["head"] = _pose(5.0, 5.0)
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}]))
    return rf.plain(rf.lines_from(frames))


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path, remote_worker_secret=SECRET, scraper_guard=True)) as c:
        yield c


def status_of(client, path):
    with client.app.state.sessionmaker() as db:
        return db.scalar(select(Replay.status).where(Replay.source_path == path))


def switch(client, on):
    with client.app.state.sessionmaker() as db:
        remote.set_enabled(db, on)


def queue(client, files, remote_on=True):
    """Put replays on the share and in the queue, without the server's own worker taking them."""
    switch(client, remote_on)
    write(client.app.state.settings, files)
    state = client.app.state
    scan_once(state.sessionmaker, state.settings, state.scanner.state)
    state.worker.notify()
    time.sleep(0.3)  # the worker looks once: it must leave them alone


def post(client, path, **kw):
    return client.post(path, headers=AUTH | kw.pop("headers", {}), **kw)


def claim(client, count=5):
    return post(client, "/api/worker/claim", json={"count": count} | VERSIONS)


def read_here(client, job):
    """What the PC does with a claimed replay: read it, with the track files, and pack it."""
    path = client.app.state.settings.source_dir / job["path"]
    tracks = path.parent / f"{path.name}.tracks.bin"
    outcome = analyse(str(path), str(tracks), job["repair"])
    files = (tracks.read_bytes() if tracks.exists() else b"", (tracks.parent / "tracks3d.bin").read_bytes()
             if (tracks.parent / "tracks3d.bin").exists() else b"")
    tracks.unlink(missing_ok=True)
    (tracks.parent / "tracks3d.bin").unlink(missing_ok=True)
    return remote.pack(outcome, *files)


def test_endpoints_need_the_secret_and_do_not_exist_without_one(tmp_path):
    with app_client(make_settings(tmp_path, remote_worker_secret="")) as off:
        assert off.post("/api/worker/claim", json={"count": 1} | VERSIONS).status_code == 404
    (tmp_path / "b").mkdir()
    with app_client(make_settings(tmp_path / "b", remote_worker_secret=SECRET, scraper_guard=True)) as on:
        no_header = on.post("/api/worker/claim", json={"count": 1} | VERSIONS)  # no browser header, no user agent needed
        assert no_header.status_code == 401 and no_header.json()["error_code"] == "bad_worker_secret"
        wrong = on.post("/api/worker/claim", json={"count": 1} | VERSIONS, headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401
        assert on.post("/api/worker/result/1", content=b"x").status_code == 401
        assert on.post("/api/worker/claim", headers=AUTH, json={"count": 1} | VERSIONS).status_code == 200
        assert on.post("/api/worker/claim", headers=AUTH, json={"count": 1} | VERSIONS).headers["cache-control"] == "private, no-store"


def test_a_pc_with_other_versions_is_turned_away(client):
    reply = post(client, "/api/worker/claim", json={"count": 1, "parser_version": "0", "stats_version": STATS_VERSION})
    assert reply.status_code == 409 and reply.json()["error_code"] == "version_mismatch"


def test_nothing_is_handed_out_while_remote_processing_is_off(client):
    queue(client, {"dyson/a.echoreplay": a_match()}, remote_on=False)  # the server's own worker reads it
    client.app.state.worker.wait_idle()
    switch(client, False)
    assert claim(client).json() == {"enabled": False, "jobs": []}


def test_the_pc_reads_a_replay_and_the_server_saves_it(client):
    queue(client, {"dyson/a.echoreplay": a_match(), "dyson/b.echoreplay": a_match(60)})
    assert status_of(client, "dyson/a.echoreplay") == "queued"  # the server's own worker took nothing
    reply = claim(client, 5).json()
    assert reply["enabled"] and sorted(j["path"] for j in reply["jobs"]) == ["dyson/a.echoreplay", "dyson/b.echoreplay"]
    assert status_of(client, "dyson/a.echoreplay") == "processing"
    assert claim(client).json()["jobs"] == []  # claimed: not handed out twice
    for job in reply["jobs"]:
        saved = post(client, f"/api/worker/result/{job['id']}", content=read_here(client, job))
        assert saved.status_code == 200 and saved.json()["saved"] is True and "save_s" in saved.json()
    assert status_of(client, "dyson/a.echoreplay") == status_of(client, "dyson/b.echoreplay") == "done"
    with client.app.state.sessionmaker() as db:
        assert db.query(Match).count() == 2
    ids = {j["path"]: j["id"] for j in reply["jobs"]}
    processed = client.app.state.settings.processed_dir
    assert (processed / str(ids["dyson/a.echoreplay"]) / "tracks.bin").exists()  # heatmaps and the timeline work
    assert (processed / str(ids["dyson/a.echoreplay"]) / "tracks3d.bin").exists()  # and 3D playback
    page = {"X-EchoVR": "1", "User-Agent": "Mozilla/5.0"}  # the website's own pages send these
    matches = client.get("/api/matches", headers=page).json()
    assert matches["total"] == 2 and all(m["duration_s"] > 0 for m in matches["items"])
    assert client.get(f"/api/matches/{matches['items'][0]['id']}/playback3d", headers=page).status_code == 200
    # the same replay read by the server itself gives the same match
    with client.app.state.sessionmaker() as db:
        remote_made = {m.replay_id: (m.frame_count, m.duration_s, m.map) for m in db.scalars(select(Match))}
    local = analyse(str(client.app.state.settings.source_dir / "dyson/a.echoreplay"))
    assert remote_made[ids["dyson/a.echoreplay"]] == (local[2].frame_count, local[2].duration_s, local[2].map)


def test_a_result_for_a_replay_that_is_not_claimed_is_dropped(client):
    queue(client, {"dyson/a.echoreplay": a_match()})
    job = claim(client).json()["jobs"][0]
    body = read_here(client, job)
    assert post(client, f"/api/worker/release", json={"ids": [job["id"]]}).json() == {"queued": 1}
    assert status_of(client, "dyson/a.echoreplay") == "queued"  # given back
    late = post(client, f"/api/worker/result/{job['id']}", content=body)
    assert late.status_code == 409 and late.json()["error_code"] == "not_claimed"
    assert status_of(client, "dyson/a.echoreplay") == "queued"  # the late answer changed nothing


def test_a_result_may_only_hold_result_classes(client, tmp_path):
    """The body is an object: anything but the result classes and plain values is refused, and never run."""
    queue(client, {"dyson/a.echoreplay": a_match()})
    job = claim(client).json()["jobs"][0]
    trap = tmp_path / "ran.txt"

    class Evil:
        def __reduce__(self):
            return open, (str(trap), "w")  # would create the file when loaded

    body = remote.MAGIC + b"".join(len(p).to_bytes(4, "little") + p for p in (pickle.dumps(("ok", Evil()), protocol=4), b"", b""))
    reply = post(client, f"/api/worker/result/{job['id']}", content=body)
    assert reply.status_code == 400 and reply.json()["error_code"] == "bad_result"
    assert not trap.exists()
    for junk in (b"", b"hello", remote.MAGIC + b"\x01\x00\x00\x00"):
        assert post(client, f"/api/worker/result/{job['id']}", content=junk).status_code == 400
    assert remote.claimed(job["id"]) and status_of(client, "dyson/a.echoreplay") == "processing"  # still the PC's


def test_damaged_track_files_are_left_out_not_saved(client):
    queue(client, {"dyson/a.echoreplay": a_match()})
    job = claim(client).json()["jobs"][0]
    outcome = analyse(str(client.app.state.settings.source_dir / job["path"]))
    reply = post(client, f"/api/worker/result/{job['id']}", content=remote.pack(outcome, b"garbage", b"more garbage"))
    assert reply.status_code == 200 and status_of(client, "dyson/a.echoreplay") == "done"
    folder = client.app.state.settings.processed_dir / str(job["id"])
    assert not (folder / "tracks.bin").exists() and not (folder / "tracks3d.bin").exists()
    with client.app.state.sessionmaker() as db:
        assert db.scalar(select(Match.has_tracks).where(Match.replay_id == job["id"])) is False


def test_a_failed_replay_is_saved_as_failed(client):
    queue(client, {"dyson/a.echoreplay": b"this is not a replay"})
    job = claim(client).json()["jobs"][0]
    reply = post(client, f"/api/worker/result/{job['id']}", content=read_here(client, job))
    assert reply.status_code == 200 and status_of(client, "dyson/a.echoreplay") == "failed"


def test_turning_remote_processing_off_gives_the_server_its_replays_back(client):
    queue(client, {"dyson/a.echoreplay": a_match(), "dyson/b.echoreplay": a_match(60)})
    assert len(claim(client).json()["jobs"]) == 2
    switch(client, False)  # the PC is gone
    client.app.state.worker.notify()
    client.app.state.worker.wait_idle()  # the server's own worker takes them back and reads them
    assert status_of(client, "dyson/a.echoreplay") == status_of(client, "dyson/b.echoreplay") == "done"
    with client.app.state.sessionmaker() as db:
        assert db.query(Match).count() == 2


def test_a_claim_with_no_answer_for_too_long_is_queued_again(client, monkeypatch):
    queue(client, {"dyson/a.echoreplay": a_match()})
    job = claim(client).json()["jobs"][0]
    assert remote.requeue_abandoned(client.app.state.sessionmaker) == 0  # not yet
    monkeypatch.setattr(remote, "CLAIM_TIMEOUT_S", -1)
    assert remote.requeue_abandoned(client.app.state.sessionmaker) == 1
    assert status_of(client, "dyson/a.echoreplay") == "queued" and not remote.claimed(job["id"])


def test_the_console_says_where_replays_are_processed(client):
    from admin_console import cmd_remote_processing
    sessions = client.app.state.sessionmaker
    with sessions() as db:
        assert remote.describe(db).startswith("on this server")
    assert cmd_remote_processing(sessions, True) is True
    with sessions() as db:
        assert "no PC has asked" in remote.describe(db)
    claim(client)  # a PC asked for work
    remote._seen_written = 0.0
    claim(client)
    with sessions() as db:
        assert "last asked for work just now" in remote.describe(db)
    assert cmd_remote_processing(sessions, False) is False


def test_web_console_commands(client):
    # the website's Console runs the same commands (needs a console login: the commands themselves are checked here)
    from backend.api.console import COMMANDS, Args
    sessions, settings = client.app.state.sessionmaker, client.app.state.settings
    COMMANDS["remote-on"](sessions, settings, Args())
    with sessions() as db:
        assert remote.enabled(db)
    COMMANDS["remote-off"](sessions, settings, Args())
    with sessions() as db:
        assert not remote.enabled(db)


def test_pack_round_trip():
    outcome = analyse_for_pack()
    body = remote.pack(outcome, b"tracks", b"tracks3d")
    got, tracks, tracks3d = remote.unpack(body)
    assert (tracks, tracks3d) == (b"tracks", b"tracks3d") and got[1] == outcome[1] and got[2] == outcome[2]


def analyse_for_pack(tmp_dir=None):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "a.echoreplay"
        path.write_bytes(a_match())
        return analyse(str(path))


def test_queue_missing_is_idempotent(client):
    from backend import admin_actions as actions
    sessions = client.app.state.sessionmaker
    with sessions() as db:
        def add(path, status, code=None):
            db.add(Replay(source_path=path, size_bytes=1, source_mtime=1.0, discovered_at="x", status=status, error_code=code))
        add("a.echoreplay", "done")              # finished, no match: missing
        add("b.echoreplay", "failed", "unreadable")  # network error: retry
        add("c.echoreplay", "failed", "corrupt")     # broken file: not touched
        add("d.echoreplay", "queued")            # already waiting: not touched
        db.commit()
        assert actions.queue_missing(db) == {"no_match": 1, "unreadable": 1}
        assert actions.queue_missing(db) == {"no_match": 0, "unreadable": 0}  # second run queues nothing
        status = dict(db.execute(select(Replay.source_path, Replay.status)).all())
    assert status == {"a.echoreplay": "queued", "b.echoreplay": "queued", "c.echoreplay": "failed", "d.echoreplay": "queued"}
