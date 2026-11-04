"""Combat stats endpoints (user, 2026-11-04): the game's own counters and the event-log numbers from the recorder's match
reports. Own tables and own routes, completely separate from the replay-derived stats (matches, players, heatmaps).

Numbers that are not available are left out or null, never 0: damage taken is never given to spectators, and the event
numbers (shots, weapons, tac mod use...) exist only for matches that had an event log (and are too low when that log
ended early: `events_incomplete`)."""

import json
from collections import Counter

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import case, func, select

from ..aliases import ids_of
from ..errors import ApiError
from ..gear import ORDNANCES, WEAPONS
from ..models import CombatMatch, CombatPlayer, PlayerAlias
from .derived import MAP_PATTERN, PERIODS, ID_MAX, period_start, ratio

router = APIRouter(prefix="/api/combat", tags=["combat"])

PERIOD_PATTERN = "^(" + "|".join(PERIODS) + ")$"
USER_PATH = Path(pattern=f"^[0-9]{{1,{ID_MAX}}}$")
SESSION_PATH = Path(pattern="^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
RECENT_MATCHES = 20
MIN_GAMES_DEFAULT = 3

# stat key -> (label, higher is better, hint)
STATS: dict[str, tuple[str, bool, str]] = {
    "kills": ("Kills", True, "Kills of other players, as the game counts them (self-kills are not included)."),
    "deaths": ("Deaths", False, "Deaths, including self-kills."),
    "assists": ("Assists", True, ""),
    "eliminations": ("Eliminations", True, "The game's own elimination counter; usually higher than kills."),
    "damage": ("Damage", True, "Damage dealt, in game units."),
    "objective_damage": ("Objective damage", True, "Damage to the payload / objective (payload maps)."),
    "objective_time": ("Objective time", True, "Seconds on the objective (payload maps)."),
    "kd": ("Kills / deaths", True, "Kills divided by deaths."),
    "kills_per_min": ("Kills per minute", True, "Kills per minute played."),
    "damage_per_min": ("Damage per minute", True, "Damage dealt per minute played."),
    "matches": ("Matches", True, ""),
}


def weapon_name(code: str) -> str:
    """The in-game name of a weapon / ordnance symbol: assault -> Pulsar, r15_ord_det -> Detonator, scout_aoe -> Comet blast.
    Anything unknown keeps its symbol, tidied up (a raw 0x... hash stays as it is)."""
    if code.startswith("0x"):
        return code
    base, suffix = code, ""
    for tail, label in (("_aoe", " blast"), ("_cone", " cone")):
        if base.endswith(tail):
            base, suffix = base[: -len(tail)], label
    key = base.removeprefix("r15_ord_")
    gear = WEAPONS.get(key) or ORDNANCES.get(key)
    return (gear.display_name if gear else key.replace("_", " ").capitalize()) + suffix


def _weapons(counts: Counter) -> list[dict]:
    return [{"code": c, "name": weapon_name(c), "count": n} for c, n in counts.most_common()]


def _main_user(db, user_id: str) -> str:
    """A merged (alias) id answers with its main player (D34)."""
    return db.scalar(select(PlayerAlias.main_user_id).where(PlayerAlias.alias_user_id == user_id)) or user_id


def _where(ids: set[str], period: str, map_: str | None):
    where = [CombatPlayer.user_id.in_(ids)]
    if start := period_start(period):
        where.append(CombatMatch.started_at >= start)
    if map_:
        where.append(CombatMatch.map == map_)
    return where


def _json(text: str | None) -> dict:
    try:
        value = json.loads(text) if text else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _rates(t: dict) -> dict:
    minutes = (t["present_s"] or 0) / 60
    t["kd"] = ratio(t["kills"], t["deaths"], 2) if t["deaths"] else (float(t["kills"]) if t["kills"] else None)
    t["kills_per_min"] = ratio(t["kills"], minutes, 3)
    t["damage_per_min"] = ratio(t["damage"], minutes, 1)
    return t


@router.get("/summary")
def summary(request: Request):
    with request.app.state.sessionmaker() as db:
        matches, last, events = db.execute(select(func.count(), func.max(CombatMatch.started_at),
                                                  func.sum(case((CombatMatch.has_events, 1), else_=0)))).one()
        players = db.scalar(select(func.count(func.distinct(CombatPlayer.user_id))))
    return {"matches": matches, "players": players, "matches_with_events": int(events or 0), "last_match_at": last}


@router.get("/stats")
def stat_options():
    return [{"key": k, "label": label, "higher_is_better": better, "hint": hint} for k, (label, better, hint) in STATS.items()]


@router.get("/players/{user_id}")
def player(request: Request, user_id: str = USER_PATH, period: str = Query("all", pattern=PERIOD_PATTERN),
           map: str | None = Query(None, pattern=MAP_PATTERN)):
    with request.app.state.sessionmaker() as db:
        main = _main_user(db, user_id)
        where = _where(ids_of(db, main), period, map)
        s = func.sum
        row = db.execute(
            select(func.count(), s(CombatPlayer.present_s), s(CombatPlayer.kills), s(CombatPlayer.assists), s(CombatPlayer.deaths),
                   s(CombatPlayer.eliminations), s(CombatPlayer.damage), s(CombatPlayer.objective_eliminations),
                   s(CombatPlayer.objective_damage), s(CombatPlayer.objective_time), s(CombatPlayer.hill_captures),
                   s(CombatPlayer.hill_defends))
            .select_from(CombatPlayer).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id).where(*where)).one()
        games = row[0]
        if not games:
            return {"user_id": main, "name": None, "matches": 0}
        keys = ("present_s", "kills", "assists", "deaths", "eliminations", "damage", "objective_eliminations",
                "objective_damage", "objective_time", "hill_captures", "hill_defends")
        totals = {k: (round(v, 3) if isinstance(v, float) else int(v or 0)) for k, v in zip(keys, row[1:12])}
        stats = _rates({"matches": games, **totals})

        by_map = [{"map": m, "matches": n, "kills": int(k or 0), "deaths": int(d or 0), "assists": int(a or 0),
                   "damage": round(dm or 0, 1), "objective_damage": round(od or 0, 1)}
                  for m, n, k, d, a, dm, od in db.execute(
                      select(CombatMatch.map, func.count(), s(CombatPlayer.kills), s(CombatPlayer.deaths), s(CombatPlayer.assists),
                             s(CombatPlayer.damage), s(CombatPlayer.objective_damage))
                      .select_from(CombatPlayer).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
                      .where(*where).group_by(CombatMatch.map).order_by(func.count().desc()))]

        # event-log numbers: only matches that had one; per-weapon counts are added up here (small JSON per match)
        ev = {"matches": 0, "incomplete": 0}
        sums, shots, kills, deaths = Counter(), Counter(), Counter(), Counter()
        for p, complete in db.execute(
                select(CombatPlayer, CombatMatch.events_complete).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
                .where(*where, CombatPlayer.shots.is_not(None))):
            ev["matches"] += 1
            ev["incomplete"] += complete is False
            for k in ("shots", "tacmod_activations", "heal_bubbles", "stuns_given", "stuns_received", "self_kills"):
                sums[k] += getattr(p, k) or 0
            shots.update(_json(p.shots_by_weapon))
            kills.update(_json(p.kills_by_weapon))
            deaths.update(_json(p.deaths_by_weapon))
        events = None
        if ev["matches"]:
            events = {"matches": ev["matches"], "events_incomplete": ev["incomplete"], **sums,
                      "shots_by_weapon": _weapons(shots), "kills_by_weapon": _weapons(kills), "deaths_by_weapon": _weapons(deaths)}

        recent = [{"session_id": m.session_id, "map": m.map, "started_at": m.started_at, "duration_s": m.duration_s,
                   "team": p.team, "kills": p.kills, "deaths": p.deaths, "assists": p.assists, "damage": round(p.damage, 1),
                   "objective_damage": round(p.objective_damage, 1)}
                  for p, m in db.execute(select(CombatPlayer, CombatMatch).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
                                         .where(*where).order_by(CombatMatch.started_at.desc()).limit(RECENT_MATCHES))]
        name = db.scalar(select(CombatPlayer.name).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
                         .where(CombatPlayer.user_id.in_(ids_of(db, main))).order_by(CombatMatch.started_at.desc()).limit(1))
    return {"user_id": main, "name": name, "matches": games, "stats": stats, "by_map": by_map, "events": events, "recent": recent}


