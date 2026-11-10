import json
from datetime import datetime, timedelta
from collections import Counter

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, func, select

from .. import gear_use, heatmaps, heatmaps3d, tracks, tracks3d, visibility
from ..heatmaps3d import build_layers3d, read_pairs
from ..version import VERSION
from ..aliases import ids_of
from .. import cache
from ..cache import cached, cached_response
from ..duplicates import counted
from ..errors import ApiError
from ..gear import WEAPONS
from ..gear import lookup as gear_lookup
from ..models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player, PlayerAlias, Replay
from ..stats import quality
from ..stats.maps import HEATMAP_LAYOUTS
from .matches import MAPS_3D
from .derived import MAP_PATTERN, PERIODS, TEXT_MAX, dominant_arm, loadout, match_summary, period_start, ratio

router = APIRouter(prefix="/api/players", tags=["players"])

RECENT_MATCHES = 20


def games_of(player_id_column):
    """Correlated count of a player's matches (index on match_players.player_id); duplicate recordings left out (D13)."""
    return (select(func.count()).where(MatchPlayer.player_id == player_id_column, counted(MatchPlayer.match_id))
            .scalar_subquery())


@router.get("")
def search_players(
    request: Request,
    q: str = Query("", max_length=TEXT_MAX),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = q.strip()
    return cached_response(request, "players", (q, limit, offset), lambda: _search_players(request, q, limit, offset))


def _search_players(request: Request, q: str, limit: int, offset: int) -> dict:
    where = [Player.user_id.not_in(select(PlayerAlias.alias_user_id))]
    if q:
        where.append(Player.name.ilike(f"%{q}%"))
    with request.app.state.sessionmaker() as db:
        total = db.scalar(select(func.count()).select_from(Player).where(*where))
        # page first (index on last_seen_at), then count games for those rows only
        rows = db.execute(select(Player, games_of(Player.id)).where(*where)
                          .order_by(Player.last_seen_at.desc()).limit(limit).offset(offset)).all()
    ids = [p.id for p, _ in rows]
    hours: dict[int, float] = {}
    maps: dict[int, dict[str, int]] = {}
    if ids:
        with request.app.state.sessionmaker() as db:
            for pid, secs in db.execute(select(MatchPlayer.player_id, func.sum(MatchPlayer.play_time_s))
                                        .where(MatchPlayer.player_id.in_(ids), counted(MatchPlayer.match_id)).group_by(MatchPlayer.player_id)):
                hours[pid] = round((secs or 0) / 3600, 1)
            for pid, map_, n in db.execute(select(MatchPlayer.player_id, Match.map, func.count()).join(Match, Match.id == MatchPlayer.match_id)
                                           .where(MatchPlayer.player_id.in_(ids), counted(MatchPlayer.match_id))
                                           .group_by(MatchPlayer.player_id, Match.map)):
                maps.setdefault(pid, {})[map_] = n
    items = [{"user_id": p.user_id, "name": p.name, "games": n, "last_seen_at": p.last_seen_at, "hours_played": hours.get(p.id, 0.0),
              "favourite_map": max(maps[p.id], key=maps[p.id].get) if maps.get(p.id) else None} for p, n in rows]
    return {"items": items, "total": total}


def _filters(player_id: int, period: str, map_: str | None):
    conditions = [MatchPlayer.player_id == player_id, counted(MatchPlayer.match_id)]  # duplicates left out (D13)
    if start := period_start(period):
        conditions.append(Match.started_at >= start)
    if map_:
        conditions.append(Match.map == map_)
    return and_(*conditions)


def _profile(db, where, strict: bool = True) -> dict:
    """The profile stat set. Totals (games, hours, emotes, push / block) count every match; averages, rates and
    win rates count only matches that pass stats/quality.py when `strict` (Settings.counted_stats, user 2026-11-07)."""
    s = func.sum
    won = case((Match.winner == MatchPlayer.team, 1), else_=0)
    lost = case((and_(Match.winner.is_not(None), Match.winner != MatchPlayer.team), 1), else_=0)

    def c(expr):
        return quality.only_counted(Match, expr, strict)

    ping = func.coalesce(MatchPlayer.ping_capped_sum, MatchPlayer.ping_sum)  # spikes capped once the replay was read again (DATA-5)
    top = func.max(case((Match.counted_for_stats == 1, MatchPlayer.top_speed), else_=None)) if strict else func.max(MatchPlayer.top_speed)
    row = db.execute(
        select(
            func.count().label("games"), s(c(1)).label("counted"), s(c(won)).label("wins"), s(c(lost)).label("losses"),
            s(c(MatchPlayer.deaths_est)).label("deaths"), s(MatchPlayer.play_time_s).label("play_time"),
            s(c(MatchPlayer.speed_sum)).label("speed_sum"), s(c(MatchPlayer.frames_in_bounds)).label("in_bounds"),
            top.label("top_speed"),
            s(c(ping)).label("ping_sum"), s(c(MatchPlayer.ping_frames)).label("ping_frames"),
            s(c(MatchPlayer.frames_stopped)).label("stopped"), s(c(MatchPlayer.frames_upside_down)).label("upside"),
            s(c(MatchPlayer.frames_near_mate)).label("mate"), s(c(MatchPlayer.frames_near_enemy)).label("enemy"),
            s(MatchPlayer.frames_left_arm).label("left"), s(MatchPlayer.frames_right_arm).label("right"),
            s(c(case((MatchPlayer.left_early, 1), else_=0))).label("left_early"),
            s(MatchPlayer.payload_push_s).label("push"), s(MatchPlayer.payload_block_s).label("block"),
            s(c(MatchPlayer.packet_loss_sum)).label("loss"), s(c(MatchPlayer.frames_present)).label("present"),
            s(MatchPlayer.emote_count).label("emotes"),
        ).select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id).where(where)
    ).one()
    games = row.games or 0
    counted = row.counted or 0  # the denominator of per-game averages
    by_map = dict(db.execute(
        select(Match.map, func.count()).select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
        .where(where).group_by(Match.map)
    ).all())
    by_mode = dict(db.execute(
        select(Match.mode, func.count()).select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
        .where(where).group_by(Match.mode)
    ).all())
    return {
        "games": games,
        "counted_games": counted,  # games behind the averages (stats/quality.py); = games when the rule is off
        "decided_games": (row.wins or 0) + (row.losses or 0),  # games with a recorded winner, behind the win rate
        "wins": row.wins or 0,
        "losses": row.losses or 0,
        "games_by_map": by_map,
        "games_by_mode": by_mode,
        "hours_played": round((row.play_time or 0) / 3600, 2),
        "deaths_est": row.deaths or 0,
        "deaths_per_game_est": ratio(row.deaths, counted, 2),
        "avg_speed": ratio(row.speed_sum, row.in_bounds, 2),
        "top_speed": round(row.top_speed, 2) if row.top_speed is not None else None,
        "avg_ping": ratio(row.ping_sum, row.ping_frames, 1),
        "pct_stopped": ratio(row.stopped, row.in_bounds),
        "pct_upside_down": ratio(row.upside, row.in_bounds),
        "pct_near_mate": ratio(row.mate, row.in_bounds),
        "pct_near_enemy": ratio(row.enemy, row.in_bounds),
        "pct_left_early": ratio(row.left_early, counted),
        "dominant_arm": dominant_arm(row.left or 0, row.right or 0),
        "pct_left_arm": ratio(row.left, (row.left or 0) + (row.right or 0)),
        "payload_push_s": round(row.push or 0, 1),
        "payload_block_s": round(row.block or 0, 1),
        "in_bounds_frames": row.in_bounds or 0,
        "avg_packet_loss": ratio(row.loss, row.present, 5),
        "emote_count": row.emotes or 0,
    }


