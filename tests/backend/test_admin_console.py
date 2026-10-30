"""The admin console (app/admin_console.py) works on the database directly; a running server's worker picks up
the re-queued replays by itself (it polls the queue)."""

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings

import admin_console as console
from sqlalchemy import func, select

from backend.models import Replay


def match(players_blue, players_orange, **kw):
    return rf.plain(rf.lines(30, teams=[{"players": players_blue}, {"players": players_orange}, {}], **kw))


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {
            "dyson/1.echoreplay": match([rf.player(100, "Main")], [rf.player(300, "Mate", 1)]),
            "dyson/2.echoreplay": match([rf.player(100, "Main")], [rf.player(300, "Mate", 1)]),
            "surge/3.echoreplay": match([rf.player(200, "Alt")], [rf.player(300, "Mate", 1)], payload=True),
        })
        yield c


@pytest.fixture
def sessions(client):
    return console.open_sessions(client.app.state.settings)


def players(client):
    return {p["user_id"]: p["games"] for p in client.get("/api/players").json()["items"]}


def test_merge_and_undo(client, sessions, capsys):
    before = players(client)
    console.cmd_merge(sessions, "100", ["Alt"], yes=True, interactive=False)  # id or name
    client.app.state.worker.wait_idle()
    assert players(client) == {"100": 3, "300": 3}
    console.cmd_merges(sessions)
    assert "Alt" in capsys.readouterr().out

    console.cmd_unmerge(sessions, "200", yes=True)
    client.app.state.worker.wait_idle()
    assert players(client) == before


def test_merge_refusals(sessions):
    with pytest.raises(console.ConsoleError, match="main player"):
        console.cmd_merge(sessions, "100", ["100"], yes=True, interactive=False)
    with pytest.raises(console.ConsoleError, match="No player"):
        console.cmd_merge(sessions, "100", ["nobody"], yes=True, interactive=False)
    console.cmd_merge(sessions, "100", ["200"], yes=True, interactive=False)
    with pytest.raises(console.ConsoleError, match="itself merged"):
        console.cmd_merge(sessions, "200", ["300"], yes=True, interactive=False)


def test_ambiguous_name_needs_an_id(sessions):
    with pytest.raises(console.ConsoleError, match="several players"):
        console.resolve(sessions(), "a", interactive=False)  # "Main", "Mate", "Alt"


def test_challenge_period(client, sessions):
    console.cmd_challenge(sessions, "2026-01-01", None, False)
    assert client.get("/api/challenges").json()["start"] == "2026-01-01"
    with pytest.raises(console.ConsoleError, match="on or before"):
        console.cmd_challenge(sessions, None, "2025-01-01", False)
    console.cmd_challenge(sessions, None, None, True)
    assert client.get("/api/challenges").json()["start"] is None


def test_missing_database(tmp_path):
    with pytest.raises(console.ConsoleError, match="Start the server"):
        console.open_sessions(make_settings(tmp_path))


def test_hide_replays_that_cannot_be_repaired(tmp_path, capsys):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {"dyson/arena.echoreplay": rf.plain(rf.lines(5, match_type="Echo_Arena")),  # not Combat
                "dyson/ok.echoreplay": rf.plain(rf.lines(5))})
        sessions = console.open_sessions(c.app.state.settings)
        assert c.get("/api/import").json()["counts"]["failed"] == 1
        console.cmd_cannot_repair(sessions, hide=True, yes=True)
        status = c.get("/api/import").json()
        assert status["counts"]["failed"] == 0 and status["hidden_failed"] == 1
        assert c.get("/api/replays", params={"status": "failed"}).json()["items"] == []
        assert console.cmd_hidden(sessions, None, False, False) == ["dyson/arena.echoreplay"]
        console.cmd_hidden(sessions, None, True, True)  # show all again
        assert c.get("/api/import").json()["counts"]["failed"] == 1


def test_rescan_and_reprocess_everything(client, sessions, capsys):
    before = client.get("/api/matches").json()["total"]
    console.cmd_reprocess_all(sessions, client.app.state.settings, yes=True)
    out = capsys.readouterr().out
    assert "3 replays queued" in out
    with sessions() as db:  # queued, while the matches already saved stay visible
        assert db.scalar(select(func.count()).select_from(Replay).where(Replay.status == "queued")) == 3
    assert client.get("/api/matches").json()["total"] == before
    client.app.state.worker.wait_idle()
    assert client.get("/api/import").json()["counts"]["done"] == 3
    assert client.get("/api/matches").json()["total"] == before
