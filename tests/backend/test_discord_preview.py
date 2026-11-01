"""Discord login gives preview access to achievements before their launch date (D41). Discord is mocked."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend import auth

BLUE = str(rf.BIG_USER_ID)  # player in rf.plain
# real Discord ids are 17-20 digits (people's ids are checked before they go into a Discord API path)
ROLE, MEMBER, OUTSIDER, NO_ROLE = "555000000000000555", "420000000000000042", "430000000000000043", "440000000000000044"
DB_ROLE, DB_MEMBER = "123456789012345678", "450000000000000045"  # role set in the admin console
BROKEN = "460000000000000046"  # Discord refuses the bot token for this lookup
SOMEONE_ELSE = "470000000000000047"  # a valid id that is none of the people above


@pytest.fixture
def discord(monkeypatch):
    """Fake Discord: the OAuth code is the user id; MEMBER has the preview role, NO_ROLE is in the server
    without it, OUTSIDER is not in the server."""
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        if path.endswith("/oauth2/token"):
            code = parse_qs(request.content.decode())["code"][0]
            return httpx.Response(200, json={"access_token": f"token-{code}"}) if code != "bad" else httpx.Response(400)
        if path.endswith("/oauth2/token/revoke"):
            return httpx.Response(200)
        if path.endswith("/users/@me"):
            uid = request.headers["Authorization"].removeprefix("Bearer token-")
            return httpx.Response(200, json={"id": uid, "username": f"user{uid}", "global_name": None})
        if path.endswith("/roles"):
            return httpx.Response(200, json=[{"id": "779349159852769310", "name": "@everyone", "position": 0},
                                             {"id": DB_ROLE, "name": "Preview", "position": 2},
                                             {"id": "999", "name": "Member", "position": 1}])
        if "/members/" in path:
            assert request.headers["Authorization"] == "Bot bot-token"
            uid = path.rsplit("/", 1)[1]
            if uid == OUTSIDER:
                return httpx.Response(404)
            if uid == BROKEN:
                return httpx.Response(401, json={"message": "401: Unauthorized"})
            return httpx.Response(200, json={"roles": {MEMBER: [ROLE], DB_MEMBER: [DB_ROLE]}.get(uid, ["999"]),
                                             "user": {"id": uid, "username": f"user{uid}"}})
        return httpx.Response(404)

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    auth._roles.clear()
    return calls


def settings(tmp_path, **kw):
    values = dict(discord_client_secret="secret", discord_bot_token="bot-token", discord_preview_roles=(ROLE,),
                  public_url="http://testserver")
    return make_settings(tmp_path, **(values | kw))


def login(client, user_id: str) -> httpx.Response:
    start = client.get("/api/auth/login", params={"next": "/achievements"}, follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["scope"] == ["identify"] and query["redirect_uri"] == ["http://testserver/api/auth/callback"]
    return client.get("/api/auth/callback", params={"code": user_id, "state": query["state"][0]}, follow_redirects=False)


def test_preview_role_sees_achievements_before_launch(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.set_challenge_window, "2999-01-01", None)  # launch still to come
        assert client.get("/api/auth/me").json() == {"enabled": True, "user": None}
        assert client.get(f"/api/players/{BLUE}/achievements").status_code == 403

        done = login(client, MEMBER)
        assert done.status_code == 303 and done.headers["location"] == "/achievements"
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{MEMBER}", "preview": True, "admin": False,
                                                                    "console": True}
        assert client.get("/api/challenges").json()["preview"] is True
        a = client.get(f"/api/players/{BLUE}/achievements").json()
        assert a["games"] == 1 and a["window"] == {"start": None, "end": None}  # whole archive before launch
        assert client.get("/api/achievements").status_code == 200
        assert "achievements" in {s["key"] for s in client.get("/api/leaderboard/stats").json()}
        assert "no-store" in client.get("/api/achievements").headers["cache-control"]

        client.get("/api/auth/logout", follow_redirects=False)
        assert client.get("/api/auth/me").json()["user"] is None
        assert client.get("/api/achievements").status_code == 403


@pytest.mark.parametrize("user_id", [NO_ROLE, OUTSIDER])
def test_without_the_role_it_stays_coming_soon(tmp_path, discord, user_id):
    with app_client(settings(tmp_path)) as client:
        login(client, user_id)
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{user_id}", "preview": False, "admin": False,
                                                                    "console": False}
        assert client.get("/api/achievements").status_code == 403


def test_role_answer_is_remembered(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        for _ in range(3):
            client.get("/api/achievements")
        assert sum("/members/" in c.url.path for c in discord) == 1


def test_bad_state_code_or_cookie_is_refused(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        client.get("/api/auth/login", follow_redirects=False)
        r = client.get("/api/auth/callback", params={"code": MEMBER, "state": "forged"}, follow_redirects=False)
        assert r.headers["location"] == "/achievements?login=failed"
        assert login(client, "bad").headers["location"] == "/achievements?login=failed"
        assert client.get("/api/auth/me").json()["user"] is None
        client.cookies.set(auth.SESSION_COOKIE, "eyJpZCI6IjQyIn0.forged")
        assert client.get("/api/auth/me").json()["user"] is None


def test_next_never_leaves_the_site(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        for evil in ("https://evil.example", "//evil.example", "/\evil.example"):
            start = client.get("/api/auth/login", params={"next": evil}, follow_redirects=False)
            state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
            r = client.get("/api/auth/callback", params={"code": MEMBER, "state": state}, follow_redirects=False)
            assert r.headers["location"] == "/achievements"


def test_other_hostname_is_sent_to_the_public_address_first(tmp_path, discord):
    with app_client(settings(tmp_path, public_url="https://echocombat.com")) as client:
        r = client.get("https://www.echocombat.com/api/auth/login", params={"next": "/players"}, follow_redirects=False)
        assert r.headers["location"] == "https://echocombat.com/api/auth/login?next=%2Fplayers"
        r = client.get("https://echocombat.com/api/auth/login", follow_redirects=False)
        assert r.headers["location"].startswith(auth.AUTHORIZE_URL) and "secure" in r.headers["set-cookie"].lower()


def test_login_off_without_secrets(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        assert client.get("/api/auth/me").json() == {"enabled": False, "user": None}
        assert client.get("/api/auth/login", follow_redirects=False).status_code == 404


def test_compose_placeholders_keep_login_off(monkeypatch):
    from backend.config import Settings

    monkeypatch.setenv("ECHOVR_DISCORD_CLIENT_SECRET", "YOUR_DISCORD_CLIENT_SECRET")
    monkeypatch.setenv("ECHOVR_DISCORD_BOT_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
    monkeypatch.setenv("ECHOVR_DISCORD_PREVIEW_ROLES", "YOUR_PREVIEW_ROLE_ID")
    assert not auth.enabled(Settings.from_env())
    monkeypatch.setenv("ECHOVR_DISCORD_CLIENT_SECRET", "real")
    monkeypatch.setenv("ECHOVR_DISCORD_BOT_TOKEN", "real")
    monkeypatch.setenv("ECHOVR_DISCORD_PREVIEW_ROLES", "1, 2")
    s = Settings.from_env()
    assert auth.enabled(s) and s.discord_preview_roles == ("1", "2")


def test_preview_roles_from_the_admin_console(tmp_path, discord, capsys):
    import admin_console as console

    with app_client(settings(tmp_path, discord_preview_roles=())) as client:
        login(client, DB_MEMBER)
        assert client.get("/api/auth/me").json()["user"]["preview"] is False  # no role set yet
        sessions = console.open_sessions(client.app.state.settings)
        with pytest.raises(actions.AdminError, match="not a role in the Discord server"):
            console.cmd_discord_roles(sessions, client.app.state.settings, "preview", add="Preview")
        server = console.cmd_discord_roles(sessions, client.app.state.settings, "preview", show_server=True)
        assert [r["name"] for r in server] == ["Preview", "Member"]  # highest first, no @everyone
        console.cmd_discord_roles(sessions, client.app.state.settings, "preview", add=DB_ROLE)
        assert "Preview" in capsys.readouterr().out
        assert client.get("/api/auth/me").json()["user"]["preview"] is True  # applies at once (roles cached, not the answer)
        console.cmd_discord_roles(sessions, client.app.state.settings, "preview", remove=DB_ROLE)
        assert client.get("/api/auth/me").json()["user"]["preview"] is False
        with pytest.raises(actions.AdminError, match="not a preview role"):
            console.cmd_discord_roles(sessions, client.app.state.settings, "preview", remove=DB_ROLE)


def test_admin_role_gets_status_not_the_old_admin_tab(tmp_path, discord):
    import admin_console as console

    with app_client(settings(tmp_path)) as client:
        login(client, DB_MEMBER)
        assert client.get("/api/admin/status").status_code == 403
        sessions = console.open_sessions(client.app.state.settings)
        console.cmd_discord_roles(sessions, client.app.state.settings, "admin", add=DB_ROLE)
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{DB_MEMBER}", "preview": True, "admin": True,
                                                                       "console": False}
        assert client.get("/api/admin/status").status_code == 200
        for gone in ("/api/admin/achievements", "/api/admin/achievements.xlsx"):  # Admin tab removed
            assert client.get(gone).status_code == 404
        assert client.get("/api/admin/icons").status_code == 403  # icons: console users only

        # a preview role is not an admin role
        console.cmd_discord_roles(sessions, client.app.state.settings, "admin", remove=DB_ROLE)
        console.cmd_discord_roles(sessions, client.app.state.settings, "preview", add=DB_ROLE)
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        assert client.get("/api/admin/status").status_code == 403


def _png(width=64, height=64) -> bytes:
    import struct
    import zlib

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_console_changes_achievement_icons(tmp_path, discord):
    headers = {"X-EchoVR": "1"}
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        login(client, NO_ROLE)
        # no console access: refused (and without the header the site stays read-only)
        assert client.put("/api/admin/achievements/5/icon", json={"icon": "nova.png"}, headers=headers).status_code == 403
        login(client, MEMBER)
        assert client.put("/api/admin/achievements/5/icon", json={"icon": "nova.png"}).status_code == 405

        choices = client.get("/api/admin/icons").json()
        assert "nova.png" in choices and "gold.png" not in choices  # tier frames are not icons
        assert client.put("/api/admin/achievements/5/icon", json={"icon": "nova.png"}, headers=headers).json()["icon"] == "nova.png"
        assert client.put("/api/admin/achievements/5/icon", json={"icon": "../secret.png"}, headers=headers).status_code == 400
        assert client.put("/api/admin/achievements/999/icon", json={"icon": "nova.png"}, headers=headers).status_code == 400

        def icon_everywhere(rule_id):
            player = {a["id"]: a["icon"] for a in client.get(f"/api/players/{BLUE}/achievements").json()["items"]}
            catalogue = {a["id"]: a["icon"] for a in client.get("/api/achievements").json()}
            export = {a["id"]: a["icon"] for a in client.get("/api/admin/console/achievements").json()}
            assert player[rule_id] == catalogue[rule_id] == export[rule_id]
            return player[rule_id]

        assert icon_everywhere(5) == "nova.png"

        bad = client.post("/api/admin/achievements/5/icon", content=b"GIF89a....", headers=headers)
        assert bad.status_code == 400 and "PNG" in bad.json()["message"]
        assert client.post("/api/admin/achievements/5/icon", content=_png(4096, 16), headers=headers).status_code == 400
        up = client.post("/api/admin/achievements/5/icon", content=_png(), headers=headers | {"Content-Type": "image/png"})
        icon = up.json()["icon"]
        assert icon.startswith("custom/") and icon_everywhere(5) == icon
        served = client.get(f"/achievements/{icon}")
        assert served.status_code == 200 and served.headers["content-type"] == "image/png"
        key = (client.app.state.settings.data_dir / "session.key").read_bytes()
        for evil in ("..%2Fsession.key", "%2e%2e/session.key", "../session.key"):
            r = client.get(f"/achievements/custom/{evil}")  # the site's page (or 404), never the file
            assert key not in r.content and r.headers.get("content-type") != "image/png"
        assert icon in client.get("/api/admin/icons").json()

        assert client.put("/api/admin/achievements/5/icon", json={"icon": None}, headers=headers).json()["icon"] == "pulsar_daily.png"
        assert icon_everywhere(5) == "pulsar_daily.png"


def test_discord_check_explains_access(tmp_path, discord, capsys):
    import admin_console as console

    with app_client(settings(tmp_path)) as client:
        st = client.app.state.settings
        sessions = console.open_sessions(st)
        assert console.cmd_discord_check(sessions, st, OUTSIDER) == {"member": False, "admin": False, "preview": False,
                                                                         "console": False}
        assert console.cmd_discord_check(sessions, st, DB_MEMBER) == {"member": True, "admin": False, "preview": False,
                                                                          "console": False}
        out = capsys.readouterr().out
        assert "  Admin         no\n  Preview       no\n  Console page  no" in out
        assert "Member" not in out and "999" not in out  # permissions only, not the person's Discord roles
        yaml_user = console.cmd_discord_check(sessions, st.__class__(**(st.__dict__ | {"discord_preview_roles": (OUTSIDER,)})), OUTSIDER)
        assert yaml_user == {"member": False, "admin": False, "preview": True, "console": True}  # user id in the YAML
        console.cmd_discord_roles(sessions, st, "admin", add=DB_ROLE)
        assert console.cmd_discord_check(sessions, st, DB_MEMBER) == {"member": True, "admin": True, "preview": True,
                                                                          "console": False}
        with pytest.raises(console.ConsoleError, match="refused the bot token"):
            console.cmd_discord_check(sessions, st, BROKEN)
        with pytest.raises(console.ConsoleError, match="bot token is not set"):
            console.cmd_discord_check(sessions, make_settings(tmp_path), DB_MEMBER)  # no bot token


def test_new_login_rechecks_roles(tmp_path, discord):
    import admin_console as console

    with app_client(settings(tmp_path)) as client:
        login(client, DB_MEMBER)
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        sessions = console.open_sessions(client.app.state.settings)
        console.cmd_discord_roles(sessions, client.app.state.settings, "admin", add=DB_ROLE)
        assert client.get("/api/auth/me").json()["user"]["admin"] is True  # role ids from the console apply at once
        calls = sum("/members/" in c.url.path for c in discord)
        login(client, DB_MEMBER)
        client.get("/api/auth/me")
        assert sum("/members/" in c.url.path for c in discord) == calls + 1  # a fresh login asks Discord again


def test_admin_users_by_discord_id(tmp_path, discord):
    import admin_console as console

    with app_client(settings(tmp_path)) as client:
        st = client.app.state.settings
        sessions = console.open_sessions(st)
        # a person's id is refused as a role, and a role is refused as a person
        with pytest.raises(console.ConsoleError, match="not a role in the Discord server"):
            console.cmd_discord_roles(sessions, st, "admin", add="463399156866875402")
        with pytest.raises(console.ConsoleError, match="is a role, not a person"):
            console.cmd_admin_users(sessions, st, add=DB_ROLE)

        login(client, NO_ROLE)  # in the server, no useful role
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        assert console.cmd_admin_users(sessions, st, add=SOMEONE_ELSE) == [SOMEONE_ELSE]
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        console.cmd_admin_users(sessions, st, remove=SOMEONE_ELSE)

    (tmp_path / "b").mkdir()
    with app_client(settings(tmp_path / "b")) as client:
        st = client.app.state.settings
        sessions = console.open_sessions(st)
        uid = "463399156866875402"
        console.cmd_admin_users(sessions, st, add=uid)
        login(client, uid)  # not in the server at all: a named admin needs no role
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{uid}", "preview": True, "admin": True,
                                                                "console": False}
        assert client.get("/api/admin/status").status_code == 200
        console.cmd_admin_users(sessions, st, remove=uid)
        assert client.get("/api/auth/me").json()["user"]["admin"] is False


CONSOLE = {"X-EchoVR": "1"}


def test_console_page_for_yaml_preview_roles_only(tmp_path, discord):
    """D45: admin.bat on the website, only for roles from ECHOVR_DISCORD_PREVIEW_ROLES (not the console's own)."""
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 403  # logged out
        act(client, actions.add_discord_role, "preview", DB_ROLE)
        login(client, DB_MEMBER)  # preview from the admin console: preview, but no Console page
        assert client.get("/api/auth/me").json()["user"]["console"] is False
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 403

        login(client, MEMBER)  # role from ECHOVR_DISCORD_PREVIEW_ROLES
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{MEMBER}", "preview": True, "admin": False,
                                                            "console": True}
        assert client.post("/api/admin/console/status", json={}).status_code == 405  # no X-EchoVR: read-only
        r = client.post("/api/admin/console/status", json={}, headers=CONSOLE).json()
        assert r["ok"] and "Replays: done 1" in r["output"]
        r = client.post("/api/admin/console/challenge", json={"start": "2026-01-01"}, headers=CONSOLE).json()
        assert r["ok"] and "2026-01-01 → open-ended" in r["output"]
        assert client.get("/api/challenges").json()["start"] == "2026-01-01"
        r = client.post("/api/admin/console/challenge", json={"start": "nope"}, headers=CONSOLE).json()
        assert not r["ok"] and "is not a date" in r["output"]
        r = client.post("/api/admin/console/find", json={"term": ""}, headers=CONSOLE).json()
        assert not r["ok"] and "Enter a name or id" in r["output"]
        assert client.post("/api/admin/console/nope", json={}, headers=CONSOLE).status_code == 404
        assert client.post("/api/admin/console/admin-users", json={}, headers=CONSOLE).status_code == 404  # Permissions page


