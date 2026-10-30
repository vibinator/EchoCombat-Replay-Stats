"""Discord login gives preview access to achievements before their launch date (D41). Discord is mocked."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend import auth

BLUE = str(rf.BIG_USER_ID)  # player in rf.plain
ROLE, MEMBER, OUTSIDER, NO_ROLE = "555", "42", "43", "44"


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
        if "/members/" in path:
            assert request.headers["Authorization"] == "Bot bot-token"
            uid = path.rsplit("/", 1)[1]
            if uid == OUTSIDER:
                return httpx.Response(404)
            return httpx.Response(200, json={"roles": [ROLE] if uid == MEMBER else ["999"]})
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
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{MEMBER}", "preview": True}
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
        assert client.get("/api/auth/me").json()["user"] == {"name": f"user{user_id}", "preview": False}
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
