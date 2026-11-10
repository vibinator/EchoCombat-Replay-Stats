"""Discord pictures with the least Discord permission (user, 2026-11-10): the member list (needs the Server Members intent)
is asked once and a refusal is not repeated; one-by-one picture lookups are kept 24 h and survive a restart."""

import logging
import time

import httpx
import pytest
from app_helpers import make_settings

from backend import auth, discord_names

USER = "111111111111111111"


@pytest.fixture
def fake_discord(monkeypatch):
    calls = []
    answer = {"members": httpx.Response(403, json={"message": "Missing Access"})}

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/members"):
            return answer["members"]
        if "/users/" in request.url.path:
            return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1], "avatar": "abc123"})
        return httpx.Response(404)

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    discord_names.clear()
    auth._avatars.clear()
    auth._avatars_loaded.clear()
    with auth._avatar_lock:
        auth._avatar_calls.clear()
    yield calls, answer
    discord_names.clear()
    auth._avatars.clear()
    auth._avatars_loaded.clear()


def settings(tmp_path, **kw):
    return make_settings(tmp_path, discord_bot_token="bot-token", **kw)


def test_member_list_refusal_is_logged_once_and_not_asked_again(tmp_path, fake_discord, caplog):
    calls, _ = fake_discord
    s = settings(tmp_path)
    with caplog.at_level(logging.WARNING):
        discord_names._refresh(s)  # what refresh_soon runs in the background
        for _ in range(5):
            discord_names.refresh_soon(s)
    assert sum(p.endswith("/members") for p in calls) == 1
    assert sum("Server Members intent" in r.getMessage() for r in caplog.records) == 1
    assert discord_names._refused[0] is True


def test_other_failures_are_retried(tmp_path, fake_discord):
    calls, answer = fake_discord
    answer["members"] = httpx.Response(500)
    s = settings(tmp_path)
    discord_names._refresh(s)
    assert discord_names._refused[0] is False and discord_names._next_refresh < float("inf")  # retried after RETRY_S


def test_name_pictures_off_never_asks_for_the_member_list(tmp_path, fake_discord):
    calls, _ = fake_discord
    s = settings(tmp_path, discord_name_pictures=False)
    discord_names.refresh_soon(s)
    time.sleep(0.2)
    assert not any(p.endswith("/members") for p in calls)
    # pictures of known Discord ids still come, one by one (no privileged intent needed)
    assert auth.avatar_url(s, USER) == f"https://cdn.discordapp.com/avatars/{USER}/abc123.png?size=256"


def test_picture_lookups_are_kept_a_day_and_survive_a_restart(tmp_path, fake_discord):
    calls, _ = fake_discord
    s = settings(tmp_path)
    url = auth.avatar_url(s, USER)
    assert url.endswith("/abc123.png?size=256") and calls.count(f"/api/v10/users/{USER}") == 1
    assert (tmp_path / "data" / auth.AVATAR_FILE).is_file()
    until = auth._avatars[USER][0]
    assert until - time.time() > 23 * 3600  # a day, not an hour

    auth._avatars.clear()  # a restart: memory empty, the file is still there
    auth._avatars_loaded.clear()
    assert auth.avatar_url(s, USER) == url
    assert calls.count(f"/api/v10/users/{USER}") == 1  # no new Discord request

    assert auth.avatar_url(s, USER, fresh=True) == url  # a profile save still asks at once
    assert calls.count(f"/api/v10/users/{USER}") == 2


def test_a_damaged_cache_file_is_ignored(tmp_path, fake_discord):
    calls, _ = fake_discord
    s = settings(tmp_path)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / auth.AVATAR_FILE).write_text('{"avatars": {"../x": [9e99, "a"], "' + USER + '": [9e99, "../evil"]}')
    assert auth.avatar_url(s, USER).endswith("/abc123.png?size=256")  # bad entries dropped, asked from Discord instead
    assert "../x" not in auth._avatars


def test_lists_never_ask_discord_only_a_profile_page_does(tmp_path, fake_discord):
    """User, 2026-11-10: a picture is fetched only when that player's profile page is opened; lists show saved ones."""
    import replay_factory as rf
    from app_helpers import add, app_client

    calls, _ = fake_discord
    site = {"X-EchoVR": "1"}
    with app_client(settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=[{"players": [rf.player(int(USER), "Someone")]},
                                                                         {"players": [rf.player(42, "Other", 1)]}, {}]))})
        assert client.get("/api/avatars", params={"ids": USER}, headers=site).json() == {}  # nobody opened the profile yet
        assert not calls  # no Discord request from a list, not even the member list
        assert "max-age=300" in client.get("/api/avatars", params={"ids": USER}, headers=site).headers["cache-control"]

        profile = client.get(f"/api/profiles/{USER}", headers=site).json()  # someone opens the player's page
        assert profile["avatar_url"].endswith(f"/{USER}/abc123.png?size=256")
        assert calls.count(f"/api/v10/users/{USER}") == 1

        before = len(calls)
        got = client.get("/api/avatars", params={"ids": USER}, headers=site).json()
        assert got[USER].endswith(f"/{USER}/abc123.png?size=256")  # the list now shows it
        auth._avatars[USER] = (time.time() - 10, auth._avatars[USER][1])  # older than a day
        assert client.get("/api/avatars", params={"ids": USER}, headers=site).json() == got  # still shown, not asked
        assert len(calls) == before