def _site_averages(request: Request, period: str, map_: str | None) -> dict:
    """Every player's shares over the same period / map, for the "site average" tick on the profile cards. One scan
    of match_players, so it is kept per filter like the leaderboard aggregate."""
    def build():
        conditions = [counted(MatchPlayer.match_id)]
        if start := period_start(period):
            conditions.append(Match.started_at >= start)
        if map_:
            conditions.append(Match.map == map_)
        s = func.sum
        strict = request.app.state.settings.counted_stats

        def c(expr):  # the same counted-game rule as the player's own averages (stats/quality.py)
            return quality.only_counted(Match, expr, strict)

        with request.app.state.sessionmaker() as db:
            row = db.execute(
                select(s(c(1)).label("games"), s(c(MatchPlayer.frames_in_bounds)).label("in_bounds"),
                       s(c(MatchPlayer.frames_stopped)).label("stopped"), s(c(MatchPlayer.frames_upside_down)).label("upside"),
                       s(c(MatchPlayer.frames_near_mate)).label("mate"), s(c(MatchPlayer.frames_near_enemy)).label("enemy"),
                       s(c(case((MatchPlayer.left_early, 1), else_=0))).label("left_early"))
                .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id).where(and_(*conditions))
            ).one()
        return {"pct_stopped": ratio(row.stopped, row.in_bounds), "pct_upside_down": ratio(row.upside, row.in_bounds),
                "pct_near_mate": ratio(row.mate, row.in_bounds), "pct_near_enemy": ratio(row.enemy, row.in_bounds),
                "pct_left_early": ratio(row.left_early, row.games)}
    return cached(request, "site-averages", (period, map_), build)


