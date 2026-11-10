"""Achievements / Flamingo Challenges per player, rarity, recent unlocks, the achievement ranking, and the
challenge period (Phase 8, D17, D31, D33). Read-only: the period and player merges are set in the admin console."""

import functools
import gc
import hashlib
import logging
import marshal
import pickle
import threading
import time
import zlib
from concurrent.futures import CancelledError
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .. import auth, combat_achievements, icons
from ..achievements import RULES, Game, evaluate, icon_file, in_window, medal_times, overall, rule_notes, unlock_dates, unlock_threshold
from ..admin_actions import (WINDOW_KEYS, achievements_counting, achievements_launched, achievements_visibility,
                             challenge_window, previews_can_see)
from .. import achievements as engine, gear as gear_tables
from ..cache import cached, current_stamp
from ..db import open_reader
from ..duplicates import counted
from ..errors import ApiError
from ..models import AppSetting, Match, MatchPlayer, MatchPlayerLoadout, Player

router = APIRouter(tags=["achievements"])
log = logging.getLogger(__name__)

RARITY_MIN_GAMES = 10
RECENT_DAYS = 30


# --- challenge period ---------------------------------------------------------------------

def _window_info(db) -> dict:
    start, end = challenge_window(db)
    updated = db.scalar(select(func.max(AppSetting.updated_at)).where(AppSetting.key.in_(WINDOW_KEYS)))
    today = date.today().isoformat()
    launched = achievements_launched(db)
    return {"start": start, "end": end, "updated_at": updated, "launched": launched,
            "visibility": achievements_visibility(db), "active": launched and (not end or today <= end)}


def visible(request: Request) -> bool:
    """Public from the start date on; before it only to Discord members with a preview role (D41)."""
    with request.app.state.sessionmaker() as db:
        launched, previews = achievements_launched(db), previews_can_see(db)
    return launched or (previews and auth.has_preview(request))


def require_launched(request: Request) -> None:
    """Before the start date achievements and challenges are private: "Coming soon" on the website."""
    if not visible(request):
        raise ApiError(403, "coming_soon", "Achievements and challenges are coming soon")


def counted_window(db) -> tuple[str | None, str | None]:
    """Matches that count. Before the launch only previewers see anything, and they get every match in the
    archive (user, 2026-10-30): a start date still to come would show everyone at 0 %. Preview-only with a start date
    that has come counts from it, like the public launch will."""
    return challenge_window(db) if achievements_counting(db) else (None, None)


@router.get("/api/challenges")
def get_challenges(request: Request):
    """The Flamingo Challenge period: only matches inside it count. No start date = not launched yet."""
    with request.app.state.sessionmaker() as db:
        info = _window_info(db)
        # total and the sneak peek are public before the launch too: the menu and "Coming soon" page tease them
        peek = PEEK | {"revealed": icons.apply(db, PEEK["revealed"])}  # icons chosen on the Console page (D43)
    with request.app.state.sessionmaker() as db:
        previews = previews_can_see(db)
    return info | {"preview": not info["launched"] and previews and auth.has_preview(request), "total": len(RULES), "peek": peek}


