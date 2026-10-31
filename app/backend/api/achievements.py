"""Achievements / Flamingo Challenges per player, rarity, recent unlocks, the achievement ranking, and the
challenge period (Phase 8, D17, D31, D33). Read-only: the period and player merges are set in the admin console."""

import threading
import time
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .. import auth, icons
from ..achievements import RULES, Game, evaluate, icon_file, in_window, overall, unlock_dates
from ..admin_actions import WINDOW_KEYS, achievements_launched, challenge_window
from ..cache import cached, data_stamp
from ..duplicates import counted
from ..errors import ApiError
from ..models import AppSetting, Match, MatchPlayer, MatchPlayerLoadout, Player

router = APIRouter(tags=["achievements"])

RARITY_MIN_GAMES = 10
RECENT_DAYS = 30


# --- challenge period ---------------------------------------------------------------------

def _window_info(db) -> dict:
    start, end = challenge_window(db)
    updated = db.scalar(select(func.max(AppSetting.updated_at)).where(AppSetting.key.in_(WINDOW_KEYS)))
    today = date.today().isoformat()
    launched = achievements_launched(db)
    return {"start": start, "end": end, "updated_at": updated, "launched": launched,
            "active": launched and (not end or today <= end)}


def visible(request: Request) -> bool:
    """Public from the start date on; before it only to Discord members with a preview role (D41)."""
    with request.app.state.sessionmaker() as db:
        launched = achievements_launched(db)
    return launched or auth.has_preview(request)


def require_launched(request: Request) -> None:
    """Before the start date achievements and challenges are private: "Coming soon" on the website."""
    if not visible(request):
        raise ApiError(403, "coming_soon", "Achievements and challenges are coming soon")


def counted_window(db) -> tuple[str | None, str | None]:
    """Matches that count. Before the launch only previewers see anything, and they get every match in the
    archive (user, 2026-10-30): a start date still to come would show everyone at 0 %."""
    return challenge_window(db) if achievements_launched(db) else (None, None)


@router.get("/api/challenges")
def get_challenges(request: Request):
    """The Flamingo Challenge period: only matches inside it count. No start date = not launched yet."""
    with request.app.state.sessionmaker() as db:
        info = _window_info(db)
        # total and the sneak peek are public before the launch too: the menu and "Coming soon" page tease them
        peek = PEEK | {"revealed": icons.apply(db, PEEK["revealed"])}  # icons chosen on the Console page (D43)
    return info | {"preview": not info["launched"] and auth.has_preview(request), "total": len(RULES), "peek": peek}


# Shown in full on the "Coming soon" page (user, 2026-10-31): one per original section, one new challenge.
REVEALED_IDS = (9, 45, 18, 70, 93)


