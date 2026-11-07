"""Fixes from the 2026-11-07 review (docs/Review-2026-11-07.MD): a busy database postpones a replay instead of failing it
(BUG-1), forget-missing after a moved replay root (BUG-2), ids beyond 64 bits and validation errors in the site's error
shape (BUG-4, BUG-9), the Combat tab flag on a match (BUG-7), empty combat lobbies left out of the match list (GUI-7)."""

import replay_factory as rf
from app_helpers import app_client, make_settings, write
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from backend import admin_actions, worker
from backend.models import Match, Replay
from backend.scanner import scan_once

PAGE = {"X-EchoVR": "1", "User-Agent": "Mozilla/5.0"}


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


def _import(client, files):
    state = client.app.state
    write(state.settings, files)
    scan_once(state.sessionmaker, state.settings, state.scanner.state)
    state.worker.notify()
    state.worker.wait_idle()


def test_a_busy_database_postpones_the_replay_and_keeps_its_match(tmp_path, monkeypatch):
    with app_client(make_settings(tmp_path)) as client:
        _import(client, {"dyson/a.echoreplay": a_match()})
        sessions = client.app.state.sessionmaker
        with sessions() as db:
            replay = db.scalar(select(Replay))
            assert replay.status == "done" and db.scalar(select(Match.id).where(Match.replay_id == replay.id))
            replay.status = "processing"  # as during a re-read
            db.commit()
            rid = replay.id

        def locked(*_a, **_k):
            raise OperationalError("INSERT", {}, Exception("database is locked"))

        monkeypatch.setattr(worker, "save_match", locked)
        result = worker.analyse(str(client.app.state.settings.source_dir / "dyson/a.echoreplay"))
        worker.save_result(sessions, rid, result)
        with sessions() as db:
            replay = db.get(Replay, rid)
            assert replay.status == "queued" and replay.error_code is None  # tried again later, not failed
            assert db.scalar(select(Match.id).where(Match.replay_id == rid)) is not None  # the old match stays


def test_forget_missing_removes_rows_whose_file_is_gone_and_keeps_the_rest(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        _import(client, {"dyson/a.echoreplay": a_match(), "dyson/b.echoreplay": a_match(30)})
        settings, sessions = client.app.state.settings, client.app.state.sessionmaker
        (settings.source_dir / "dyson/a.echoreplay").unlink()
        with sessions() as db:
            assert [r.source_path for r in admin_actions.missing_replays(db, settings)] == ["dyson/a.echoreplay"]
            assert admin_actions.forget_missing(db, settings) == 1
            assert db.scalars(select(Replay.source_path)).all() == ["dyson/b.echoreplay"]
            assert db.scalar(select(Match.id).join(Replay).where(Replay.source_path == "dyson/b.echoreplay")) is not None
            assert admin_actions.forget_missing(db, settings) == 0


def test_forget_missing_refuses_while_the_replay_folder_is_offline(tmp_path):
    import shutil

    with app_client(make_settings(tmp_path)) as client:
        _import(client, {"dyson/a.echoreplay": a_match()})
        settings, sessions = client.app.state.settings, client.app.state.sessionmaker
        shutil.rmtree(settings.source_dir)  # the share is gone, not the files
        with sessions() as db:
            try:
                admin_actions.missing_replays(db, settings)
            except admin_actions.AdminError as e:
                assert "not reachable" in str(e)
            else:
                raise AssertionError("an offline folder must not look like every file is missing")
            assert db.scalar(select(Replay)) is not None


def test_error_shape_for_validation_and_huge_ids(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        r = client.get("/api/matches?limit=1000", headers=PAGE)
        assert r.status_code == 422 and r.json()["error_code"] == "bad_request" and r.json()["message"].startswith("limit:")
        r = client.get("/api/matches/" + "9" * 30, headers=PAGE)
        assert r.status_code == 404 and r.json()["error_code"] == "not_found"


def test_match_says_whether_it_has_a_combat_report(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        _import(client, {"dyson/a.echoreplay": a_match()})
        m = client.get("/api/matches?limit=1", headers=PAGE).json()["items"][0]
        assert client.get(f"/api/matches/{m['id']}", headers=PAGE).json()["has_combat"] is False
