"""What people open, remembered across restarts, so a restarted server can build those answers again before they are
asked for (user, 2026-11-16: "a brand new load in").

Every answer kept in memory (cache.py) is gone after a restart, and the site restarts with every update: several times
a day. Until now only the home page, the first Matches screen and the Leaderboard cards were built ahead; everything
else (a player's profile, a match, a board with a filter) made its first visitor wait for the build, on a server whose
database had just been evicted from memory by the update (measured on the live site on 2026-11-16, minutes after a
restart: a match list filter 21 s, the most active player's profile 13.5 s, a match 1 s; the same requests took
0.1 - 0.3 s ten minutes later).

`Popular` counts the data requests answered from the answer cache (public ones only: nothing that depends on the
visitor), saves the counts in <data>/cache/popular.json every few minutes, and after a restart `rebuild` asks the
server itself for the most asked ones, one at a time, most asked first. The answers are built by the new version's own
code: nothing from before the restart is ever sent to a visitor.

Counts fade (halved every HALF_LIFE_S), so the list follows what is being looked at this week. Cloudflare answers
most repeats itself, so a count here is "asked for at least once in that minute", which still ranks the busy pages
first."""

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

FILE_VERSION = 1
HALF_LIFE_S = 3 * 86400
MAX_PATHS = 4000  # remembered; the least asked go first
SAVE_EVERY_S = 300
# never rebuilt ahead: big answers that have their own stores (heatmaps are kept on disk, cache.py), lists of ids that
# change with every match, downloads, and searches (one per thing typed)
SKIP = ("/heatmap", "/playback", "/export", "/thumbnails", "/api/search", "/api/players?q=", ".csv", ".xlsx")
SCOPE_MARK = "echovr.rebuild"  # in the ASGI scope of a request this module makes itself (middleware.py lets it through)
UA = b"Mozilla/5.0 (rebuild after restart)"


def _wanted(path: str, query: str) -> str | None:
    """The address to remember for a request, None when it is not one to rebuild."""
    if query:
        # "_v" (api.ts: past a copy Cloudflare kept from before an update) is not part of the question
        query = "&".join(p for p in query.split("&") if p and not p.startswith("_v="))
    url = f"{path}?{query}" if query else path
    if len(url) > 300 or any(s in url for s in SKIP):
        return None
    return url


class Popular:
    def __init__(self, data_dir: Path):
        self.file = data_dir / "cache" / "popular.json"
        self.lock = threading.Lock()
        self.scores: dict[str, float] = {}
        self.at = time.time()  # the scores are as of this moment (fading is applied when saving / loading)
        self.changed = False
        self.saved_at = time.monotonic()
        self._load()

    def _load(self) -> None:
        try:
            saved = json.loads(self.file.read_text(encoding="utf-8"))
            if saved.get("version") != FILE_VERSION:
                return
            fade = 0.5 ** (max(0.0, time.time() - float(saved["saved"])) / HALF_LIFE_S)
            self.scores = {str(k): float(v) * fade for k, v in saved["paths"].items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            log.warning("The list of most asked answers (%s) cannot be read; starting a new one", self.file)

    def count(self, path: str, query: str) -> None:
        """One request answered from the answer cache."""
        url = _wanted(path, query)
        if url is None:
            return
        with self.lock:
            self.scores[url] = self.scores.get(url, 0.0) + 1.0
            self.changed = True
            due = time.monotonic() - self.saved_at > SAVE_EVERY_S
        if due:
            self.save()

    def top(self, n: int) -> list[str]:
        with self.lock:
            return [url for url, _ in sorted(self.scores.items(), key=lambda kv: -kv[1])[:n]]

    def save(self) -> None:
        """Never an error: a list that could not be saved only means fewer answers built ahead after the next restart."""
        with self.lock:
            if not self.changed:
                return
            now = time.time()
            fade = 0.5 ** ((now - self.at) / HALF_LIFE_S)
            kept = sorted(((u, s * fade) for u, s in self.scores.items()), key=lambda kv: -kv[1])[:MAX_PATHS]
            self.scores, self.at = {u: s for u, s in kept if s >= 0.05}, now
            self.changed, self.saved_at = False, time.monotonic()
            body = json.dumps({"version": FILE_VERSION, "saved": now, "paths": {u: round(s, 3) for u, s in self.scores.items()}})
        tmp = self.file.with_name(f"{self.file.name}.{os.getpid()}.tmp")
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, self.file)
        except OSError as e:
            log.warning("The list of most asked answers was not saved: %s", e)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


async def _ask(app, url: str) -> tuple[int, bool]:
    """One GET to this server from inside, as a page would send it; returns (status, it was built for this request).
    The body is thrown away: the point is that the answer cache now has it."""
    path, _, query = url.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"host", b"localhost"), (b"user-agent", UA), (b"x-echovr", b"1")],
             "client": ("127.0.0.1", 0), "server": ("localhost", 80), "state": {}, SCOPE_MARK: True}
    status, built = [0], [False]
    asked = []

    async def receive():
        if not asked:
            asked.append(1)
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()  # "still connected" until the answer is done

    async def send(message):
        if message["type"] == "http.response.start":
            status[0] = message["status"]
            built[0] = any(k.lower() == b"x-echovr-cache" and v == b"MISS" for k, v in message.get("headers", ()))

    await app(scope, receive, send)
    return status[0], built[0]


def rebuild(app, count: int, stop: threading.Event, busy=lambda: False) -> int:
    """Ask for the `count` most asked answers, most asked first; returns how many were built (those the server had
    already are not counted). One at a time, resting as long as each build took (never more than half a core), not
    while replays are being processed, and ending early when the server stops."""
    popular: Popular | None = getattr(app.state, "popular", None)
    if popular is None or count <= 0:
        return 0
    urls = popular.top(count)
    started, built = time.monotonic(), 0
    for url in urls:
        while busy() and not stop.wait(10):
            pass
        if stop.is_set():
            break
        t = time.monotonic()
        try:
            status, was_built = asyncio.run(_ask(app, url))
        except Exception as e:  # noqa: BLE001 - one answer that cannot be built must not end the pass
            log.debug("Rebuilding %s failed: %s: %s", url, type(e).__name__, e)
            continue
        if status == 200 and was_built:  # not one the server had already (asked for by a visitor meanwhile)
            built += 1
            if stop.wait(min(time.monotonic() - t, 5.0)):
                break
    if urls:
        log.warning("Answers built again after the restart: %d of the %d most asked, in %.0f s", built, len(urls), time.monotonic() - started)
    return built