@router.get("/leaderboard")
def leaderboard(request: Request, stat: str = Query("kills", pattern="^(" + "|".join(STATS) + ")$"),
                period: str = Query("all", pattern=PERIOD_PATTERN), map: str | None = Query(None, pattern=MAP_PATTERN),
                min_games: int = Query(MIN_GAMES_DEFAULT, ge=1, le=1000), limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0)):
    s = func.sum
    where = []
    if start := period_start(period):
        where.append(CombatMatch.started_at >= start)
    if map:
        where.append(CombatMatch.map == map)
    with request.app.state.sessionmaker() as db:
        aliases = dict(db.execute(select(PlayerAlias.alias_user_id, PlayerAlias.main_user_id)).all())
        groups: dict[str, dict] = {}
        # bare name with max(): SQLite gives the name of the newest row
        for uid, name, last, n, *vals in db.execute(
                select(CombatPlayer.user_id, CombatPlayer.name, func.max(CombatMatch.started_at), func.count(),
                       s(CombatPlayer.present_s), s(CombatPlayer.kills), s(CombatPlayer.assists), s(CombatPlayer.deaths),
                       s(CombatPlayer.eliminations), s(CombatPlayer.damage), s(CombatPlayer.objective_damage),
                       s(CombatPlayer.objective_time))
                .select_from(CombatPlayer).join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
                .where(*where).group_by(CombatPlayer.user_id)):
            main = aliases.get(uid, uid)
            g = groups.setdefault(main, {"user_id": main, "name": name, "last": last, "matches": 0, "present_s": 0.0, "kills": 0,
                                         "assists": 0, "deaths": 0, "eliminations": 0, "damage": 0.0, "objective_damage": 0.0,
                                         "objective_time": 0.0})
            if last >= g["last"]:
                g["name"], g["last"] = name, last
            g["matches"] += n
            for k, v in zip(("present_s", "kills", "assists", "deaths", "eliminations", "damage", "objective_damage", "objective_time"), vals):
                g[k] += v or 0
    rows = [_rates(g) for g in groups.values() if g["matches"] >= min_games]
    better = STATS[stat][1]
    rows = [r for r in rows if r.get(stat) is not None]
    rows.sort(key=lambda r: r["name"].lower())
    rows.sort(key=lambda r: r[stat], reverse=better)  # stable: ties stay in name order
    total = len(rows)
    items = [{"rank": offset + i + 1, "user_id": r["user_id"], "name": r["name"], "matches": r["matches"], "value": round(r[stat], 3) if isinstance(r[stat], float) else r[stat],
              "kills": r["kills"], "deaths": r["deaths"], "assists": r["assists"], "damage": round(r["damage"], 1), "kd": r["kd"]}
             for i, r in enumerate(rows[offset: offset + limit])]
    return {"stat": stat, "label": STATS[stat][0], "higher_is_better": better, "items": items, "total": total}


