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


def test_admin_links_a_player_to_a_discord_account_and_reports(tmp_path, capsys):
    from backend.db import open_db
    from backend.models import Player, PlayerProfile
    import admin_console as console
    _, sm = open_db(tmp_path / "t.db", 0)
    d1, d2 = "1346263035425325078", "1033759231184224368"
    with sm() as db:
        db.add_all([Player(user_id=d1, name="Recent", first_seen_at="t", last_seen_at="2099-01-01"),
                    Player(user_id="oculus-1", name="Old", first_seen_at="t", last_seen_at="2099-01-01")])
        db.commit()
    with pytest.raises(console.ConsoleError):
        console.cmd_link_profile(sm, "Old", "12", yes=True)  # not a Discord id
    console.cmd_link_profile(sm, "oculus-1", d2, yes=True)
    r = console.cmd_profile_links(sm)
    assert (r["players"], r["linked_by_bot_or_admin"], r["player_id_is_discord_id"], r["players_unlinked"]) == (2, 1, 1, 0)
    console.cmd_link_profile(sm, "Recent", d2, yes=True)  # one player per Discord account: the link moves
    with sm() as db:
        assert db.scalar(select(PlayerProfile.user_id)) == d1
    console.cmd_unlink_profile(sm, d2, yes=True)
    with sm() as db:
        assert db.scalar(select(PlayerProfile.user_id)) is None
