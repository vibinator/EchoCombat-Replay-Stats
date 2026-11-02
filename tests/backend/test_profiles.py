"""Discord-linked player profiles (user, 2026-11-02): the bot links, the linked person edits only bio + avatar."""

import httpx
import pytest
import replay_factory as rf
from app_helpers import add, app_client
from test_discord_preview import MEMBER, NO_ROLE, discord, login, settings  # noqa: F401 (fixture)

from backend import auth, guard
from backend.api.profiles import clean_bio

BLUE = str(rf.BIG_USER_ID)
SECRET = "bot-secret"
BOT = {"Authorization": f"Bearer {SECRET}"}
SITE = {"X-EchoVR": "1"}


@pytest.fixture
def avatars(monkeypatch, discord):  # noqa: F811
    """discord fixture plus /users/{id} answering an avatar hash."""
    inner = auth.http_client

    def handle(request: httpx.Request) -> httpx.Response:
        if "/users/" in request.url.path and not request.url.path.endswith("@me"):
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1], "avatar": "abc123"})
        with inner() as c:
            return c.send(request)

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    auth._avatars.clear()


def test_bot_links_and_owner_edits_only_bio_and_avatar(tmp_path, avatars):
    with app_client(settings(tmp_path, bot_link_secret=SECRET)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        assert client.get(f"/api/profiles/{BLUE}").json()["linked"] is False

        # the bot needs its secret
        assert client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": BLUE}).status_code == 401
        assert client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": BLUE},
                           headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.post("/api/bot/link", json={"discord_id": "12", "user_id": BLUE}, headers=BOT).status_code == 400
        assert client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": "nobody"}, headers=BOT).status_code == 404
        r = client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": BLUE}, headers=BOT).json()
        assert r["linked"] and r["user_id"] == BLUE and r["changed"]
        assert client.post("/api/bot/lookup", json={"discord_id": MEMBER}, headers=BOT).json()["user_id"] == BLUE

        # not logged in / someone else: refused
        assert client.post(f"/api/profiles/{BLUE}", json={"bio": "hi"}, headers=SITE).status_code == 401
        login(client, NO_ROLE)
        assert client.get(f"/api/profiles/{BLUE}").json()["editable"] is False
        assert client.post(f"/api/profiles/{BLUE}", json={"bio": "hi"}, headers=SITE).status_code == 403

        login(client, MEMBER)
        p = client.get(f"/api/profiles/{BLUE}").json()
        assert p["editable"] and p["avatar_url"] == f"https://cdn.discordapp.com/avatars/{MEMBER}/abc123.png?size=256"
        # without the site's header the write is refused (read-only website)
        assert client.post(f"/api/profiles/{BLUE}", json={"bio": "hi"}).status_code == 405
        # extra fields (e.g. a name) are ignored: only bio and avatar can change
        p = client.post(f"/api/profiles/{BLUE}", json={"bio": "  Hello\n\n\n\nworld\x00 ", "show_avatar": False,
                                                       "name": "Hacked"}, headers=SITE).json()
        assert p["bio"] == "Hello\n\nworld" and p["avatar_url"] is None and p["show_avatar"] is False
        assert client.get(f"/api/players/{BLUE}").json()["name"] != "Hacked"

        # relinking to another account moves the link; unlink removes it
        client.post("/api/bot/link", json={"discord_id": NO_ROLE, "user_id": BLUE}, headers=BOT)
        assert client.get(f"/api/profiles/{BLUE}").json()["editable"] is False
        assert client.post("/api/bot/unlink", json={"user_id": BLUE}, headers=BOT).json() == {"removed": True}
        assert client.get(f"/api/profiles/{BLUE}").json()["linked"] is False


def test_bot_linking_off_without_secret(tmp_path, avatars):
    with app_client(settings(tmp_path)) as client:
        assert client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": BLUE}, headers=BOT).status_code == 404


def test_bio_cleaning():
    assert clean_bio("") is None and clean_bio(None) is None
    assert clean_bio("a‮b\r\nc") == "ab\nc"  # bidi override removed
    assert len(clean_bio("x" * 2000)) == 500
    assert clean_bio("\n".join("abcdefghijk")).count("\n") == 7


def test_guard_lets_the_bot_through_but_not_scripts_elsewhere():
    class Req:
        def __init__(self, path, agent="python-httpx/0.27"):
            self.url = type("U", (), {"path": path})()
            self.headers = {"user-agent": agent}
            self.client = None
    assert guard.check(Req("/api/bot/link"), None) is None
    assert guard.check(Req("/api/players"), None).status_code == 403


M1, M2, M3, LINKED = "111111111111111111", "222222222222222222", "333333333333333333", "444444444444444444"


@pytest.fixture
def members(monkeypatch, avatars):
    """avatars fixture plus the server's member list (/guilds/{id}/members)."""
    from backend import discord_names
    inner = auth.http_client
    listed = [
        {"user": {"id": M1, "username": "someone", "global_name": "Player", "avatar": "aaa"}, "nick": None},
        {"user": {"id": M2, "username": "other", "avatar": "bbb"}},  # "Other" belongs to two members: no match
        {"user": {"id": M3, "username": "x", "global_name": "OTHER", "avatar": "ccc"}},
        {"user": {"id": LINKED, "username": "y", "avatar": "ddd"}, "nick": "Third"},
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/members"):
            return httpx.Response(200, json=listed if request.url.params["after"] == "0" else [])
        with inner() as c:
            return c.send(request)

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    discord_names.clear()
    yield discord_names
    discord_names.clear()


def test_discord_avatar_for_a_one_to_one_name_match(tmp_path, members):
    teams = [{"players": [rf.player(rf.BIG_USER_ID, "player")]}, {"players": [rf.player(42, "Other", 1)]}, {}]
    third = [{"players": [rf.player(77, "Third")]}, {"players": [rf.player(78, "Fourth", 1)]}, {}]
    with app_client(settings(tmp_path, bot_link_secret=SECRET)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=teams)),
                     "dyson/1.echoreplay": rf.plain(rf.lines(20, teams=third))})
        members._refresh(client.app.state.settings)
        p = client.get(f"/api/profiles/{BLUE}").json()  # "player" = M1's display name, case ignored
        assert p["linked"] is False and p["editable"] is False
        assert p["avatar_url"] == f"https://cdn.discordapp.com/avatars/{M1}/aaa.png?size=256"  # Discord's CDN
        assert client.get("/api/profiles/42").json()["avatar_url"] is None  # two members are "Other"
        assert client.get("/api/profiles/78").json()["avatar_url"] is None  # no member named "Fourth"

        # a member linked by the bot to another player is shown only there
        assert client.get("/api/profiles/77").json()["avatar_url"].endswith(f"/{LINKED}/ddd.png?size=256")
        client.post("/api/bot/link", json={"discord_id": LINKED, "user_id": "78"}, headers=BOT)
        assert client.get("/api/profiles/77").json()["avatar_url"] is None

        # a second player with the same name: not 1:1 any more
        dup = [{"players": [rf.player(555, "PLAYER")]}, {"players": [rf.player(556, "Sixth", 1)]}, {}]
        add(client, {"dyson/2.echoreplay": rf.plain(rf.lines(20, teams=dup))})
        assert client.get(f"/api/profiles/{BLUE}").json()["avatar_url"] is None


def test_names_of_members():
    from backend.discord_names import names_of
    got = names_of([
        {"user": {"id": M1, "username": "a", "global_name": "A", "avatar": "h1"}, "nick": "Nick"},
        {"user": {"id": M2, "username": "nick", "avatar": "h2"}},
        {"user": {"id": M3, "username": "noavatar", "avatar": None}},
        {"user": {"id": LINKED, "username": "bot", "avatar": "h3", "bot": True}},
    ])
    assert got == {"a": (M1, "h1")}  # "nick" is two members; no avatar and bots give nothing