def _peek() -> dict:
    """Sneak peek for the "Coming soon" page (user, 2026-10-31): how many per section, the REVEALED_IDS in full,
    and a few more badge pictures without names, descriptions or targets."""
    periods: dict[str, int] = defaultdict(int)
    themes: dict[str, int] = defaultdict(int)
    for r in RULES:
        if r.new:
            themes[r.group or "More"] += 1
        else:
            periods[r.period] += 1
    by_id = {r.id: r for r in RULES}
    revealed = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r),
                 "estimated": r.estimated, "new": r.new, "group": r.group} for r in map(by_id.get, REVEALED_IDS)]
    shown = {r["icon"] for r in revealed}
    art = [f for f in dict.fromkeys(icon_file(r) for r in RULES if r.icon) if f and f not in shown]
    step = max(1, len(art) // 6)
    return {"periods": dict(periods), "new": dict(themes), "revealed": revealed, "icons": art[::step][:6]}


PEEK = _peek()


# --- data ---------------------------------------------------------------------------------

FINGERPRINT_MASK = (1 << 64) - 1


def _games(db, player_ids: list[int] | None = None, fingerprints: dict[int, int] | None = None) -> dict[int, list[Game]]:
    """player_id -> Game list (all matches). None = every player. Plain column rows, not ORM objects
    (the full archive is 200k+ appearances). `fingerprints` is filled with player_id -> a hash of every row the
    player's games are built from: equal fingerprints = equal games."""
    fp = fingerprints if fingerprints is not None else {}
    query = select(
        MatchPlayer.player_id, MatchPlayer.match_id, Match.started_at, Match.map, Match.mode, Match.private_match,
        MatchPlayer.play_time_s, MatchPlayer.deaths_est, MatchPlayer.frames_in_bounds, MatchPlayer.frames_near_mate,
        MatchPlayer.frames_near_enemy, MatchPlayer.frames_upside_down, MatchPlayer.speed_sum, MatchPlayer.top_speed,
        Match.frame_rate_hz, MatchPlayer.team, Match.winner, Match.attacking_team, Match.blue_rounds, Match.orange_rounds,
        MatchPlayer.payload_push_s, MatchPlayer.payload_block_s, MatchPlayer.emote_count,
    ).join(Match, Match.id == MatchPlayer.match_id).where(counted(MatchPlayer.match_id))  # duplicates left out (D13)
    lo_query = select(MatchPlayerLoadout.match_id, MatchPlayerLoadout.player_id, MatchPlayerLoadout.weapon,
                      MatchPlayerLoadout.tacmod, MatchPlayerLoadout.ordnance, MatchPlayerLoadout.frames
                      ).where(counted(MatchPlayerLoadout.match_id))
    if player_ids is not None:
        query = query.where(MatchPlayer.player_id.in_(player_ids))
        lo_query = lo_query.where(MatchPlayerLoadout.player_id.in_(player_ids))
    loadouts: dict[tuple[int, int], dict] = defaultdict(dict)
    for row in db.execute(lo_query):
        match_id, player_id, weapon, tacmod, ordnance, frames = row = tuple(row)
        loadouts[(match_id, player_id)][(weapon, tacmod, ordnance)] = frames
        fp[player_id] = (fp.get(player_id, 0) + hash(row)) & FINGERPRINT_MASK
    games: dict[int, list[Game]] = defaultdict(list)
    for row in db.execute(query):
        (pid, mid, started, map_, mode, private, play, deaths, bounds, mate, enemy, upside, speed, top, hz,
         team, winner, attacking, blue_rounds, orange_rounds, push, block, emotes) = row = tuple(row)
        fp[pid] = (fp.get(pid, 0) + hash(row)) & FINGERPRINT_MASK
        games[pid].append(Game(
            started_at=started, map=map_, mode=mode, private=private, play_time_s=play, deaths=deaths,
            in_bounds=bounds, near_mate=mate, near_enemy=enemy, upside=upside, speed_sum=speed, top_speed=top,
            frame_rate=hz, loadouts=loadouts.get((mid, pid), {}), team=team, winner=winner, attacking_team=attacking,
            rounds_lost=orange_rounds if team == "blue" else blue_rounds, push_s=push, block_s=block, emotes=emotes,
        ))
    return games


@router.get("/api/players/{user_id}/achievements")
def player_achievements(request: Request, user_id: str):
    require_launched(request)
    with request.app.state.sessionmaker() as db:
        window = counted_window(db)  # part of the cache key: an admin period change shows at once
    result = cached(request, "achievements", (user_id, window), lambda: _player_achievements(request, user_id))
    with request.app.state.sessionmaker() as db:
        return result | {"items": icons.apply(db, result["items"])}  # icons chosen on the Console page (D43)


def _player_achievements(request: Request, user_id: str) -> dict:
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        start, end = counted_window(db)
        games = in_window(_games(db, [player.id]).get(player.id, []), start, end)
    results = evaluate(games)
    unlocked = unlock_dates(games)
    for r in results:
        r["unlocked_at"] = unlocked.get(r["id"])
    return {
        "user_id": user_id,
        "name": player.name,
        "window": {"start": start, "end": end},
        "games": len(games),
        "overall": overall(results),
        "completed": sum(1 for r in results if r["progress"] >= 1),
        "total": len(results),
        "items": results,
    }


# --- everyone (ranking, rarity, recent unlocks) ---------------------------------------------

REUSE_WHILE_IMPORTING_S = 600  # the full archive takes a while: not redone for every processed replay
_cache: dict[int, tuple[tuple, float, dict]] = {}  # id(sessions) -> (key, computed at, data)
_refreshing: set[int] = set()
_lock = threading.Lock()


# id(sessions) -> player_id -> [(fingerprint, window), progress per rule, overall, unlock dates or None]. A new
# replay changes the games of ~8 players: only those are evaluated again (all 8k players take ~15 s).
_evaluated: dict[int, dict[int, list]] = {}


def _compute(sessions, window: tuple) -> dict:
    fingerprints: dict[int, int] = {}
    with sessions() as db:
        games = {pid: in_window(gs, *window) for pid, gs in _games(db, fingerprints=fingerprints).items()}
        latest = db.scalar(select(func.max(Match.started_at)))
        people = {pid: (uid, name) for pid, uid, name in db.execute(select(Player.id, Player.user_id, Player.name))}
    previous = _evaluated.get(id(sessions), {})
    evaluated: dict[int, list] = {}
    rows, progress = [], {}
    for pid, gs in games.items():
        if not gs:
            continue
        key = (fingerprints[pid], window)
        entry = previous.get(pid)
        if entry is None or entry[0] != key:
            results = evaluate(gs)
            entry = [key, [r["progress"] for r in results], overall(results), None]
        evaluated[pid] = entry
        progress[pid] = entry[1]
        rows.append((pid, len(gs), entry[2]))
    _evaluated[id(sessions)] = evaluated
    return {"rows": rows, "progress": progress, "recent": _recent(games, latest, people, evaluated)}


def _recent(games: dict[int, list[Game]], latest: str | None, people: dict, evaluated: dict[int, list]) -> list[dict]:
    """Every 100 % completion in the last RECENT_DAYS of the archive, newest first."""
    if not latest:
        return []
    cutoff = (date.fromisoformat(latest[:10]) - timedelta(days=RECENT_DAYS)).isoformat()
    rules = {r.id: r for r in RULES}
    events = []
    for pid, gs in games.items():
        if not gs or max(g.started_at for g in gs)[:10] < cutoff:
            continue
        entry = evaluated[pid]
        if entry[3] is None:
            entry[3] = unlock_dates(gs)
        for rule_id, day in entry[3].items():
            if day >= cutoff:
                uid, name = people[pid]
                events.append({"date": day, "user_id": uid, "name": name, "id": rule_id,
                               "achievement": rules[rule_id].name, "icon": icon_file(rules[rule_id])})
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


def _store(sessions, key: tuple) -> dict:
    data = _compute(sessions, key[1])
    _cache[id(sessions)] = (key, time.monotonic(), data)
    return data


def _refresh_in_background(sessions, key: tuple) -> None:
    with _lock:
        if id(sessions) in _refreshing:
            return
        _refreshing.add(id(sessions))

    def run():
        try:
            _store(sessions, key)
        finally:
            with _lock:
                _refreshing.discard(id(sessions))

    threading.Thread(target=run, name="achievements-refresh", daemon=True).start()


def ranking_state(sessions) -> dict:
    """For the Status page: is the everyone-ranking (leaderboard, rarity, recent unlocks) being recalculated, and
    does the last result match the current data?"""
    with _lock:
        calculating = id(sessions) in _refreshing
    cached = _cache.get(id(sessions))
    return {"calculating": calculating, "calculated": cached is not None,
            "up_to_date": bool(cached) and cached[0] == _key(sessions),
            "age_s": round(time.monotonic() - cached[1]) if cached else None}


def _key(sessions) -> tuple:
    """(data stamp, challenge window)."""
    with sessions() as db:
        return data_stamp(db), counted_window(db)


def warm(sessions, previews: bool = False) -> None:
    """Fill the cache at startup so the first achievements / leaderboard visit does not wait."""
    with sessions() as db:
        if not achievements_launched(db) and not previews:
            return  # nobody can see anything before the start date
    _refresh_in_background(sessions, _key(sessions))


def _everyone(request: Request) -> dict:
    """{"rows": [(player_id, games, overall)], "progress": {player_id: [progress per rule]}, "recent": [...]}
    within the challenge period. New data: the previous result is served at once and recomputed in the
    background (at most every 10 minutes while an import is running). Only the very first request and a
    challenge-period change wait for the computation."""
    sessions = request.app.state.sessionmaker
    key = _key(sessions)
    cached = _cache.get(id(sessions))
    if cached and cached[0] == key:
        return cached[2]
    if cached and cached[0][1] == key[1]:
        if not (request.app.state.worker.busy and time.monotonic() - cached[1] < REUSE_WHILE_IMPORTING_S):
            _refresh_in_background(sessions, key)
        return cached[2]
    return _store(sessions, key)


def achievement_ranking(request: Request) -> list[tuple[int, int, float]]:
    return _everyone(request)["rows"]


@router.get("/api/achievements")
def list_achievements(request: Request):
    """The rule catalogue with rarity: share of players (10+ games) who unlocked (25 %+) / completed each."""
    require_launched(request)
    data = _everyone(request)
    eligible = [data["progress"][pid] for pid, games, _ in data["rows"] if games >= RARITY_MIN_GAMES]
    out = []
    for i, r in enumerate(RULES):
        values = [p[i] for p in eligible]
        out.append({"id": r.id, "name": r.name, "description": r.description, "period": r.period,
                    "icon": icon_file(r), "estimated": r.estimated, "new": r.new, "group": r.group,
                    "unlocked_share": round(sum(v >= 0.25 for v in values) / len(values), 4) if values else None,
                    "completed_share": round(sum(v >= 1 for v in values) / len(values), 4) if values else None})
    with request.app.state.sessionmaker() as db:
        return icons.apply(db, out)


@router.get("/api/achievements/recent")
def recent_unlocks(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Latest 100 % completions by players active in the last 30 days of the archive."""
    require_launched(request)
    with request.app.state.sessionmaker() as db:
        return icons.apply(db, _everyone(request)["recent"][:limit])
