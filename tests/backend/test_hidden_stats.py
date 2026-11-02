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
