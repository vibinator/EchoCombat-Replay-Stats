"""Win-loss stats hidden from players (Console: Hide stats from players): left out of every answer except for
logged-in admins, and such answers are never kept by Cloudflare. Discord is mocked (test_discord_preview)."""

import replay_factory as rf
from app_helpers import act, add, app_client
from test_discord_preview import BLUE, MEMBER, NO_ROLE, discord, login, settings  # noqa: F401 (fixture)

import admin_console as console
from backend import admin_actions as actions
from backend import visibility

PAGES = (f"/api/players/{BLUE}", f"/api/players/{BLUE}/trends", f"/api/players/{BLUE}/companions", "/api/overview",
         "/api/leaderboard?min_games=1", "/api/leaderboard/stats")


def every(items, *keys):
    """Whether every item has the keys; None for an empty list (nothing to tell)."""
    return all(k in i for i in items for k in keys) if items else None


def has_win_loss(client) -> dict:
    """Per page: are the win-loss fields there (None: the page has no rows in this archive)."""
    player = client.get(PAGES[0]).json()
    companions = client.get(PAGES[2]).json()
    found = {
        "profile": every([player["stats"]], "wins", "losses"),
        "results": every(player["recent_matches"], "result"),
        "trends": every(client.get(PAGES[1]).json()["items"], "win_rate"),
        "companions": every(companions["teammates"] + companions["opponents"], "wins", "losses"),
        "overview": every(client.get(PAGES[3]).json()["top_this_week"], "wins"),
        "leaderboard": every(client.get(PAGES[4]).json()["items"], "wins", "losses", "win_rate"),
        "stat list": {"wins", "win_rate"} <= {s["key"] for s in client.get(PAGES[5]).json()},
        "team win rates": every([client.get(PAGES[3]).json()["global"]], "payload_attack_win_rate", "capture_wins"),
    }
    return {k: v for k, v in found.items() if v is not None}


def test_hidden_win_loss_only_for_admins(tmp_path, discord):  # noqa: F811
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.add_discord_role, "admin_user", MEMBER)
        shown = has_win_loss(client)
        assert len(shown) >= 7 and all(shown.values())

        act(client, actions.set_stats_hidden, "win_loss", True)
        visibility._memo.clear()  # the website re-reads the setting within 2 s
        assert not any(has_win_loss(client).values())
        assert client.get("/api/leaderboard", params={"stat": "win_rate"}).status_code == 404
        cmp = client.get(f"/api/players/compare/{BLUE},{BLUE}").json()
        assert all("wins" not in p["stats"] for p in cmp["players"])
        assert all(set(h) == {"games"} for h in cmp["head_to_head"].values())
        r = client.get(PAGES[0])
        assert "no-store" in r.headers["Cloudflare-CDN-Cache-Control"]  # per visitor while hidden

        login(client, NO_ROLE)  # logged in, but not an admin
        assert not any(has_win_loss(client).values())
        login(client, MEMBER)  # admin
        assert all(has_win_loss(client).values())
        assert client.get("/api/leaderboard", params={"stat": "win_rate"}).status_code == 200

        act(client, actions.set_stats_hidden, "win_loss", False)
        visibility._memo.clear()
        client.cookies.clear()
        assert all(has_win_loss(client).values())


def test_console_command(tmp_path, discord, capsys):  # noqa: F811
    with app_client(settings(tmp_path)) as client:
        sessions = client.app.state.sessionmaker
        assert console.cmd_hide_stats(sessions) == []
        assert console.cmd_hide_stats(sessions, hide="win_loss") == ["win_loss"]
        assert "HIDDEN" in capsys.readouterr().out
        assert console.cmd_hide_stats(sessions, show="win_loss") == []
        try:
            console.cmd_hide_stats(sessions, hide="nope")
        except console.ConsoleError as e:
            assert "not a stat group" in str(e)
        else:
            raise AssertionError("unknown group accepted")


def test_hidden_for_one_player(tmp_path, discord):  # noqa: F811
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.add_discord_role, "admin_user", MEMBER)
        other = next(p["user_id"] for p in client.get("/api/players").json()["items"] if p["user_id"] != BLUE)
        console.cmd_hide_stats(client.app.state.sessionmaker, hide="win_loss", player=BLUE)
        visibility._memo.clear()

        assert "wins" not in client.get(f"/api/players/{BLUE}").json()["stats"]
        assert "win_rate" not in client.get(f"/api/players/{BLUE}/trends").json()["items"][0]
        assert "wins" in client.get(f"/api/players/{other}").json()["stats"]  # only that player
        board = {r["user_id"]: r for r in client.get("/api/leaderboard?min_games=1").json()["items"]}
        assert board[BLUE]["wins"] is None and board[other]["wins"] is not None
        wins_board = [r["user_id"] for r in client.get("/api/leaderboard?stat=wins&min_games=1").json()["items"]]
        assert BLUE not in wins_board and other in wins_board
        cmp = client.get(f"/api/players/compare/{BLUE},{other}").json()  # either hidden: no record at all
        assert all("wins" not in p["stats"] for p in cmp["players"])

        login(client, MEMBER)  # admins still see it
        assert "wins" in client.get(f"/api/players/{BLUE}").json()["stats"]

        console.cmd_hide_stats(client.app.state.sessionmaker, show="win_loss", player=BLUE)
        visibility._memo.clear()
        client.cookies.clear()
        assert "wins" in client.get(f"/api/players/{BLUE}").json()["stats"]


def test_console_tools_and_audit_log(tmp_path, discord):  # noqa: F811
    """Dashboard facts, player tools and the audit log (Console page); console users only."""
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        for path in ("/api/admin/console/overview", "/api/admin/console/players?q=a", "/api/admin/console/log"):
            assert client.get(path).status_code == 403
        login(client, MEMBER)  # MEMBER has the console role (ECHOVR_DISCORD_PREVIEW_ROLES)

        found = client.get("/api/admin/console/players", params={"q": BLUE}).json()
        assert found[0]["user_id"] == BLUE and found[0]["win_loss_hidden"] is False and found[0]["games"] == 1

        r = client.post("/api/admin/console/hide-stats", json={"hide_win_loss": True, "player": BLUE},
                        headers={"X-EchoVR": "1"})
        assert r.status_code == 200 and r.json()["ok"], r.text
        assert client.get("/api/admin/console/players", params={"q": BLUE}).json()[0]["win_loss_hidden"] is True

        overview = client.get("/api/admin/console/overview").json()
        group = overview["stat_groups"][0]
        assert group["key"] == "win_loss" and group["hidden"] is False and group["players"][0]["user_id"] == BLUE
        assert overview["players"] >= 1

        log = client.get("/api/admin/console/log").json()
        assert log[0]["command"] == "hide-stats" and log[0]["source"] == "website" and log[0]["ok"]
        assert log[0]["args"] == {"hide_win_loss": True, "player": BLUE} and log[0]["who_id"] == MEMBER
        assert overview["recent"][0]["id"] == log[0]["id"]
        assert client.get("/api/admin/console/log", params={"q": "nothing-like-this"}).json() == []