@router.get("/compare/{user_ids}")
def compare_players(request: Request, user_ids: str, period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$")):
    """Profiles of 2-4 players side by side + head-to-head record of the first two."""
    v = visibility.view(request)
    return cached_response(request, "compare", (user_ids, period, v), lambda: _compare_players(request, user_ids, period, v))


def _compare_players(request: Request, user_ids: str, period: str, v: visibility.View = visibility.ALL_SHOWN) -> dict:
    ids = [u for u in user_ids.split(",") if u][:4]
    if len(ids) < 2:
        raise ApiError(400, "need_two", "Give at least two user ids, comma-separated")
    with request.app.state.sessionmaker() as db:
        players = {p.user_id: p for p in db.scalars(select(Player).where(Player.user_id.in_(ids)))}
        missing = [u for u in ids if u not in players]
        if missing:
            raise ApiError(404, "not_found", f"Player(s) not found: {', '.join(missing)}")
        wl = not any(v.hides(*visibility.ids(db, u)) for u in ids)
        strict = request.app.state.settings.counted_stats
        profiles = [{"user_id": u, "name": players[u].name, "stats": _profile(db, _filters(players[u].id, period, None), strict)}
                    for u in ids]
        if not wl:
            profiles = [p | {"stats": visibility.without(p["stats"])} for p in profiles]
        a, b = players[ids[0]].id, players[ids[1]].id
        h2h = {"together": [0, 0, 0], "against": [0, 0, 0]}  # games, wins, losses for the first player
        for _, same, won, decided in _together(db, a, other=b):
            entry = h2h["together" if same else "against"]
            entry[0] += 1
            if decided:
                entry[1 if won else 2] += 1
    return {"period": period, "players": profiles, "head_to_head": {
        k: {"games": g, "wins": w, "losses": l} if wl else {"games": g} for k, (g, w, l) in h2h.items()}}


@router.get("/{user_id}")
def get_player(
    request: Request,
    user_id: str,
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    map: str | None = Query(None, pattern=MAP_PATTERN),
):
    v = visibility.view(request)
    return cached_response(request, "player", (user_id, period, map, v),
                           lambda: _get_player(request, user_id, period, map, v))


def _get_player(request: Request, user_id: str, period: str, map: str | None, v: visibility.View = visibility.ALL_SHOWN) -> dict:
    with request.app.state.sessionmaker() as db:
        # a merged id (D34) answers with its main player; the page then moves to the main player's address
        if (alias := db.get(PlayerAlias, user_id)) is not None:
            user_id = alias.main_user_id
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        wl = not v.hides(*visibility.ids(db, user_id))
        where = _filters(player.id, period, map)
        stats = _profile(db, where, request.app.state.settings.counted_stats)
        if not wl:
            stats = visibility.without(stats)
        ids = ids_of(db, player.user_id)

        level = db.scalar(
            select(MatchPlayer.level).join(Match, Match.id == MatchPlayer.match_id)
            .where(MatchPlayer.player_id == player.id).order_by(Match.started_at.desc()).limit(1)
        )
        loadout_rows = db.execute(
            select(MatchPlayerLoadout.weapon, MatchPlayerLoadout.tacmod, MatchPlayerLoadout.ordnance,
                   func.sum(MatchPlayerLoadout.frames).label("frames"))
            .join(Match, Match.id == MatchPlayerLoadout.match_id)
            .join(MatchPlayer, and_(MatchPlayer.match_id == MatchPlayerLoadout.match_id,
                                    MatchPlayer.player_id == MatchPlayerLoadout.player_id))
            .where(where)
            .group_by(MatchPlayerLoadout.weapon, MatchPlayerLoadout.tacmod, MatchPlayerLoadout.ordnance)
            .order_by(func.sum(MatchPlayerLoadout.frames).desc())
        ).all()
        total_frames = sum(r.frames for r in loadout_rows)
        matches_in_view = (select(MatchPlayer.match_id).join(Match, Match.id == MatchPlayer.match_id).where(where))
        gear = gear_use.summarize(gear_use.picks_of_player(db, player.id, matches_in_view), loadout_rows)

        recent = db.execute(
            select(Match, MatchPlayer).join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(where).order_by(Match.started_at.desc()).limit(RECENT_MATCHES)
        ).all()

    return {
        "user_id": player.user_id,
        "name": player.name,
        "merged_ids": sorted(ids - {player.user_id}),
        "level": level,
        "first_seen_at": player.first_seen_at,
        "last_seen_at": player.last_seen_at,
        "period": period,
        "map": map,
        "stats": stats,
        "site_avg": _site_averages(request, period, map),  # same period / map, all players
        "loadouts": [loadout(r.weapon, r.tacmod, r.ordnance, r.frames, total_frames) for r in loadout_rows],
        "gear": gear,  # per weapon / ordnance / tac mod: times picked, games used, share of time held
        "recent_matches": [
            match_summary(m) | {
                "team": mp.team,
                "deaths_est": mp.deaths_est,
                "play_time_s": mp.play_time_s,
            } | ({"result": None if m.winner is None else ("win" if m.winner == mp.team else "loss")} if wl else {})
            for m, mp in recent
        ],
    }


HEATMAP_MODES = heatmaps.TRACK_MODES + ("deaths",)
ALL_MATCHES = 5000  # "All" in the page's Matches list
HEATMAP_STAMP = 1  # another number when a heatmap is worked out differently: every kept one is then built again


_heatmap_stamps: dict[tuple, tuple] = {}  # (user id, map, period) -> (state of the archive, stamp)


def heatmap_stamp(app, user_id: str, map_: str, period: str) -> tuple:
    """What a player heatmap is built from, as a stamp for the cache: the player's ids, and the number, newest and
    last (re-)read of the matches on this map in this period. It changes when one of the player's own matches is
    added, re-read or removed, and not when anybody else's replay comes in. Looked up once per state of the archive
    (10 ms for a player with 1,700 matches): while no replay comes in, a repeat costs nothing."""
    archive = (cache.current_stamp(app.state.sessionmaker), datetime.now().date() if period != "all" else None)
    key = (user_id, map_, period)
    memo = _heatmap_stamps.get(key)
    if memo is not None and memo[0] == archive:
        return memo[1]
    with app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            return (HEATMAP_STAMP, None)
        found = db.execute(
            select(func.count(), func.max(Match.id), func.max(Replay.processed_at))
            .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id).join(Replay, Replay.id == Match.replay_id)
            .where(_filters(player.id, period, map_))).one()
        stamp = (HEATMAP_STAMP, player.id, sorted(ids_of(db, user_id)), found[0], found[1], str(found[2]))
    if len(_heatmap_stamps) >= 4096:
        _heatmap_stamps.clear()
    _heatmap_stamps[key] = (archive, stamp)
    return stamp


