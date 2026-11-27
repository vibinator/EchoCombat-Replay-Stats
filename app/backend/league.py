"""Echo Combat George League, Rookie League only (user, 2026-11-27: "focus only on the rookie league, ignore the varsity
league"): who is in it, on a team, has played and won a Rookie match, and who is a League Sub allowed in Rookie, read from
the league's public site, ecgleague.com, for its Specials (profile_achievements.py).

The site serves both leagues at the same addresses and picks one by the X-ECGL-League header ("main" = Varsity, the default,
or "rookie"; its own pages send it from the league chosen in the menu). Teams, team pages, the leaderboard and player pages
follow it; the player list (/api/players) is shared by both leagues. Every POLL_S (an hour) the server reads, with
"rookie": the player list (League Subs, veterans), the player leaderboard (/api/leaderboard/players: this season's Rookie
matches and wins), the team list and each team's roster (/api/team/<id>: current and former members), one request a
second. Earlier Rookie seasons are read once per player from their own page (/api/player/<id>, archived_stats).

What counts (user, 2026-11-27): joined = on a Rookie team (now or before) or on the Rookie leaderboard; team = on a Rookie
team's roster; played / won = at least one Rookie match; sub = the League Sub role and allowed in Rookie (not a veteran, or
given an override; the role itself is shared by both leagues). Only the Discord ids and the date each thing was first
seen are kept (models.LeagueMember). Nothing is sent to the league site but plain GETs."""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .models import LeagueMember

log = logging.getLogger(__name__)

BASE = "https://ecgleague.com"
POLL_S = 3600  # every hour (user, 2026-11-27: 6 hours was too long); ~10 small requests a read. First read a minute after start
FIRST_S = 60
PACE_S = 1.0  # between requests to the league site
TIMEOUT_S = 20
MAX_BYTES = 2_000_000
MAX_TEAMS = 200  # a sane cap on requests per read (the Rookie League had 6 teams, 2026-11-27)
MAX_ARCHIVES = 400  # player pages read per run for earlier seasons (18 on the Rookie leaderboard on 2026-11-27)
MAX_BACKOFF_S = 24 * 3600
LEAGUE = "rookie"  # the X-ECGL-League value of the Rookie League ("main" = Varsity, not read)
SUB_ROLE = "League Sub"


@dataclass
class Rosters:
    league: set[str] = field(default_factory=set)  # in the Rookie League: on a Rookie team (now or before) or its leaderboard
    on_team: set[str] = field(default_factory=set)  # on a Rookie team's roster, current or former
    played: set[str] = field(default_factory=set)  # at least one Rookie match
    won: set[str] = field(default_factory=set)  # at least one Rookie match won
    subs: set[str] = field(default_factory=set)  # League Sub role, allowed in Rookie
    ranked: set[str] = field(default_factory=set)  # everyone on the Rookie leaderboard (their earlier seasons can be read)


def _is_discord_id(value) -> bool:
    return isinstance(value, str) and value.isdigit() and 15 <= len(value) <= 21


def _count(value) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def _get(path: str):
    r = httpx.get(BASE + path, timeout=TIMEOUT_S, headers={"User-Agent": "EchoVR-Replay-Stats", "X-ECGL-League": LEAGUE},
                  follow_redirects=False)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError("league answer too large")
    return r.json()


def _people(answer) -> list[dict]:
    if not isinstance(answer, list):
        raise ValueError("unexpected league answer")
    return [p for p in answer if isinstance(p, dict) and _is_discord_id(p.get("id"))]


def read_rosters(get=_get, pause=time.sleep) -> Rosters:
    """The Rookie League: the player list (subs), the leaderboard and every team's roster (`get` sends X-ECGL-League)."""
    out = Rosters()
    for p in _people(get("/api/players")):  # shared by both leagues: only the subs allowed in Rookie are taken from it
        if p.get("role") == SUB_ROLE and (not p.get("is_veteran") or p.get("play_override")):
            out.subs.add(p["id"])
    pause(PACE_S)
    for p in _people(get("/api/leaderboard/players")):
        out.ranked.add(p["id"])
        if _count(p.get("matches")):
            out.played.add(p["id"])
        if _count(p.get("wins")):
            out.won.add(p["id"])
    pause(PACE_S)
    teams = get("/api/teams")
    if not isinstance(teams, list):
        raise ValueError("unexpected team list")
    for t in [t for t in teams if isinstance(t, dict) and isinstance(t.get("id"), int)][:MAX_TEAMS]:
        pause(PACE_S)
        team = get(f"/api/team/{t['id']}")
        if not isinstance(team, dict):
            continue
        for member in (team.get("roster") or []) + (team.get("former_roster") or []):
            if isinstance(member, dict) and _is_discord_id(member.get("id")):
                out.on_team.add(member["id"])
    out.league = out.on_team | out.ranked
    return out


def read_archive(get, discord_id: str) -> tuple[bool, bool]:
    """(played, won) a league match in an earlier season, from the player's own page."""
    page = get(f"/api/player/{discord_id}")
    seasons = page.get("archived_stats") if isinstance(page, dict) else None
    seasons = [s for s in seasons or [] if isinstance(s, dict)]
    return any(_count(s.get("archive_matches")) for s in seasons), any(_count(s.get("archive_wins")) for s in seasons)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def store(sessionmaker, r: Rosters, now: str | None = None) -> int:
    """Adds who is new and dates what each did first; returns how many accounts were added. Nothing is ever taken away:
    a player who left the league or a team keeps what they did."""
    now = now or _now()
    added = 0
    with sessionmaker() as db:
        known = {m.discord_id: m for m in db.scalars(select(LeagueMember))}
        for discord_id in r.league | r.on_team | r.played | r.won | r.subs:
            m = known.get(discord_id)
            if m is None:
                m = LeagueMember(discord_id=discord_id, last_seen_at=now)
                db.add(m)
                added += 1
            m.last_seen_at = now
            for flag, column in ((r.league, "joined_at"), (r.on_team, "team_at"), (r.played, "played_at"), (r.won, "won_at"),
                                 (r.subs, "sub_at")):
                if discord_id in flag and getattr(m, column) is None:
                    setattr(m, column, now)
        db.commit()
    return added


def store_archives(sessionmaker, get, ranked: set[str], pause=time.sleep, now: str | None = None) -> int:
    """Earlier seasons, read once for each leaderboard player not read yet; returns how many pages were read."""
    with sessionmaker() as db:
        todo = sorted(db.scalars(select(LeagueMember.discord_id).where(
            LeagueMember.discord_id.in_(list(ranked)), LeagueMember.archive_checked.is_not(True))))[:MAX_ARCHIVES]
    for i, discord_id in enumerate(todo):
        if i:
            pause(PACE_S)
        played, won = read_archive(get, discord_id)
        stamp = now or _now()
        with sessionmaker() as db:
            m = db.get(LeagueMember, discord_id)
            if (played or won) and m.joined_at is None:
                m.joined_at = stamp
            if played and m.played_at is None:
                m.played_at = stamp
            if won and m.won_at is None:
                m.won_at = stamp
            m.archive_checked = True
            db.commit()
    return len(todo)


class LeagueSync:
    """Reads the league every POLL_S in its own thread (started with the other pollers, main.py)."""

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
        def pause(s):
            self._stop.wait(s)

        rosters = read_rosters(self.get, pause)
        added = store(self.sessionmaker, rosters)
        pause(PACE_S)
        store_archives(self.sessionmaker, self.get, rosters.ranked, pause)
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
