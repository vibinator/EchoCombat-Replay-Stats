"""Echo Combat George League roster (user, 2026-11-27): who is in the league and who is on a team, read from the league's
public site, ecgleague.com, for two Specials (profile_achievements.py). Every POLL_S (an hour) the server reads the player list
(/api/players) and each team's roster (/api/team/<id>: current and former members), one request a second, and keeps only
the Discord ids with the date each was first seen (models.LeagueMember). Nothing is sent to the league site but plain GETs."""

import logging
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .models import LeagueMember

log = logging.getLogger(__name__)

BASE = "https://ecgleague.com"
POLL_S = 3600  # every hour (user, 2026-11-27: 6 hours was too long); ~33 small requests a read. First read a minute after start
FIRST_S = 60
PACE_S = 1.0  # between requests to the league site
TIMEOUT_S = 20
MAX_BYTES = 2_000_000
MAX_TEAMS = 200  # a sane cap on requests per read (the league had 32 teams, 2026-11-27)
MAX_BACKOFF_S = 24 * 3600


def _is_discord_id(value) -> bool:
    return isinstance(value, str) and value.isdigit() and 15 <= len(value) <= 21


def _get(path: str):
    r = httpx.get(BASE + path, timeout=TIMEOUT_S, headers={"User-Agent": "EchoVR-Replay-Stats"}, follow_redirects=False)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError("league answer too large")
    return r.json()


def read_rosters(get=_get, pause=time.sleep) -> tuple[set[str], set[str]]:
    """(Discord ids on the player list, Discord ids on any team's current or former roster)."""
    players = get("/api/players")
    if not isinstance(players, list):
        raise ValueError("unexpected player list")
    league = {p["id"] for p in players if isinstance(p, dict) and _is_discord_id(p.get("id"))}
    teams = get("/api/teams")
    if not isinstance(teams, list):
        raise ValueError("unexpected team list")
    on_team: set[str] = set()
    for t in [t for t in teams if isinstance(t, dict) and isinstance(t.get("id"), int)][:MAX_TEAMS]:
        pause(PACE_S)
        team = get(f"/api/team/{t['id']}")
        if not isinstance(team, dict):
            continue
        for member in (team.get("roster") or []) + (team.get("former_roster") or []):
            if isinstance(member, dict) and _is_discord_id(member.get("id")):
                on_team.add(member["id"])
    return league, on_team


def store(sessionmaker, league: set[str], on_team: set[str], now: str | None = None) -> int:
    """Adds who is new and dates their first team; returns how many accounts were added. A team member missing from the
    player list (a former member who left the league) still counts as having joined."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = 0
    with sessionmaker() as db:
        known = {m.discord_id: m for m in db.scalars(select(LeagueMember))}
        for discord_id in league | on_team:
            m = known.get(discord_id)
            if m is None:
                m = LeagueMember(discord_id=discord_id, joined_at=now, team_at=None, last_seen_at=now)
                db.add(m)
                added += 1
            if discord_id in league:
                m.last_seen_at = now
            if discord_id in on_team and m.team_at is None:
                m.team_at = now
        db.commit()
    return added


class LeagueSync:
    """Reads the league rosters every POLL_S in its own thread (started with the other pollers, main.py)."""

    def __init__(self, sessionmaker, get=_get):
        self.sessionmaker, self.get = sessionmaker, get
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="league-sync", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def sync(self) -> int:
        league, on_team = read_rosters(self.get, lambda s: self._stop.wait(s))
        added = store(self.sessionmaker, league, on_team)
        self.last_ok, self.last_error = time.time(), None
        return added

    def _run(self) -> None:
        wait = FIRST_S
        while not self._stop.wait(wait):
            try:
                added = self.sync()
                log.info("league roster read: %d new", added)
                wait = POLL_S
            except Exception as e:  # league site down or changed: try again later, less often
                wait = min(max(wait, POLL_S) * 2, MAX_BACKOFF_S)
                self.last_error = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"[:160]
                log.warning("league roster read failed (%s); next try in %d s", e, wait)