def _heatmap_job(request, user_id: str, map_: str, mode: str, period: str, last: int, cell: float) -> dict:
    return {"name": "player-heatmap", "params": (user_id, map_, mode, period, last, cell),
            "compute": lambda: _player_heatmap(request, user_id, map_, mode, period, last, cell),
            "stamp": lambda: heatmap_stamp(request.app, user_id, map_, period), "daily": period != "all"}


# 3D heatmaps that leave matches out because their 3D tracks are not there yet (an archive still being backfilled):
# those tracks arrive without the database knowing, so such a heatmap is looked at again once a day. One that covers
# all its matches is only built again when the player has a new match.
_partial_3d: set[tuple] = set()


def _heatmap3d_job(request, user_id: str, map_: str, mode: str, period: str, last: int) -> dict:
    params = (user_id, map_, mode, period, last)

    def compute() -> dict:
        answer = _player_heatmap3d(request, user_id, map_, mode, period, last)
        (_partial_3d.add if answer["matches_3d"] < answer["matches"] else _partial_3d.discard)(params)
        return answer

    def stamp() -> tuple:
        day = datetime.now().date().isoformat() if params in _partial_3d else None
        return (*heatmap_stamp(request.app, user_id, map_, period), day)

    return {"name": "player-heatmap3d", "params": params, "compute": compute, "stamp": stamp, "daily": period != "all"}


