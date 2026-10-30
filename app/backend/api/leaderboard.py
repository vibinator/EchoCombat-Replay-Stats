"""Leaderboard (D15): the profile aggregates grouped by player, ranked by one stat."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, func, select

from ..cache import cached
from ..errors import ApiError
from ..gear import ORDNANCES, TACMODS, WEAPONS
from ..models import Match, MatchPlayer, MatchPlayerLoadout, Player
from .achievements import achievement_ranking, require_launched, visible
from .derived import PERIODS, gear, period_start, ratio

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

# stat -> (label, higher_is_better, value from the aggregate row)
STATS = {
    "games": ("Games", True, lambda r: r.games),
    "wins": ("Wins", True, lambda r: r.wins),
    "win_rate": ("Win rate", True, lambda r: ratio(r.wins, (r.wins or 0) + (r.losses or 0))),
    "hours_played": ("Hours played", True, lambda r: round((r.play_time or 0) / 3600, 2)),
    "deaths_per_game_est": ("Deaths per game (est.)", False, lambda r: ratio(r.deaths, r.games, 2)),
    "avg_speed": ("Average speed", True, lambda r: ratio(r.speed_sum, r.in_bounds, 2)),
    "top_speed": ("Top speed", True, lambda r: round(r.top_speed or 0, 2)),
    "pct_stopped": ("Time idle", False, lambda r: ratio(r.stopped, r.in_bounds)),
    "pct_upside_down": ("Inverted", True, lambda r: ratio(r.upside, r.in_bounds)),
    "pct_near_mate": ("Near a teammate", True, lambda r: ratio(r.mate, r.in_bounds)),
    "pct_near_enemy": ("Near an enemy", True, lambda r: ratio(r.enemy, r.in_bounds)),
    "avg_ping": ("Average ping", False, lambda r: ratio(r.ping_sum, r.ping_frames, 1)),
    "payload_push_s": ("Payload push time (est.)", True, lambda r: round(r.push or 0, 1)),
    "payload_block_s": ("Payload block time (est.)", True, lambda r: round(r.block or 0, 1)),
    "emote_count": ("Emotes", True, lambda r: r.emotes or 0),
}


def _aggregate(where):
    s = func.sum
    won = case((Match.winner == MatchPlayer.team, 1), else_=0)
    lost = case((and_(Match.winner.is_not(None), Match.winner != MatchPlayer.team), 1), else_=0)
    return (
        select(
            MatchPlayer.player_id, func.count().label("games"), s(won).label("wins"), s(lost).label("losses"),
            s(MatchPlayer.deaths_est).label("deaths"), s(MatchPlayer.play_time_s).label("play_time"),
            s(MatchPlayer.speed_sum).label("speed_sum"), s(MatchPlayer.frames_in_bounds).label("in_bounds"),
            func.max(MatchPlayer.top_speed).label("top_speed"),
            s(MatchPlayer.ping_sum).label("ping_sum"), s(MatchPlayer.ping_frames).label("ping_frames"),
            s(MatchPlayer.frames_stopped).label("stopped"), s(MatchPlayer.frames_upside_down).label("upside"),
            s(MatchPlayer.frames_near_mate).label("mate"), s(MatchPlayer.frames_near_enemy).label("enemy"),
            s(MatchPlayer.payload_push_s).label("push"), s(MatchPlayer.payload_block_s).label("block"),
            s(MatchPlayer.emote_count).label("emotes"),
        )
        .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
        .where(where).group_by(MatchPlayer.player_id)
    )


def _values(db, request, stat, period, map, private, weapon, tacmod, ordnance, shift_days: int = 0):
    """(label, higher_is_better, [(player_id, games, value)]); shift_days moves the window back
    (for rank changes): period windows move back one period, all-time stops `shift_days` ago."""
    conditions = []
    start = period_start(period)
    if shift_days:
        today = datetime.now().date()
        if period == "all":
            conditions.append(Match.started_at < (today - timedelta(days=shift_days)).isoformat())
        else:
            prev_end = date.fromisoformat(start)
            prev_start = {"day": prev_end - timedelta(days=1), "week": prev_end - timedelta(days=7),
                          "month": (prev_end - timedelta(days=1)).replace(day=1)}[period]
            conditions += [Match.started_at >= prev_start.isoformat(), Match.started_at < prev_end.isoformat()]
            start = None
    if start:
        conditions.append(Match.started_at >= start)
    if map:
        conditions.append(Match.map == map)
    if private is not None:
        conditions.append(Match.private_match == private)
    where = and_(True, *conditions)
    if stat == "achievements":
        return "Achievements (overall %)", True, achievement_ranking(request)  # career-wide, not shifted
    if stat == "loadout":
        lo_where = [where]
        for column, value in ((MatchPlayerLoadout.weapon, weapon), (MatchPlayerLoadout.tacmod, tacmod),
                              (MatchPlayerLoadout.ordnance, ordnance)):
            if value is not None:
                lo_where.append(column == value)
        rows = db.execute(
            select(MatchPlayerLoadout.player_id,
                   func.count(func.distinct(MatchPlayerLoadout.match_id)).label("games"),
                   func.sum(MatchPlayerLoadout.frames / Match.frame_rate_hz).label("seconds"))
            .join(Match, Match.id == MatchPlayerLoadout.match_id)
            .where(and_(*lo_where)).group_by(MatchPlayerLoadout.player_id)
        ).all()
        return "Loadout time (hours)", True, [(r.player_id, r.games, round((r.seconds or 0) / 3600, 3)) for r in rows]
    label, higher, value_of = STATS[stat]
    return label, higher, [(r.player_id, r.games, value_of(r)) for r in db.execute(_aggregate(where)).all()]


def _rank(values, higher: bool, min_games: int) -> list[tuple[int, int, float]]:
    eligible = [v for v in values if v[1] >= min_games and v[2] is not None]
    eligible.sort(key=lambda v: (-v[2] if higher else v[2], -v[1]))
    return eligible


@router.get("/stats")
def list_stats(request: Request):
    launched = visible(request)
    return [{"key": k, "label": label, "higher_is_better": hib} for k, (label, hib, _) in STATS.items()] + [
        {"key": "loadout", "label": "Loadout time (hours)", "higher_is_better": True},
    ] + ([{"key": "achievements", "label": "Achievements (overall %)", "higher_is_better": True}] if launched else [])


@router.get("")
def leaderboard(
    request: Request,
    stat: str = "games",
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    map: str | None = None,
    private: bool | None = Query(None, description="true / false; omit for all matches (old app had no filter)"),
    min_games: int = Query(10, ge=1),
    weapon: str | None = None,
    tacmod: str | None = None,
    ordnance: str | None = None,
    compare: bool = Query(False, description="add previous_rank: same board one period earlier"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if stat not in STATS and stat not in ("loadout", "achievements"):
        raise ApiError(400, "unknown_stat", f"Unknown stat '{stat}'")
    params = (stat, period, map, private, min_games, weapon, tacmod, ordnance, compare, limit, offset)
    if stat == "achievements":  # has its own background-refreshed cache
        require_launched(request)
        return _leaderboard(request, *params)
    return cached(request, "leaderboard", params, lambda: _leaderboard(request, *params))


def _leaderboard(request, stat, period, map, private, min_games, weapon, tacmod, ordnance, compare, limit, offset):
    with request.app.state.sessionmaker() as db:
        names = dict(db.execute(select(Player.id, Player.name)).all())
        user_ids = dict(db.execute(select(Player.id, Player.user_id)).all())
        label, higher, values = _values(db, request, stat, period, map, private, weapon, tacmod, ordnance)
        previous = {}
        if compare and stat != "achievements":
            _, _, before = _values(db, request, stat, period, map, private, weapon, tacmod, ordnance, shift_days=7)
            previous = {pid: i + 1 for i, (pid, _, _) in enumerate(_rank(before, higher, min_games))}

    ranked = [
        {"rank": i + 1, "user_id": user_ids[pid], "name": names[pid], "games": games, "value": value,
         "previous_rank": previous.get(pid) if compare else None}
        for i, (pid, games, value) in enumerate(_rank(values, higher, min_games))
    ]
    result = {
        "stat": stat, "label": label, "higher_is_better": higher, "period": period, "map": map,
        "min_games": min_games, "total": len(ranked), "items": ranked[offset : offset + limit],
    }
    if stat == "loadout":
        result["loadout"] = {
            "weapon": weapon and gear(weapon, WEAPONS), "tacmod": tacmod and gear(tacmod, TACMODS),
            "ordnance": ordnance and gear(ordnance, ORDNANCES),
        }
    return result


@router.get("/gear")
def list_gear():
    """Loadout codes + names, for the loadout leaderboard picker (released first, then cut)."""
    def table(t):
        return [{"code": code, "name": g.display_name, "cut": g.cut} for code, g in sorted(t.items(), key=lambda kv: kv[1].cut)]
    return {"weapons": table(WEAPONS), "tacmods": table(TACMODS), "ordnances": table(ORDNANCES)}