@router.get("/matches")
def matches(request: Request, limit: int = Query(30, ge=1, le=200), offset: int = Query(0, ge=0),
            map: str | None = Query(None, pattern=MAP_PATTERN)):
    where = [CombatMatch.map == map] if map else []
    with request.app.state.sessionmaker() as db:
        total = db.scalar(select(func.count()).select_from(CombatMatch).where(*where))
        rows = db.execute(
            select(CombatMatch, func.count(CombatPlayer.user_id), func.sum(CombatPlayer.kills), func.sum(CombatPlayer.damage))
            .outerjoin(CombatPlayer, CombatPlayer.match_id == CombatMatch.id).where(*where).group_by(CombatMatch.id)
            .order_by(CombatMatch.started_at.desc()).limit(limit).offset(offset)).all()
    items = [{"session_id": m.session_id, "map": m.map, "started_at": m.started_at, "duration_s": m.duration_s,
              "players": n, "kills": int(k or 0), "damage": round(d or 0, 1), "has_events": m.has_events} for m, n, k, d in rows]
    return {"items": items, "total": total}


@router.get("/matches/{session_id}")
def match(request: Request, session_id: str = SESSION_PATH):
    with request.app.state.sessionmaker() as db:
        m = db.scalar(select(CombatMatch).where(CombatMatch.session_id == session_id.upper()))
        if m is None:
            raise ApiError(404, "not_found", "No combat stats for this match")
        rows = db.scalars(select(CombatPlayer).where(CombatPlayer.match_id == m.id)
                          .order_by(CombatPlayer.team, CombatPlayer.kills.desc(), CombatPlayer.name)).all()
    players = []
    for p in rows:
        events = None
        if p.shots is not None:
            events = {"shots": p.shots, "tacmod_activations": p.tacmod_activations, "heal_bubbles": p.heal_bubbles,
                      "stuns_given": p.stuns_given, "stuns_received": p.stuns_received, "self_kills": p.self_kills,
                      "shots_by_weapon": _weapons(Counter(_json(p.shots_by_weapon))),
                      "kills_by_weapon": _weapons(Counter(_json(p.kills_by_weapon))),
                      "deaths_by_weapon": _weapons(Counter(_json(p.deaths_by_weapon)))}
        loadouts = _json(p.loadouts)
        players.append({"user_id": p.user_id, "name": p.name, "team": p.team, "present_s": p.present_s, "kills": p.kills,
                        "assists": p.assists, "deaths": p.deaths, "eliminations": p.eliminations, "damage": round(p.damage, 1),
                        "objective_eliminations": p.objective_eliminations, "objective_damage": round(p.objective_damage, 1),
                        "objective_time": round(p.objective_time, 1), "hill_captures": p.hill_captures, "hill_defends": p.hill_defends,
                        "weapons": [weapon_name(w) for w in loadouts.get("weapons", [])],
                        "tacmods": loadouts.get("tacmods", []), "ordnance": [weapon_name(w) for w in loadouts.get("ordnance", [])],
                        "events": events})
    return {"session_id": m.session_id, "map": m.map, "started_at": m.started_at, "ended_at": m.ended_at, "duration_s": m.duration_s,
            "has_events": m.has_events, "events_complete": m.events_complete, "teams": _json(m.teams), "players": players}
