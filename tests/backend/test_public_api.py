"""The public player-stats API (/api/v1, user 2026-11-27): API keys from the admin console, profile stats only."""

import replay_factory as rf
from app_helpers import add, app_client, make_settings
from sqlalchemy import select

import admin_console as console
from backend import api_keys
from backend.models import ConsoleLog

SCRIPT = {"User-Agent": "python-requests/2.32"}  # a script, no X-EchoVR header: what the API is for
BROWSER = {"User-Agent": "Mozilla/5.0 Chrome/140.0", "X-EchoVR": "1"}


def guarded(tmp_path, **overrides):
    return app_client(make_settings(tmp_path, scraper_guard=True, **overrides))


def new_key(client, name="Stats bot") -> tuple[str, str]:
    with client.app.state.sessionmaker() as db:
        return api_keys.create(db, name, "test")


def test_player_stats_with_a_key(tmp_path):
    with guarded(tmp_path) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
        player = client.get("/api/players", headers=BROWSER).json()["items"][0]
        key_id, key = new_key(client)

        found = client.get("/api/v1/players", params={"q": player["name"][:3]}, headers=SCRIPT | {"Authorization": f"Bearer {key}"})
        assert found.status_code == 200
        assert found.json()["items"][0] == {k: player[k] for k in ("user_id", "name", "games", "hours_played", "last_seen_at")}

        for how in ({"headers": SCRIPT | {"Authorization": f"Bearer {key}"}}, {"headers": SCRIPT | {"X-API-Key": key}},
                    {"headers": SCRIPT, "params": {"key": key}}):
            r = client.get(f"/api/v1/players/{player['user_id']}", **how)
            assert r.status_code == 200, how
            body = r.json()
            assert body["user_id"] == player["user_id"] and body["stats"]["games"] == player["games"]
            # profile stats only: no match list, heatmaps, loadouts, pings or the top-speed match
            assert set(body) == {"user_id", "name", "level", "first_seen_at", "last_seen_at", "period", "map", "stats"}
            assert not {"avg_ping", "avg_packet_loss", "top_speed_match", "in_bounds_frames"} & set(body["stats"])
            # never kept by Cloudflare or a browser: a revoked key stops at once
            assert r.headers["cache-control"] == "private, no-store"

        with client.app.state.sessionmaker() as db:
            assert api_keys.listing(db)[0]["last_used_at"] is not None
        assert client.get("/api/v1/players/nobody", headers=SCRIPT | {"X-API-Key": key}).status_code == 404


def test_no_key_wrong_key_revoked_key(tmp_path):
    with guarded(tmp_path) as client:
        assert client.get("/api/v1/players", headers=SCRIPT).json()["error_code"] == "api_key_missing"
        key_id, key = new_key(client)
        wrong = key[:-4] + ("aaaa" if not key.endswith("aaaa") else "bbbb")
        assert client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": wrong}).json()["error_code"] == "bad_api_key"
        assert client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": "ecs_nonsense"}).status_code == 401
        assert client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": key}).status_code == 200
        with client.app.state.sessionmaker() as db:
            assert api_keys.revoke(db, key_id)["name"] == "Stats bot"
            assert api_keys.revoke(db, key_id) is None
        assert client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": key}).json()["error_code"] == "bad_api_key"
        # the site's own API still refuses scripts
        assert client.get("/api/players", headers=SCRIPT).status_code == 403


def test_limit_per_key(tmp_path, monkeypatch):
    monkeypatch.setattr(api_keys, "minute", api_keys.RateLimiter(2, 2))
    with guarded(tmp_path, rate_limit_per_min=0, rate_limit_per_hour=0) as client:
        _, key = new_key(client)
        _, other = new_key(client, "Other bot")
        codes = [client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": key}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert client.get("/api/v1/players", headers=SCRIPT | {"X-API-Key": other}).status_code == 200


def test_listed_as_json_without_a_key(tmp_path):
    with guarded(tmp_path) as client:
        schema = client.get("/api/v1/openapi.json", headers=SCRIPT).json()
        assert set(schema["paths"]) == {"/api/v1/players", "/api/v1/players/{user_id}"}
        assert "bearer" in schema["components"]["securitySchemes"]
        assert client.get("/openapi.json").status_code != 200 or "paths" not in client.get("/openapi.json").text


def test_hidden_win_loss_stays_hidden(tmp_path):
    with guarded(tmp_path) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
        user_id = client.get("/api/players", headers=BROWSER).json()["items"][0]["user_id"]
        _, key = new_key(client)
        assert "wins" in client.get(f"/api/v1/players/{user_id}", headers=SCRIPT | {"X-API-Key": key}).json()["stats"]
        console.cmd_hide_stats(client.app.state.sessionmaker, "win_loss", None, "")
        import time
        time.sleep(2.1)  # visibility.TTL_S
        stats = client.get(f"/api/v1/players/{user_id}", headers=SCRIPT | {"X-API-Key": key}).json()["stats"]
        assert "wins" not in stats and "losses" not in stats and "games" in stats


def test_console_commands_show_the_key_once(tmp_path, capsys):
    with app_client(make_settings(tmp_path)) as client:
        sessions, settings = client.app.state.sessionmaker, client.app.state.settings
        key = console.cmd_api_key_add(sessions, settings, "League bot")
        out = capsys.readouterr().out
        assert key in out and f"/api/v1/players/<player id>?key={key}" in out
        console.cmd_api_keys(sessions)
        listed = capsys.readouterr().out
        assert "League bot" in listed and key not in listed
        # the audit log never keeps a key
        from backend import admin_actions as actions
        with sessions() as db:
            actions.log_command(db, "admin.bat", "tester", "api-key-add", {"name": "League bot"}, True, out)
            logged = db.scalars(select(ConsoleLog)).all()[-1].output
        assert key not in logged and key[:13] in logged
        key_id = key.split("_")[1]
        console.cmd_api_key_revoke(sessions, key_id)
        assert "revoked" in capsys.readouterr().out