class _NoRequest:
    """What the builders read of a request, for building without one."""

    def __init__(self, app):
        self.app = app


def prebuild_heatmaps(app, user_id: str, map_: str) -> int:
    """The two long heatmaps of a player on a map (all time, all matches, by team: flat and 3D) onto disk ahead of
    time (heights_warm.py). Returns how many were built: 0 when both saved ones are still current."""
    if map_ not in HEATMAP_LAYOUTS:
        return 0
    request = _NoRequest(app)
    return (cache.prebuild(app, **_heatmap_job(request, user_id, map_, "team", "all", ALL_MATCHES, heatmaps.HEATMAP_CELL_M))
            + cache.prebuild(app, **_heatmap3d_job(request, user_id, map_, "team", "all", ALL_MATCHES)))


def _player_heatmap(request: Request, user_id: str, map_: str, mode: str, period: str, last: int, cell: float) -> dict:
    layout = HEATMAP_LAYOUTS[map_]
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        player_id, user_ids = player.id, ids_of(db, user_id)
        rows = db.execute(
            select(Match.id, Match.replay_id).join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(_filters(player_id, period, map_)).order_by(Match.started_at.desc()).limit(last)
        ).all()
        deaths = []
        if mode == "deaths" and rows:
            deaths = db.scalars(
                select(Event.data).where(Event.match_id.in_([r.id for r in rows]), Event.type == "death_est",
                                         Event.player_id == player_id)
            ).all()
    if mode == "deaths":
        counts = Counter()
        for data in deaths:
            point = json.loads(data)
            cell_xy = heatmaps.to_cell(layout, point["x"], point["z"], cell)
            if cell_xy:
                counts[cell_xy] += 1
        layers, labels = {"deaths": counts}, {"deaths": "Deaths (estimated)"}
    else:
        processed = request.app.state.settings.processed_dir
        decoded = tracks.read_many(tracks.tracks_path(processed, r.replay_id) for r in rows)
        layers, labels = heatmaps.build_layers(layout, decoded, user_ids, mode, cell)
    return heatmaps.response(map_, layers, labels, matches=len(rows), cell_m=cell, mode=mode)


@router.get("/{user_id}/heatmap")
def get_player_heatmap(
    request: Request,
    user_id: str,
    map: str = Query(..., pattern="^(" + "|".join(HEATMAP_LAYOUTS) + ")$"),
    mode: str = Query("team", pattern="^(" + "|".join(HEATMAP_MODES) + ")$"),
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    last: int = Query(200, ge=1, le=5000, description="most recent N matches"),
    cell: float = Query(heatmaps.HEATMAP_CELL_M, description="cell size in metres: 0.1 only"),
):
    if cell not in heatmaps.CELL_SIZES:
        raise ApiError(400, "bad_cell", f"cell must be one of {heatmaps.CELL_SIZES}")
    return cached_response(request, **_heatmap_job(request, user_id, map, mode, period, last, cell), persist=True)