# Shown in full on the "Coming soon" page (user, 2026-10-31; refreshed 2026-11-03): original day, week and all-time
# challenges plus two of the new 4v4 "In one game" ones (Point Guard, Speed Demon).
REVEALED_IDS = (9, 45, 70, 146, 145)


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
    revealed = [{"id": r.id, "name": r.name, "description": r.description, "rules": rule_notes(r), "period": r.period, "icon": icon_file(r),
                 "estimated": r.estimated, "new": r.new, "group": r.group} for r in map(by_id.get, REVEALED_IDS)]
    shown = {r["icon"] for r in revealed}
    art = [f for f in dict.fromkeys(icon_file(r) for r in RULES if r.icon) if f and f not in shown]
    step = max(1, len(art) // 6)
    one_game = sum(1 for r in RULES if r.period == "game")  # original and new: every one needs 3+ players per team
    return {"periods": dict(periods), "new": dict(themes), "revealed": revealed, "icons": art[::step][:6], "one_game": one_game}


PEEK = _peek()


# --- data ---------------------------------------------------------------------------------

FINGERPRINT_MASK = (1 << 64) - 1


def _stable_hash(row: tuple) -> int:
    """Same value in every process (str hash() is randomised), so the results can be kept on disk across restarts.
    marshal: the row's exact values as bytes, twice as fast as repr() over the archive's 620k rows."""
    return zlib.crc32(marshal.dumps(row))


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
        MatchPlayer.frames_stopped, MatchPlayer.frames_left_arm, MatchPlayer.frames_right_arm, Match.contested_s,
        Match.blue_capture_s, Match.orange_capture_s, MatchPlayer.frames_lone_wolf_near,
    ).join(Match, Match.id == MatchPlayer.match_id).where(counted(MatchPlayer.match_id))  # duplicates left out (D13)
    lo_query = select(MatchPlayerLoadout.match_id, MatchPlayerLoadout.player_id, MatchPlayerLoadout.weapon,
                      MatchPlayerLoadout.tacmod, MatchPlayerLoadout.ordnance, MatchPlayerLoadout.frames
                      ).where(counted(MatchPlayerLoadout.match_id))
    if player_ids is not None:
        query = query.where(MatchPlayer.player_id.in_(player_ids))
        lo_query = lo_query.where(MatchPlayerLoadout.player_id.in_(player_ids))
    # players per team who were there for at least half of the match: 3 or more each = enough (3v3, 4v4, 5v4 ...)
    size_query = (select(MatchPlayer.match_id, MatchPlayer.team, func.count())
                  .join(Match, Match.id == MatchPlayer.match_id)
                  .where(counted(MatchPlayer.match_id), MatchPlayer.play_time_s >= 0.5 * Match.duration_s)
                  .group_by(MatchPlayer.match_id, MatchPlayer.team))
    if player_ids is not None:
        size_query = size_query.where(MatchPlayer.match_id.in_(
            select(MatchPlayer.match_id).where(MatchPlayer.player_id.in_(player_ids))))
    rows = db.connection()  # plain rows, without the ORM's per-row handling (a quarter of the time over the whole archive)
    sizes = {(m, t): n for m, t, n in rows.execute(size_query)}
    loadouts: dict[tuple[int, int], dict] = defaultdict(dict)
    for row in rows.execute(lo_query):
        match_id, player_id, weapon, tacmod, ordnance, frames = row = tuple(row)
        loadouts[(match_id, player_id)][(weapon, tacmod, ordnance)] = frames
        fp[player_id] = (fp.get(player_id, 0) + _stable_hash(row)) & FINGERPRINT_MASK
    games: dict[int, list[Game]] = defaultdict(list)
    for row in rows.execute(query):
        (pid, mid, started, map_, mode, private, play, deaths, bounds, mate, enemy, upside, speed, top, hz,
         team, winner, attacking, blue_rounds, orange_rounds, push, block, emotes, stopped, left, right, contested,
         blue_cap, orange_cap, lone_wolf_near) = row = tuple(row)
        four = sizes.get((mid, "blue"), 0) >= 3 and sizes.get((mid, "orange"), 0) >= 3
        fp[pid] = (fp.get(pid, 0) + _stable_hash(row + (four,))) & FINGERPRINT_MASK
        games[pid].append(Game(
            started_at=started, map=map_, mode=mode, private=private, play_time_s=play, deaths=deaths,
            in_bounds=bounds, near_mate=mate, near_enemy=enemy, upside=upside, speed_sum=speed, top_speed=top,
            frame_rate=hz, loadouts=loadouts.get((mid, pid), {}), team=team, winner=winner, attacking_team=attacking,
            rounds_lost=orange_rounds if team == "blue" else blue_rounds, push_s=push, block_s=block, emotes=emotes,
            stopped=stopped, left_arm=left, right_arm=right, contested_s=contested,
            capture_s=blue_cap if team == "blue" else orange_cap, enough_players=four, lone_wolf_near=lone_wolf_near,
        ))
    return games


@router.get("/api/players/{user_id}/achievements")
def player_achievements(request: Request, user_id: str):
    require_launched(request)
    with request.app.state.sessionmaker() as db:
        window = counted_window(db)  # part of the cache key: an admin period change shows at once
    result = cached(request, "achievements", (user_id, window), lambda: _player_achievements(request, user_id))
    # the Combat cards come from the recorder's reports, apart from the replay answer and its totals (D56)
    items = result["items"] + combat_achievements.player_items(request.app.state.sessionmaker, window, user_id)
    with request.app.state.sessionmaker() as db:
        return result | {"items": icons.apply(db, items)}  # icons chosen on the Console page (D43)


OFFLOAD_MIN_GAMES = 100  # a player with fewer games is evaluated at once (a few ms); more: in a helper process