def test_console_page_for_a_user_id_in_the_yaml(tmp_path, discord):
    """A person's own Discord id in ECHOVR_DISCORD_PREVIEW_ROLES works too (D44: one was put there)."""
    with app_client(settings(tmp_path, discord_preview_roles=(NO_ROLE,))) as client:
        login(client, NO_ROLE)
        assert client.get("/api/auth/me").json()["user"]["console"] is True
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).json()["ok"]
        login(client, MEMBER)
        assert client.get("/api/auth/me").json()["user"]["console"] is False


def test_after_the_launch_no_login_is_needed(tmp_path, discord):
    """From the start date on achievements are public (D40): Discord login is on, but nobody has to use it."""
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.set_challenge_window, "2026-01-01", None)  # launched
        assert client.get("/api/auth/me").json() == {"enabled": True, "user": None}
        challenges = client.get("/api/challenges").json()
        assert challenges["launched"] is True and challenges["preview"] is False
        assert client.get("/api/achievements").status_code == 200
        assert client.get(f"/api/players/{BLUE}/achievements").json()["window"]["start"] == "2026-01-01"
        assert "achievements" in {s["key"] for s in client.get("/api/leaderboard/stats").json()}
        assert not any("/members/" in c.url.path for c in discord)  # Discord never asked


