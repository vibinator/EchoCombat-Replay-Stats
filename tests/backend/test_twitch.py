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


def test_answer_is_remembered(monkeypatch):
    calls = []
    monkeypatch.setattr(twitch, "_memo", {})
    monkeypatch.setattr(twitch, "_ask", lambda channel: calls.append(channel) or {"live": True, "since": None})
    assert twitch.live("bot")["live"] and twitch.live("bot")["live"]
    assert calls == ["bot"]