def _player_achievements(request: Request, user_id: str) -> dict:
    """Evaluating every rule over a busy player's games is seconds of pure Python (measured 2026-11-10: 3.7 s for 8,700
    games on the dev PC, 5-12x that on the NAS). Done in the web server it holds up every other request meanwhile, so
    players with OFFLOAD_MIN_GAMES+ games are evaluated in a helper process (_elsewhere)."""
    sessions = request.app.state.sessionmaker
    with sessions() as db:
        played = db.scalar(select(func.count()).select_from(MatchPlayer).join(Player).where(Player.user_id == user_id))
    if (played or 0) >= OFFLOAD_MIN_GAMES:
        result = _elsewhere(sessions, "side", _player_job, _player_result, user_id)
    else:
        result = _player_result(sessions, user_id)
    if result is None:
        raise ApiError(404, "not_found", f"Player {user_id} not found")
    return result


def _player_result(sessions, user_id: str) -> dict | None:
    """One player's cards. None = no such player (neither in the replays nor in the combat reports)."""
    with sessions() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        start, end = counted_window(db)
        # someone can be in the combat reports without having a replay: their replay challenges are simply at 0
        name = player.name if player else combat_achievements.player_name(sessions, (start, end), user_id)
        if name is None:
            return None
        games = in_window(_games(db, [player.id]).get(player.id, []), start, end) if player else []
    results = evaluate(games)
    unlocked = unlock_dates(games)
    for r in results:
        r["unlocked_at"] = unlocked.get(r["id"])
    return {
        "user_id": user_id,
        "name": name,
        "window": {"start": start, "end": end},
        "games": len(games),
        "overall": overall(results),
        "completed": sum(1 for r in results if r["progress"] >= 1),
        "total": len(results),
        "items": results,
    }


# --- everyone (ranking, rarity, recent unlocks) ---------------------------------------------

REUSE_WHILE_IMPORTING_S = 600  # the full archive takes a while: not redone for every processed replay
FIRST_WAIT_S = 20  # a request needing a ranking that does not exist yet waits this long for it, then gets "try again"
_cache: dict[int, tuple[tuple, float, dict]] = {}  # id(sessions) -> (key, computed at, data)
_refreshing: set[int] = set()
_lock = threading.Lock()


# id(sessions) -> player_id -> [(fingerprint, window), progress per rule, overall, medal times or None]. A new
# replay changes the games of ~8 players: only those are evaluated again (all 8k players take ~15 s).
_evaluated: dict[int, dict[int, list]] = {}


def _cache_file(sessions) -> Path | None:
    try:
        database = sessions.kw["bind"].url.database
    except Exception:  # noqa: BLE001
        return None
    return Path(database).with_name("achievements-cache.pkl") if database else None


@functools.cache
def _code_signature() -> str:
    digest = hashlib.sha1()
    for source in (engine.__file__, gear_tables.__file__, __file__):
        try:
            digest.update(Path(source).read_bytes().replace(b"\r\n", b"\n"))
        except OSError:  # no source beside the module: never reuse results across starts
            digest.update(repr(time.time()).encode())
    return digest.hexdigest()


def _signature() -> str:
    """Results are only reused while what produced them is the same: the rules, and the code that reads the games and
    evaluates them (achievements.py, this file, the gear tables). Not the app version: until 2026-11-10 every update
    of the site threw the results away, and the first ranking after each one evaluated all 8,600 players again
    (72 s of CPU on the dev PC, minutes on the NAS, with the website stalling meanwhile)."""
    rules = repr([(r.id, r.levels, r.period, r.description) for r in RULES])
    return f"{_code_signature()}|{hashlib.sha1(rules.encode()).hexdigest()}"


def _load_results(sessions) -> dict[int, list]:
    """Per-player results kept from the last run (so a restart only evaluates players whose games changed)."""
    path = _cache_file(sessions)
    try:
        with open(path, "rb") as f:
            signature, entries = pickle.load(f)
        return entries if signature == _signature() else {}
    except Exception:  # noqa: BLE001 - missing, damaged or from another version: start over
        return {}


def _save_results(sessions, entries: dict[int, list]) -> None:
    path = _cache_file(sessions)
    if path is None:
        return
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            # medal times too (entry[3], filled for players active lately): without them a restart worked them out
            # again for every such player (14 of 19 s on the dev PC)
            pickle.dump((_signature(), {pid: list(e[:4]) for pid, e in entries.items()}), f)
        tmp.replace(path)
    except Exception:  # noqa: BLE001 - a cache that cannot be written is just slower next time
        pass


_gc_lock = threading.Lock()
_gc_depth = 0


