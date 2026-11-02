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
