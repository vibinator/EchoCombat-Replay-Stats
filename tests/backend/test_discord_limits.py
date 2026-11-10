"""One limiter for every Discord request (user, 2026-11-10): far below Discord's 50/s per bot, a 429 pauses everything,
and many refusals stop all requests before Discord would block the IP address."""

import time

import httpx
import pytest
from app_helpers import make_settings

from backend import auth

USER = "111111111111111111"


@pytest.fixture
def discord(monkeypatch):
    calls = []
    answer = {"status": 200, "headers": {}}

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append((time.monotonic(), request.url.path))
        if answer["status"] != 200:
            return httpx.Response(answer["status"], headers=answer["headers"], json={"message": "x", "retry_after": 3})
        if request.url.path.endswith("/roles"):
            return httpx.Response(200, json=[{"id": "123456789012345678", "name": "Staff", "position": 1}])
        return httpx.Response(200, json={"id": USER, "avatar": "abc", "roles": []})

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    return calls, answer


def settings(tmp_path):
    return make_settings(tmp_path, discord_bot_token="bot-token")


def test_never_more_than_the_sites_own_rate(tmp_path, discord, monkeypatch):
    calls, _ = discord
    monkeypatch.setattr(auth, "DISCORD_WAIT_S", 30.0)
    s = settings(tmp_path)
    start = time.monotonic()
    for _ in range(auth.DISCORD_BURST + 10):
        auth._bot_get(s, f"/users/{USER}")
    took = time.monotonic() - start
    # the burst goes at once, the next 10 at DISCORD_PER_S: about 2 s, never faster
    assert took >= 10 / auth.DISCORD_PER_S - 0.2
    times = [t for t, _ in calls]
    for i in range(len(times)):  # in any one second: at most burst + rate requests (Discord allows 50)
        assert sum(1 for t in times if times[i] <= t < times[i] + 1) <= auth.DISCORD_BURST + auth.DISCORD_PER_S + 1
    assert auth.DISCORD_PER_S <= 50 / 10  # a tenth of Discord's per-bot limit at most


def test_a_request_never_waits_long_it_fails_like_an_unreachable_discord(tmp_path, discord, monkeypatch):
    calls, _ = discord
    monkeypatch.setattr(auth, "DISCORD_WAIT_S", 0.05)
    s = settings(tmp_path)
    for _ in range(auth.DISCORD_BURST):
        auth._bot_get(s, f"/users/{USER}")
    with pytest.raises(auth.DiscordPaused):
        auth._bot_get(s, f"/users/{USER}")
    assert len(calls) == auth.DISCORD_BURST
    # callers already treat it as "Discord unreachable": the role check keeps its last answer instead of failing
    assert auth.member_roles(s, USER) == frozenset()


def test_a_429_pauses_every_discord_request(tmp_path, discord):
    calls, answer = discord
    s = settings(tmp_path)
    answer.update(status=429, headers={"Retry-After": "3"})
    assert auth._bot_get(s, f"/users/{USER}").status_code == 429
    answer.update(status=200, headers={})
    for path in (f"/users/{USER}", f"/guilds/x/members/{USER}", "/guilds/x/roles"):  # every kind, not only the one refused
        with pytest.raises(auth.DiscordPaused, match="429"):
            auth._bot_get(s, path)
    assert len(calls) == 1
    auth.discord_limiter.paused_until = time.monotonic()  # the wait is over
    assert auth._bot_get(s, f"/users/{USER}").status_code == 200


def test_many_refusals_stop_all_discord_requests(tmp_path, discord, monkeypatch, caplog):
    calls, answer = discord
    monkeypatch.setattr(auth, "INVALID_MAX", 5)
    monkeypatch.setattr(auth, "DISCORD_BURST", 100)
    auth.discord_limiter.reset()
    s = settings(tmp_path)
    answer["status"] = 401  # e.g. a wrong bot token
    for _ in range(5):
        auth._bot_get(s, f"/users/{USER}")
    with pytest.raises(auth.DiscordPaused, match="refused requests"):
        auth._bot_get(s, f"/users/{USER}")
    assert len(calls) == 5
    assert any("check the bot token" in r.getMessage() for r in caplog.records)


def test_server_roles_are_remembered(tmp_path, discord):
    calls, _ = discord
    s = settings(tmp_path)
    for _ in range(5):
        assert auth.server_roles(s)[0]["name"] == "Staff"
    assert sum(p.endswith("/roles") for _, p in calls) == 1


def test_login_goes_through_the_limiter(tmp_path, discord):
    calls, answer = discord
    s = settings(tmp_path)
    answer.update(status=429, headers={"Retry-After": "5"})
    with pytest.raises(httpx.HTTPError):
        auth.user_from_code(s, "code")
    answer.update(status=200, headers={})
    with pytest.raises(auth.DiscordPaused):
        auth.user_from_code(s, "code")
    assert len(calls) == 1