@contextmanager
def _collector_paused():
    """Python's cycle collector off while the ranking builds its ~600k objects (they hold no cycles and are freed as
    usual): measured on the full archive, 14 full collections (1.4 s, the longest 0.3 s) froze every request
    while it ran, and the build is 17 % faster without them."""
    global _gc_depth
    with _gc_lock:
        _gc_depth += 1
        if _gc_depth == 1:
            gc.disable()
    try:
        yield
    finally:
        with _gc_lock:
            _gc_depth -= 1
            if _gc_depth == 0:
                gc.enable()


def _compute(sessions, window: tuple) -> dict:
    with _collector_paused():
        return _compute_ranking(sessions, window)


# --- helper processes -------------------------------------------------------------------------
# Evaluating achievements is pure Python, and Python runs one thread at a time: while the web server itself built the
# everyone-ranking, every page request waited its turn (measured 2026-11-10 on the dev PC: 16x fewer requests answered,
# stalls of 1.5 s; the NAS is 5-12x slower and showed "Server busy"). So the calculations run in the import worker's
# low-priority side processes (worker.run_side) and the web server only waits for the result.

_offload: dict[int, tuple] = {}  # id(sessions) -> (worker, database path, database cache MB)


def offload(sessions, worker, settings) -> None:
    """Called once at start (main.py). Without it (the tests, workers = 0) everything is calculated in this process."""
    _offload[id(sessions)] = (worker, str(settings.db_path), settings.db_cache_mb)


def stop_offload(sessions) -> None:
    _offload.pop(id(sessions), None)


def _ranking_job(db_path: str, cache_mb: int, window: tuple) -> dict:
    """In the ranking process, which keeps _evaluated between builds: a build after a new replay evaluates ~8 players."""
    return _compute(open_reader(db_path, cache_mb), tuple(window))


def _player_job(db_path: str, cache_mb: int, user_id: str) -> dict | None:
    return _player_result(open_reader(db_path, cache_mb), user_id)


def _elsewhere(sessions, lane: str, job, inline, *args):
    """job(database path, cache MB, *args) in a helper process of `lane` (worker.LANES), waited for here. When there is
    no helper (tests), or it cannot be started or died, inline(sessions, *args) in this process instead: slower for
    everyone, but the answer still comes."""
    target = _offload.get(id(sessions))
    if target is not None:
        worker, db_path, cache_mb = target
        try:
            return worker.run_side(job, db_path, cache_mb, *args, lane=lane).result()
        except (RuntimeError, BrokenProcessPool, CancelledError) as e:
            log.warning("Achievement calculation in a helper process failed (%s); calculating in the web server", e)
    return inline(sessions, *args)


def _compute_ranking(sessions, window: tuple) -> dict:
    fingerprints: dict[int, int] = {}
    with sessions() as db:
        games = {pid: in_window(gs, *window) for pid, gs in _games(db, fingerprints=fingerprints).items()}
        latest = db.scalar(select(func.max(Match.started_at)))
        people = {pid: (uid, name) for pid, uid, name in db.execute(select(Player.id, Player.user_id, Player.name))}
    previous = _evaluated.get(id(sessions))
    if previous is None:
        previous = _load_results(sessions)
    changed = False
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
            changed = True
        evaluated[pid] = entry
        progress[pid] = entry[1]
        rows.append((pid, len(gs), entry[2]))
    _evaluated[id(sessions)] = evaluated
    untimed = sum(1 for e in evaluated.values() if e[3] is None)
    recent = _recent(games, latest, people, evaluated)
    if changed or untimed != sum(1 for e in evaluated.values() if e[3] is None):
        _save_results(sessions, evaluated)
    return {"rows": rows, "progress": progress, "recent": recent}


def _recent(games: dict[int, list[Game]], latest: str | None, people: dict, evaluated: dict[int, list]) -> list[dict]:
    """Every medal earned in the last RECENT_DAYS of the archive (bronze ... platinum; a single-step challenge when
    completed, medal None), newest first, with the time of the game that earned it."""
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
            entry[3] = medal_times(gs)
        for rule_id, medals in entry[3].items():
            for medal, at in medals.items():
                if at[:10] >= cutoff:
                    uid, name = people[pid]
                    events.append({"date": at[:10], "at": at, "user_id": uid, "name": name, "id": rule_id, "medal": medal,
                                   "achievement": rules[rule_id].name, "description": rules[rule_id].description, "icon": icon_file(rules[rule_id])})
    events.sort(key=lambda e: e["at"], reverse=True)
    return events


_compute_lock = threading.Lock()


def _store(sessions, key: tuple) -> dict:
    """One computation at a time: requests that arrive while it runs wait for it (the page asks three things at once)."""
    with _compute_lock:
        cached = _cache.get(id(sessions))
        if cached and cached[0] == key:
            return cached[2]
        data = _elsewhere(sessions, "ranking", _ranking_job, _compute, key[1])
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
    stamp = current_stamp(sessions)
    with sessions() as db:
        return stamp, counted_window(db)