def test_console_refuses_everyone_without_access(tmp_path, discord, monkeypatch):
    """D45: the server checks every command; a role taken away stops working at once (no 5-minute memory)."""
    with app_client(settings(tmp_path)) as client:
        for method in ("get", "put", "delete"):  # only POST runs a command
            assert getattr(client, method)("/api/admin/console/status", headers=CONSOLE).status_code in (404, 405)
        login(client, MEMBER)
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 200
        assert client.post("/api/admin/console/status", json={}, headers={"X-EchoVR": "0"}).status_code == 405
        client.cookies.clear()
        client.cookies.set(auth.SESSION_COOKIE, "eyJpZCI6IjQyIn0.forged")  # MEMBER's id, unsigned
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 403

        client.cookies.clear()
        login(client, MEMBER)
        assert client.get("/api/auth/me").json()["user"]["console"] is True  # remembered for the menu
        real = auth.http_client
        monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"roles": ["999"]}))))  # role taken away in Discord
        r = client.post("/api/admin/console/status", json={}, headers=CONSOLE)
        assert r.status_code == 403 and "ECHOVR" not in r.json()["message"]
        monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(503))))  # Discord cannot be asked: refused, not the remembered answer
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 403
        monkeypatch.setattr(auth, "http_client", real)
        assert client.post("/api/admin/console/status", json={}, headers=CONSOLE).status_code == 200