HEATMAP3D_MODES = heatmaps.TRACK_MODES  # deaths are stored without a height


def _player_heatmap3d(request: Request, user_id: str, map_: str, mode: str, period: str, last: int) -> dict:
    layout = HEATMAP_LAYOUTS[map_]
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        player_id, user_ids = player.id, ids_of(db, user_id)
        rows = db.execute(
            select(Match.id, Match.replay_id).join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(_filters(player_id, period, map_)).order_by(Match.started_at.desc()).limit(last)
        ).all()
    processed = request.app.state.settings.processed_dir
    pairs = read_pairs((tracks.tracks_path(processed, r.replay_id), tracks3d.tracks3d_path(processed, r.replay_id))
                       for r in rows)
    layers, labels, used = build_layers3d(layout, pairs, user_ids, mode)
    model = f"/maps3d/{map_}.glb?v={VERSION}" if map_ in MAPS_3D else None
    return heatmaps3d.response(map_, layers, labels, matches=len(rows), matches_3d=used, mode=mode, model=model)


@router.get("/{user_id}/heatmap3d")
def get_player_heatmap3d(
    request: Request,
    user_id: str,
    map: str = Query(..., pattern="^(" + "|".join(HEATMAP_LAYOUTS) + ")$"),
    mode: str = Query("team", pattern="^(" + "|".join(HEATMAP3D_MODES) + ")$"),
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    last: int = Query(200, ge=1, le=5000, description="most recent N matches"),
):
    """The 3D version of /heatmap, from the matches whose 3D tracks exist (`matches_3d` of `matches`): none is built here."""
    return cached_response(request, **_heatmap3d_job(request, user_id, map, mode, period, last), persist=True)


@router.get("/{user_id}/trends")
def get_trends(request: Request, user_id: str, bucket: str = Query("month", pattern="^(week|month|year)$")):
    v = visibility.view(request)
    return cached_response(request, "trends", (user_id, bucket, v), lambda: _get_trends(request, user_id, bucket, v))


def _get_trends(request: Request, user_id: str, bucket: str, v: visibility.View = visibility.ALL_SHOWN) -> dict:
    """Per-period aggregates for trend charts."""
    expr = {"week": func.strftime("%Y-%W", Match.started_at), "month": func.substr(Match.started_at, 1, 7),
            "year": func.substr(Match.started_at, 1, 4)}[bucket]
    s = func.sum
    won = case((Match.winner == MatchPlayer.team, 1), else_=0)
    lost = case((and_(Match.winner.is_not(None), Match.winner != MatchPlayer.team), 1), else_=0)
    strict = request.app.state.settings.counted_stats

    def c(e):  # averages over counted games only, as on the profile (stats/quality.py)
        return quality.only_counted(Match, e, strict)

    ping = func.coalesce(MatchPlayer.ping_capped_sum, MatchPlayer.ping_sum)
    top = func.max(case((Match.counted_for_stats == 1, MatchPlayer.top_speed), else_=None)) if strict else func.max(MatchPlayer.top_speed)
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        wl = not v.hides(*visibility.ids(db, user_id))
        rows = db.execute(
            select(expr.label("period"), func.count().label("games"), s(c(1)).label("counted"), s(c(won)).label("wins"), s(c(lost)).label("losses"),
                   s(c(MatchPlayer.deaths_est)).label("deaths"), s(c(MatchPlayer.speed_sum)).label("speed"),
                   s(c(MatchPlayer.frames_in_bounds)).label("in_bounds"), s(c(ping)).label("ping"),
                   s(c(MatchPlayer.ping_frames)).label("ping_frames"), top.label("top"))
            .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
            .where(MatchPlayer.player_id == player.id, counted(Match.id)).group_by("period").order_by("period")
        ).all()
    return {"bucket": bucket, "items": [{
        "period": r.period, "games": r.games,
        **({"win_rate": ratio(r.wins, (r.wins or 0) + (r.losses or 0))} if wl else {}),
        "deaths_per_game_est": ratio(r.deaths, r.counted, 2),
        "avg_speed": ratio(r.speed, r.in_bounds, 2),
        "top_speed": round(r.top or 0, 2),
        "avg_ping": ratio(r.ping, r.ping_frames, 1),
    } for r in rows]}