def warm(sessions, previews: bool = False) -> None:
    """Fill the cache at startup so the first achievements / leaderboard visit does not wait."""
    with sessions() as db:
        if not achievements_launched(db) and not previews:
            return  # nobody can see anything before the start date
    _refresh_in_background(sessions, _key(sessions))


def _everyone(request: Request) -> dict:
    """{"rows": [(player_id, games, overall)], "progress": {player_id: [progress per rule]}, "recent": [...]}
    within the challenge period. New data: the previous result is served at once and recomputed in the
    background, at most every ECHOVR_CACHE_REFRESH_S (every 10 minutes while an import is running). Only the very
    first request and a challenge-period change wait for the computation."""
    sessions = request.app.state.sessionmaker
    key = _key(sessions)
    cached = _cache.get(id(sessions))
    if cached and cached[0] == key:
        return cached[2]
    if cached and cached[0][1] == key[1]:
        reuse = max(request.app.state.settings.cache_refresh_s,
                    REUSE_WHILE_IMPORTING_S if request.app.state.worker.busy else 0)
        if time.monotonic() - cached[1] >= reuse:
            _refresh_in_background(sessions, key)
        return cached[2]
    if id(sessions) not in _offload:
        return _store(sessions, key)  # no helper process (tests): calculated here, the request waits
    # No ranking yet (just started, or the challenge period changed): it is calculated in the background. Wait a little,
    # then say so: a request held for the minutes a first build can take on the NAS only ties up a server thread
    # (the page gives up after 30 s anyway, api.ts)
    _refresh_in_background(sessions, key)
    deadline = time.monotonic() + FIRST_WAIT_S
    while time.monotonic() < deadline:
        cached = _cache.get(id(sessions))
        if cached and cached[0][1] == key[1]:
            return cached[2]
        time.sleep(0.1)
    raise ApiError(503, "ranking_building", "The achievement ranking is being calculated. Try again in a minute.")


def _ready_or_start(request: Request) -> dict | None:
    """The ranking if there is one (stale is fine); otherwise start calculating it in the background and say "not yet"
    instead of making the page wait for it."""
    sessions = request.app.state.sessionmaker
    if id(sessions) in _cache:
        return _everyone(request)
    _refresh_in_background(sessions, _key(sessions))
    return None


def achievement_ranking(request: Request) -> list[tuple[int, int, float]]:
    return _everyone(request)["rows"]


def achievement_progress(request: Request) -> dict[int, list[float]]:
    """player_id -> progress per rule (same order as RULES), from the same cached computation as the ranking."""
    return _everyone(request)["progress"]


@router.get("/api/achievements")
def list_achievements(request: Request):
    """The rule catalogue with rarity: share of players (10+ games) who unlocked (25 %+, tiered: bronze) / completed each."""
    require_launched(request)
    data = _ready_or_start(request) or {"rows": [], "progress": {}}  # no shares yet: the list itself is quick
    eligible = [data["progress"][pid] for pid, games, _ in data["rows"] if games >= RARITY_MIN_GAMES]
    out = []
    for i, r in enumerate(RULES):
        values = [p[i] for p in eligible]
        out.append({"id": r.id, "name": r.name, "description": r.description, "rules": rule_notes(r), "period": r.period,
                    "icon": icon_file(r), "estimated": r.estimated, "new": r.new, "group": r.group, "counted": r.counted,
                    "levels": list(r.levels) or None,  # ladder: targets for bronze ... platinum
                    "unit": r.unit,
                    "unlocked_share": round(sum(v >= unlock_threshold(r) for v in values) / len(values), 4) if values else None,
                    "completed_share": round(sum(v >= 1 for v in values) / len(values), 4) if values else None})
    with request.app.state.sessionmaker() as db:
        window = counted_window(db)
        return icons.apply(db, out + combat_achievements.catalogue(request.app.state.sessionmaker, window))


@router.get("/api/achievements/recent")
def recent_unlocks(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Latest 100 % completions by players active in the last 30 days of the archive."""
    require_launched(request)
    with request.app.state.sessionmaker() as db:
        window = counted_window(db)
        combat = combat_achievements.recent(request.app.state.sessionmaker, window)
        replay = (_ready_or_start(request) or {"recent": []})["recent"]
        merged = sorted(replay[:limit] + combat[:limit], key=lambda e: e["at"], reverse=True)
        return icons.apply(db, merged[:limit])
