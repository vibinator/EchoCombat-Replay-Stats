from datetime import datetime

from app.backend import twitch

NOW = datetime(2026, 11, 1, 20, 0, 0)


def test_live_uptime_gives_the_start_time():
    assert twitch.parse("bot", "1 hour, 3 minutes, 52 seconds", NOW) == {"live": True, "since": "2026-11-01T18:56:08"}
    assert twitch.parse("bot", "42 seconds", NOW)["live"] is True


def test_offline():
    assert twitch.parse("bot", "bot is offline", NOW) == {"live": False, "since": None}


def test_anything_else_is_unknown():
    for text in ("", "User not found: bot", "Rate limit exceeded, 5 minutes", "<html>502</html>"):
        assert twitch.parse("bot", text, NOW)["live"] is None, text


def test_no_channel_is_not_asked(monkeypatch):
    monkeypatch.setattr(twitch, "_ask", lambda channel: (_ for _ in ()).throw(AssertionError("asked")))
    assert twitch.live("") == {"live": None, "since": None}


def test_live_endpoint_is_never_cached(monkeypatch, tmp_path):
    # "Game in progress" (user 2026-11-01): no browser or Cloudflare copy, even with the edge cache on
    from app_helpers import app_client, make_settings

    from backend import twitch as app_twitch  # the module the app imported

    monkeypatch.setattr(app_twitch, "live", lambda channel: {"live": True, "since": "2026-11-01T18:56:08"})
    with app_client(make_settings(tmp_path, edge_cache_s=60)) as client:
        r = client.get("/api/overview/live")
        assert r.json() == {"live": True, "since": "2026-11-01T18:56:08"}
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["cloudflare-cdn-cache-control"] == "no-store"
        assert "in_progress" not in client.get("/api/overview/last-match").json()


def test_twitch_is_checked_every_10_seconds():
    assert twitch.CHECK_S <= 10


def test_old_answer_is_sent_while_asking_again(monkeypatch):
    import threading

    monkeypatch.setattr(twitch, "_memo", {"bot": (0.0, {"live": False, "since": None})})  # long out of date
    monkeypatch.setattr(twitch, "_refreshing", set())
    asked = threading.Event()
    monkeypatch.setattr(twitch, "_ask", lambda channel: asked.set() or {"live": True, "since": None})
    assert twitch.live("bot")["live"] is False  # at once, the old answer
    assert asked.wait(5)
    for _ in range(100):  # the background ask stores its answer
        if twitch._memo["bot"][1]["live"]:
            break
        threading.Event().wait(0.01)
    assert twitch.live("bot")["live"] is True


def test_answer_is_remembered(monkeypatch):
    calls = []
    monkeypatch.setattr(twitch, "_memo", {})
    monkeypatch.setattr(twitch, "_ask", lambda channel: calls.append(channel) or {"live": True, "since": None})
    assert twitch.live("bot")["live"] and twitch.live("bot")["live"]
    assert calls == ["bot"]