def test_console_output_uses_the_page_names(tmp_path, discord):
    from pathlib import Path

    from backend.api import console as page

    source = (Path(__file__).parents[2] / "app" / "admin_console.py").read_text(encoding="utf-8")
    for old, _ in page.WEB_WORDING:
        assert old in source, f"admin_console.py no longer says {old!r}: update WEB_WORDING"
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        login(client, MEMBER)
        out = client.post("/api/admin/console/status", json={}, headers=CONSOLE).json()["output"]
        assert out.startswith("Server: running\n") and "http://" not in out
        out = client.post("/api/admin/console/challenge", json={"start": "2026-01-01"}, headers=CONSOLE).json()["output"]
        assert "2026-01-01 → open-ended" in out
        out = client.post("/api/admin/console/repair-failed", json={}, headers=CONSOLE).json()["output"]
        assert "'" not in out.replace("don't", "")  # no console command names


def test_console_exports_achievement_names_and_rules(tmp_path, discord):
    import csv
    import io

    from backend.achievements import RULES

    with app_client(settings(tmp_path)) as client:
        for url in ("/api/admin/console/achievements", "/api/admin/console/achievements.csv"):
            assert client.get(url).status_code == 403  # logged out
        login(client, NO_ROLE)
        assert client.get("/api/admin/console/achievements").status_code == 403  # no console access

        login(client, MEMBER)
        items = client.get("/api/admin/console/achievements").json()
        assert len(items) == len(RULES) and set(items[0]) == {"id", "name", "rule", "icon", "default_icon"}
        assert items[0]["name"] == RULES[0].name and items[0]["rule"] == RULES[0].description
        assert items[0]["icon"] == items[0]["default_icon"]
        estimated = next(r for r in RULES if r.estimated)
        assert next(i for i in items if i["id"] == estimated.id)["rule"] == estimated.description + " (deaths are estimated)"
        r = client.get("/api/admin/console/achievements.csv")
        assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        assert rows[0] == ["Name", "How to win it"] and rows[1:] == [[i["name"], i["rule"]] for i in items]
        assert "no-store" in r.headers["cache-control"]


