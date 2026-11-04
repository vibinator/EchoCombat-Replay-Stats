"""Public Echo Arena matches per player, counted from the live Nakama match list (user, 2026-11-04). Completely
separate from the Combat stats: own tables (arena_players, arena_counted), own module, own endpoint.

The list (https://g.echovrce.com/status/matches) only shows the matches running right now, so this polls it and
remembers who is in which public Arena match. A player counts once per match after MIN_PRESENT_S (3 minutes) in it.
Polling is kept very low (user, 2026-11-04): one small GET per `arena_poll_s` (60 s), the database is only written
when a match is counted, a failed request backs off (x2, up to 5 minutes), and the rest of the state is in memory."""

import logging
import threading
import time
from datetime import datetime

import httpx
from sqlalchemy import delete, select

from .models import ArenaCounted, ArenaPlayer

URL = "https://g.echovrce.com/status/matches"
MIN_PRESENT_S = 180.0  # time spent in one match before it counts (user, 2026-11-04)
TIMEOUT_S = 5
MAX_BACKOFF_S = 300.0
KEEP_COUNTED_S = 2 * 86400
PRUNE_EVERY_S = 3600
log = logging.getLogger("uvicorn.error")


def is_public_arena(label: dict) -> bool:
    mode = str(label.get("mode") or "")
    return label.get("lobby_type") == "public" and mode.startswith("echo_arena") and "private" not in mode


class Tracker:
    def __init__(self, sessionmaker, settings, fetch=None):
        self.sessionmaker, self.interval = sessionmaker, settings.arena_poll_s
        self.fetch = fetch or self._fetch
        self._seen: dict[tuple[str, str], list[float]] = {}  # (match id, user id) -> [last seen, seconds present]
        self._counted: set[tuple[str, str]] = set()
        self._loaded = False
        self._pruned = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="arena-poll", daemon=True)

    def start(self) -> None:
        if self.interval > 0:
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _fetch() -> dict:
        r = httpx.get(URL, timeout=TIMEOUT_S, headers={"User-Agent": "EchoVR-Replay-Stats"})
        r.raise_for_status()
        return r.json()

    def _run(self) -> None:
        wait = self.interval
        while not self._stop.wait(wait):
            try:
                self.poll()
                wait = self.interval
            except Exception as e:  # network down, bad JSON...: ask less often until it works again
                wait = min(max(wait, self.interval) * 2, MAX_BACKOFF_S)
                log.warning("arena poll failed (%s); next try in %d s", e, wait)

    def poll(self, now: float | None = None) -> int:
        """One look at the list; returns how many player-matches were newly counted."""
        data = self.fetch()
        now = time.time() if now is None else now
        if not self._loaded:  # after a restart: what was already counted
            with self.sessionmaker() as db:
                self._counted = {(m, u) for m, u in db.execute(select(ArenaCounted.match_id, ArenaCounted.user_id))}
            self._loaded = True
        present: dict[tuple[str, str], dict] = {}
        for label in data.get("labels") or []:
            if is_public_arena(label):
                for p in label.get("players") or []:
                    if p.get("user_id") and label.get("id"):
                        present[(str(label["id"]), str(p["user_id"]))] = p
        new: list[tuple[tuple[str, str], dict]] = []
        for key, p in present.items():
            if key in self._seen:
                last, secs = self._seen[key]
                # a gap (left and came back, or a missed poll) adds at most two intervals: only time in the match counts
                secs += min(now - last, 2 * self.interval)
            else:
                secs = 0.0
            self._seen[key] = [now, secs]
            if secs >= MIN_PRESENT_S and key not in self._counted:
                new.append((key, p))
        for key in [k for k, v in self._seen.items() if k not in present and now - v[0] > 2 * self.interval + 1]:
            del self._seen[key]  # gone from the list
        prune = now - self._pruned >= PRUNE_EVERY_S
        if new or prune:
            self._save(new, now, prune)
        return len(new)

    def _save(self, new, now: float, prune: bool) -> None:
        stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        with self.sessionmaker() as db:
            for (match_id, user_id), p in new:
                db.add(ArenaCounted(match_id=match_id, user_id=user_id, counted_at=now))
                row = db.get(ArenaPlayer, user_id)
                if row is None:
                    row = ArenaPlayer(user_id=user_id, username=p.get("username") or "?", display_name=p.get("display_name"),
                                      matches=0, last_match_at=stamp)
                    db.add(row)
                row.matches += 1
                row.username = p.get("username") or row.username
                row.display_name = p.get("display_name") or row.display_name
                row.last_match_at = stamp
                self._counted.add((match_id, user_id))
            if prune:
                db.execute(delete(ArenaCounted).where(ArenaCounted.counted_at < now - KEEP_COUNTED_S))
            db.commit()
        if prune:
            self._pruned = now
            self._loaded = False  # re-read what is still counted (pruned rows leave memory too)