COMPANION_WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "1m": timedelta(days=30),
                     "3m": timedelta(days=91), "6m": timedelta(days=182), "12m": timedelta(days=365)}


def _mine(player_id: int, window: str = "all"):
    """The player's matches (and team in each) within a rolling window, duplicate recordings left out."""
    conditions = [MatchPlayer.player_id == player_id, counted(MatchPlayer.match_id)]
    if delta := COMPANION_WINDOWS.get(window):
        # started_at is recorder-local time (D17), so the cutoff is local time too
        conditions.append(MatchPlayer.match_id.in_(
            select(Match.id).where(Match.started_at >= (datetime.now() - delta).isoformat(timespec="seconds"))))
    return select(MatchPlayer.match_id, MatchPlayer.team).where(*conditions).subquery()


def _together(db, player_id: int, window: str = "all", other: int | None = None):
    """Rows of (other_player_id, same_team, won, decided) for every match shared with another player (or `other`)."""
    me = _mine(player_id, window)
    query = (select(MatchPlayer.player_id, MatchPlayer.team == me.c.team, Match.winner == me.c.team, Match.winner.is_not(None))
             .join(me, me.c.match_id == MatchPlayer.match_id).join(Match, Match.id == MatchPlayer.match_id)
             .where(MatchPlayer.player_id != player_id))
    if other is not None:
        query = query.where(MatchPlayer.player_id == other)
    return db.execute(query).all()


@router.get("/{user_id}/companions")
def get_companions(request: Request, user_id: str, limit: int = Query(10, ge=1, le=50),
                   window: str = Query("all", pattern="^(24h|7d|1m|3m|6m|12m|all)$")):
    """Most frequent teammates and opponents, with the record together / against, over a rolling time window."""
    v = visibility.view(request)
    return cached_response(request, "companions", (user_id, limit, window, v),
                           lambda: _get_companions(request, user_id, limit, window, v))


def _get_companions(request: Request, user_id: str, limit: int, window: str = "all", v: visibility.View = visibility.ALL_SHOWN) -> dict:
    """Counted in the database (one row per companion and side) and only the names shown are looked up: the busiest
    players share ~60k match slots with others."""
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        wl = not v.hides(*visibility.ids(db, user_id))
        me = _mine(player.id, window)
        same = MatchPlayer.team == me.c.team
        decided = Match.winner.is_not(None)
        rows = db.execute(
            select(MatchPlayer.player_id, same.label("same"), func.count().label("games"),
                   func.sum(case((and_(decided, Match.winner == me.c.team), 1), else_=0)).label("wins"),
                   func.sum(case((and_(decided, Match.winner != me.c.team), 1), else_=0)).label("losses"))
            .join(me, me.c.match_id == MatchPlayer.match_id).join(Match, Match.id == MatchPlayer.match_id)
            .where(MatchPlayer.player_id != player.id).group_by(MatchPlayer.player_id, same)
        ).all()
        # most games first; ties: most wins (when shown: the order would give them away), then the player first seen
        ranked = sorted(rows, key=lambda r: (-r.games, -r.wins if wl else 0, r.player_id))
        top = {side: [r for r in ranked if bool(r.same) == side][:limit] for side in (True, False)}
        shown = {r.player_id for side in top.values() for r in side}
        people = {pid: (uid, name) for pid, uid, name in
                  db.execute(select(Player.id, Player.user_id, Player.name).where(Player.id.in_(shown)))}

    def side(rows):
        return [{"user_id": people[r.player_id][0], "name": people[r.player_id][1], "games": r.games}
                | ({"wins": r.wins, "losses": r.losses} if wl else {}) for r in rows]

    return {"teammates": side(top[True]), "opponents": side(top[False])}