def test_console_users_change_icons(tmp_path, discord):
    """Icons can be changed from the console export too (console access, not only admins), and set back."""
    with app_client(settings(tmp_path)) as client:
        icon = "/api/admin/achievements/5/icon"
        login(client, NO_ROLE)  # neither admin nor console
        assert client.get("/api/admin/icons").status_code == 403
        assert client.put(icon, json={"icon": "nova.png"}, headers=CONSOLE).status_code == 403
        assert client.post(icon, content=b"x", headers=CONSOLE | {"Content-Type": "image/png"}).status_code == 403

        login(client, MEMBER)  # console, not admin
        assert client.get("/api/auth/me").json()["user"]["admin"] is False
        assert "nova.png" in client.get("/api/admin/icons").json()
        default = next(i for i in client.get("/api/admin/console/achievements").json() if i["id"] == 5)["default_icon"]
        assert client.put(icon, json={"icon": "nova.png"}, headers=CONSOLE).json()["icon"] == "nova.png"
        assert next(i for i in client.get("/api/admin/console/achievements").json() if i["id"] == 5)["icon"] == "nova.png"
        assert client.put(icon, json={"icon": None}, headers=CONSOLE).json()["icon"] == default  # back to the original
        assert client.put(icon, json={"icon": "nova.png"}).status_code == 405  # no X-EchoVR: read-only


