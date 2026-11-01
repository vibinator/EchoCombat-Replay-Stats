"""Is the Echo Combat spectator bot streaming on Twitch? It only streams while a game is being played, so "live" means
a game is in progress (home page, next to "Last match"). Asked through decapi.me (user 2026-11-01: no Twitch app to
set up): plain text, "<channel> is offline" or the uptime ("1 hour, 3 minutes, 52 seconds").

The answer is shared for CHECK_S seconds, wrong answers too, so decapi is asked at most every 10 s however many
visitors there are (asking per visitor would get the site rate-limited, and then nothing is known); one request at a
time (the others wait for it and get its answer). Nothing else keeps it: /api/overview/live is no-store."""

import re
import threading
import time
from datetime import datetime, timedelta

import httpx

CHECK_S = 10
TIMEOUT_S = 4
URL = "https://decapi.me/twitch/uptime/{channel}"
_PART = re.compile(r"(\d+)\s+(day|hour|minute|second)s?")
_UNIT_S = {"day": 86400, "hour": 3600, "minute": 60, "second": 1}

_lock = threading.Lock()
_memo: dict[str, tuple[float, dict]] = {}


def parse(channel: str, text: str, now: datetime) -> dict:
    """{"live": True/False, "since": local ISO time the stream started or None}; live None = no usable answer."""
    text = text.strip()
    if text.lower().endswith("is offline"):
        return {"live": False, "since": None}
    parts = _PART.findall(text)
    if parts and _PART.sub("", text).strip(" ,") == "":  # nothing but "<n> <unit>" pieces: an uptime
        up = sum(int(n) * _UNIT_S[u] for n, u in parts)
        return {"live": True, "since": (now - timedelta(seconds=up)).isoformat(timespec="seconds")}
    return {"live": None, "since": None}  # an error message, rate limit, unknown channel...


def _ask(channel: str) -> dict:
    try:
        r = httpx.get(URL.format(channel=channel), timeout=TIMEOUT_S, headers={"User-Agent": "EchoVR-Replay-Stats"})
        r.raise_for_status()
    except httpx.HTTPError:
        return {"live": None, "since": None}
    return parse(channel, r.text, datetime.now())


_refreshing: set[str] = set()


def _refresh(channel: str) -> None:
    try:
        answer = _ask(channel)
        with _lock:
            _memo[channel] = (time.monotonic(), answer)
    finally:
        with _lock:
            _refreshing.discard(channel)


def live(channel: str) -> dict:
    """The last answer at once; once it is CHECK_S old, decapi is asked again in the background (one request at a
    time), so no visitor waits the ~0.5 s it takes. Only the very first ask waits for the answer."""
    if not channel:
        return {"live": None, "since": None}
    with _lock:
        memo = _memo.get(channel)
        if memo is not None:
            if time.monotonic() - memo[0] >= CHECK_S and channel not in _refreshing:
                _refreshing.add(channel)
                threading.Thread(target=_refresh, args=(channel,), name="twitch-live", daemon=True).start()
            return memo[1]
        memo = (time.monotonic(), _ask(channel))  # first ask: wait for it (others wait on the lock and share it)
        _memo[channel] = memo
        return memo[1]
