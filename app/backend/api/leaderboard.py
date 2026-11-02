"""Leaderboard (D15): the profile aggregates grouped by player, ranked by one stat."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, func, select

from .. import visibility
from ..cache import cached, cached_response
from ..duplicates import counted
from ..errors import ApiError
from ..gear import ORDNANCES, TACMODS, WEAPONS
from ..models import Match, MatchPlayer, MatchPlayerLoadout, Player
from .achievements import achievement_ranking, require_launched, visible
from .derived import MAP_PATTERN, PERIODS, gear, period_start, ratio

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

WIN_LOSS_STATS = ("wins", "win_rate")  # left out while win-loss stats are hidden (visibility.py)
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


def _where(period, map, private, shift_days: int = 0):
    """Match filter; shift_days moves the window back (for rank changes): period windows move back one period,
    all-time stops `shift_days` ago."""
    conditions = [counted(Match.id)]  # duplicate recordings left out (D13)
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
    return and_(True, *conditions)


def _aggregate_rows(db, request, period, map, private, shift_days: int = 0):
    # one scan computes every stat: keep the rows per filter set so switching the stat (or asking for the rank
    # change arrows, or the per-player summary columns) does not scan the archive again
    return cached(request, "leaderboard-aggregate", (period, map, private, shift_days),
                  lambda: db.execute(_aggregate(_where(period, map, private, shift_days))).all())


def _summary(r, wl: bool = True, player_shown: bool = True) -> dict:
    """Context columns shown beside every leaderboard row, whatever the ranked stat. wl: win-loss shown site-wide;
    player_shown: not hidden for this player (their columns are empty then)."""
    if not wl:
        return {"hours_played": STATS["hours_played"][2](r)}
    if not player_shown:
        return {"wins": None, "losses": None, "win_rate": None, "hours_played": STATS["hours_played"][2](r)}
    return {"wins": r.wins or 0, "losses": r.losses or 0,
            "win_rate": STATS["win_rate"][2](r), "hours_played": STATS["hours_played"][2](r)}


def _values(db, request, stat, period, map, private, weapon, tacmod, ordnance, shift_days: int = 0):
    """(label, higher_is_better, [(player_id, games, value)]); shift_days as in _where."""
    where = _where(period, map, private, shift_days)
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
    rows = _aggregate_rows(db, request, period, map, private, shift_days)
    return label, higher, [(r.player_id, r.games, value_of(r)) for r in rows]


def _rank(values, higher: bool, min_games: int) -> list[tuple[int, int, float]]:
    eligible = [v for v in values if v[1] >= min_games and v[2] is not None]
    eligible.sort(key=lambda v: (-v[2] if higher else v[2], -v[1]))
    return eligible


SORTS = ("games", "wins", "losses", "win_rate", "hours_played")  # summary columns the # column can be re-ranked by


def _resort(ranking, rows, sort: str | None, wl: bool, hidden) -> list[tuple[int, int, float]]:
    """Re-order the ranked players by a summary column (highest first, empty values last); ties keep the stat order.
    The set of players is unchanged: still the ones eligible for the ranked stat."""
    if not sort:
        return ranking
    if sort == "games":
        def key(v):
            return v[1]  # the games shown in the row (the loadout board counts only games with that gear)
    else:
        column = {r.player_id: _summary(r, wl, r.player_id not in hidden).get(sort) for r in rows}

        def key(v):
            return column.get(v[0])
    return sorted(ranking, key=lambda v: (key(v) is None, -(key(v) or 0)))


@router.get("/stats")
def list_stats(request: Request):
    launched = visible(request)
    wl = visibility.win_loss(request)
    return [{"key": k, "label": label, "higher_is_better": hib} for k, (label, hib, _) in STATS.items()
            if wl or k not in WIN_LOSS_STATS] + [
        {"key": "loadout", "label": "Loadout time (hours)", "higher_is_better": True},
    ] + ([{"key": "achievements", "label": "Achievements (overall %)", "higher_is_better": True}] if launched else [])


@router.get("")
def leaderboard(
    request: Request,
    stat: str = "games",
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    map: str | None = Query(None, pattern=MAP_PATTERN),
    private: bool | None = Query(None, description="true / false; omit for all matches (old app had no filter)"),
    min_games: int = Query(10, ge=1, le=100_000),
    weapon: str | None = None,
    tacmod: str | None = None,
    ordnance: str | None = None,
    compare: bool = Query(False, description="add previous_rank: same board one period earlier"),
    sort: str | None = Query(None, description="rank by this summary column instead of the stat: " + ", ".join(SORTS)),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if stat not in STATS and stat not in ("loadout", "achievements"):
        raise ApiError(400, "unknown_stat", f"Unknown stat '{stat}'")
    if sort is not None and sort not in SORTS:
        raise ApiError(400, "unknown_sort", f"Unknown sort column '{sort[:32]}'")
    if sort == stat:
        sort = None  # the stat's own order
    v = visibility.view(request)
    wl = not v.everything
    if (stat in WIN_LOSS_STATS or sort in WIN_LOSS_STATS + ("losses",)) and not wl:
        raise ApiError(404, "stat_hidden", "This stat is hidden")
    for value, table, what in ((weapon, WEAPONS, "weapon"), (tacmod, TACMODS, "tac mod"), (ordnance, ORDNANCES, "ordnance")):
        if value is not None and value not in table:
            raise ApiError(400, "unknown_gear", f"Unknown {what} '{value[:32]}'")
    params = (stat, period, map, private, min_games, weapon, tacmod, ordnance, compare, limit, offset, v, sort)
    if stat == "achievements":  # has its own background-refreshed cache
        require_launched(request)
        return _leaderboard(request, *params)
    return cached_response(request, "leaderboard", params, lambda: _leaderboard(request, *params))


def _leaderboard(request, stat, period, map, private, min_games, weapon, tacmod, ordnance, compare, limit, offset,
                 v: visibility.View = visibility.ALL_SHOWN, sort: str | None = None):
    wl = not v.everything
    with request.app.state.sessionmaker() as db:
        hidden = visibility.hidden_player_ids(db, v)  # hidden one by one
        label, higher, values = _values(db, request, stat, period, map, private, weapon, tacmod, ordnance)
        if stat in WIN_LOSS_STATS and hidden:
            values = [x for x in values if x[0] not in hidden]
        previous = {}
        if compare and stat != "achievements":
            _, _, before = _values(db, request, stat, period, map, private, weapon, tacmod, ordnance, shift_days=7)
            if stat in WIN_LOSS_STATS and hidden:
                before = [x for x in before if x[0] not in hidden]
            before_rows = _aggregate_rows(db, request, period, map, private, 7) if sort else []
            previous = {pid: i + 1 for i, (pid, _, _) in
                        enumerate(_resort(_rank(before, higher, min_games), before_rows, sort, wl, hidden))}
        ranking = _rank(values, higher, min_games)
        if sort:
            ranking = _resort(ranking, _aggregate_rows(db, request, period, map, private), sort, wl, hidden)
        page = ranking[offset : offset + limit]
        people = {pid: (name, user_id) for pid, name, user_id in
                  db.execute(select(Player.id, Player.name, Player.user_id).where(Player.id.in_([pid for pid, _, _ in page])))}
        on_page = {pid for pid, _, _ in page}
        summary = {r.player_id: _summary(r, wl, r.player_id not in hidden) for r in _aggregate_rows(db, request, period, map, private) if r.player_id in on_page}

    empty = {"wins": None, "losses": None, "win_rate": None, "hours_played": None} if wl else {"hours_played": None}
    ranked = [
        {"rank": offset + i + 1, "user_id": people[pid][1], "name": people[pid][0], "games": games, "value": value,
         "previous_rank": previous.get(pid) if compare else None,
         # same period / map, all modes and gear: the loadout board's `games` counts only games with that gear
         **summary.get(pid, empty)}
        for i, (pid, games, value) in enumerate(page)
    ]
    result = {
        "stat": stat, "label": label, "higher_is_better": higher, "sort": sort, "period": period, "map": map,
        "min_games": min_games, "total": len(ranking), "items": ranked,
        # biggest value on the whole board (not just this page): the bars in the value column are scaled to it
        "max_value": max((v for _, _, v in ranking), default=None),
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