PERMS = "/api/admin/permissions"


def test_permissions_page(tmp_path, discord):
    """Console users give / take away Admin, Console and Preview by role or user id; the YAML ids are fixed."""
    with app_client(settings(tmp_path)) as client:
        assert client.get(PERMS).status_code == 403  # logged out
        login(client, NO_ROLE)
        assert client.get(PERMS).status_code == 403
        assert client.post(PERMS, json={"permission": "admin", "type": "user", "id": NO_ROLE}, headers=CONSOLE).status_code == 403

        login(client, MEMBER)  # console via the YAML role
        state = client.get(PERMS).json()
        assert state["fixed"] == [{"id": ROLE, "name": "?", "type": "user"}]  # 555 is not a role in the fake server
        assert {r["name"] for r in state["server_roles"]} == {"Preview", "Member"}
        assert client.post(PERMS, json={"permission": "admin", "type": "user", "id": "123456789012345679"}).status_code == 405

        def change(**kw):
            return client.post(PERMS, json=kw, headers=CONSOLE)

        # by role: everyone with "Member" (999) gets the preview -> NO_ROLE (who has 999) sees it
        assert change(permission="preview", type="role", id="999").status_code == 400  # ids are 17-20 digits
        state = change(permission="preview", type="role", id=DB_ROLE).json()
        assert state["permissions"]["preview"]["roles"] == [{"id": DB_ROLE, "name": "Preview"}]
        # by user id: a person, not a role, and the other way round
        assert "is a role" in change(permission="admin", type="user", id=DB_ROLE).json()["message"]
        assert "not a role" in change(permission="admin", type="role", id="123456789012345679").json()["message"]
        uid = "123456789012345679"
        state = change(permission="console", type="user", id=uid).json()
        assert state["permissions"]["console"]["users"] == [{"id": uid, "name": "?"}]  # the fake bot has no /users
        # the YAML ids cannot be removed here
        assert change(permission="console", type="role", id=ROLE, remove=True).json()["error_code"] == "fixed"
        state = change(permission="console", type="user", id=uid, remove=True).json()
        assert state["permissions"]["console"]["users"] == []
        assert change(permission="nope", type="role", id=DB_ROLE).status_code == 400


def test_permissions_give_access(tmp_path, discord):
    """Each permission works by user id and by role, straight away (no restart)."""
    with app_client(settings(tmp_path, discord_preview_roles=(MEMBER,))) as client:
        login(client, MEMBER)  # console by user id in the YAML

        def change(**kw):
            client.cookies.clear()
            login(client, MEMBER)
            assert client.post(PERMS, json=kw, headers=CONSOLE).status_code == 200

        def me(user_id):
            client.cookies.clear()
            login(client, user_id)
            u = client.get("/api/auth/me").json()["user"]
            return {k for k in ("admin", "console", "preview") if u[k]}

        assert me(DB_MEMBER) == set()
        change(permission="preview", type="role", id=DB_ROLE)
        assert me(DB_MEMBER) == {"preview"}
        person = "123456789012345670"  # in the server with only the Member role
        assert me(person) == set()
        change(permission="admin", type="user", id=person)
        assert me(person) == {"admin", "preview"}
        change(permission="console", type="user", id=person)
        assert me(person) == {"admin", "console", "preview"}
        assert client.get(PERMS).status_code == 200  # a console user given on the page can use it too
        change(permission="console", type="user", id=person, remove=True)
        client.cookies.clear()
        login(client, person)
        assert client.get(PERMS).status_code == 403  # taken away: refused at once


def test_status_page_for_admins_and_console_users(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        assert client.get("/api/admin/status").status_code == 403  # logged out
        login(client, NO_ROLE)
        assert client.get("/api/admin/status").status_code == 403
        login(client, MEMBER)  # console
        d = client.get("/api/admin/status").json()
        assert d["counts"]["done"] == 1 and {s["key"] for s in d["stages"]} >= {"replays", "tracks", "heatmaps", "achievements"}
        assert set(d["achievement_ranking"]) == {"calculating", "calculated", "up_to_date", "age_s"}
        assert "no-store" in client.get("/api/admin/status").headers["cache-control"]
        act(client, actions.add_discord_role, "admin", DB_ROLE)
        client.cookies.clear()
        login(client, DB_MEMBER)  # admin, not console
        assert client.get("/api/admin/status").status_code == 200
