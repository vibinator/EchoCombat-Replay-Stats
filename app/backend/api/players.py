import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query, Request
from sqlalchemy import and_, case, func, select

from .. import heatmaps, tracks
from ..aliases import ids_of
from ..cache import cached, data_stamp
from ..errors import ApiError
from ..gear import WEAPONS
from ..gear import lookup as gear_lookup
from ..models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player, PlayerAlias
from ..stats.maps import HEATMAP_LAYOUTS
from .derived import PERIODS, dominant_arm, loadout, match_summary, period_start, ratio
from .downloads import json_response

router = APIRouter(prefix="/api/players", tags=["players"])

RECENT_MATCHES = 20


def games_of(player_id_column):
    """Correlated count of a player's matches (index-only on match_players.player_id)."""
    return select(func.count()).where(MatchPlayer.player_id == player_id_column).scalar_subquery()


@router.get("")
def search_players(
    request: Request,
    q: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where = [Player.user_id.not_in(select(PlayerAlias.alias_user_id))]
    if q.strip():
        where.append(Player.name.ilike(f"%{q.strip()}%"))
    with request.app.state.sessionmaker() as db:
        total = db.scalar(select(func.count()).select_from(Player).where(*where))
        # page first (index on last_seen_at), then count games for those rows only
        rows = db.execute(select(Player, games_of(Player.id)).where(*where)
                          .order_by(Player.last_seen_at.desc()).limit(limit).offset(offset)).all()
    items = [{"user_id": p.user_id, "name": p.name, "games": n, "last_seen_at": p.last_seen_at} for p, n in rows]
    return {"items": items, "total": total}


def _filters(player_id: int, period: str, map_: str | None):
    conditions = [MatchPlayer.player_id == player_id]
    if start := period_start(period):
        conditions.append(Match.started_at >= start)
    if map_:
        conditions.append(Match.map == map_)
    return and_(*conditions)


def _profile(db, where) -> dict:
    s = func.sum
    won = case((Match.winner == MatchPlayer.team, 1), else_=0)
    lost = case((and_(Match.winner.is_not(None), Match.winner != MatchPlayer.team), 1), else_=0)
    row = db.execute(
        select(
            func.count().label("games"), s(won).label("wins"), s(lost).label("losses"),
            s(MatchPlayer.deaths_est).label("deaths"), s(MatchPlayer.play_time_s).label("play_time"),
            s(MatchPlayer.speed_sum).label("speed_sum"), s(MatchPlayer.frames_in_bounds).label("in_bounds"),
            func.max(MatchPlayer.top_speed).label("top_speed"),
            s(MatchPlayer.ping_sum).label("ping_sum"), s(MatchPlayer.ping_frames).label("ping_frames"),
            s(MatchPlayer.frames_stopped).label("stopped"), s(MatchPlayer.frames_upside_down).label("upside"),
            s(MatchPlayer.frames_near_mate).label("mate"), s(MatchPlayer.frames_near_enemy).label("enemy"),
            s(MatchPlayer.frames_left_arm).label("left"), s(MatchPlayer.frames_right_arm).label("right"),
            s(case((MatchPlayer.left_early, 1), else_=0)).label("left_early"),
            s(MatchPlayer.payload_push_s).label("push"), s(MatchPlayer.payload_block_s).label("block"),
            s(MatchPlayer.packet_loss_sum).label("loss"), s(MatchPlayer.frames_present).label("present"),
            s(MatchPlayer.emote_count).label("emotes"),
        ).select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id).where(where)
    ).one()
    games = row.games or 0
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
        "wins": row.wins or 0,
        "losses": row.losses or 0,
        "games_by_map": by_map,
        "games_by_mode": by_mode,
        "hours_played": round((row.play_time or 0) / 3600, 2),
        "deaths_est": row.deaths or 0,
        "deaths_per_game_est": ratio(row.deaths, games, 2),
        "avg_speed": ratio(row.speed_sum, row.in_bounds, 2),
        "top_speed": round(row.top_speed, 2) if row.top_speed is not None else None,
        "avg_ping": ratio(row.ping_sum, row.ping_frames, 1),
        "pct_stopped": ratio(row.stopped, row.in_bounds),
        "pct_upside_down": ratio(row.upside, row.in_bounds),
        "pct_near_mate": ratio(row.mate, row.in_bounds),
        "pct_near_enemy": ratio(row.enemy, row.in_bounds),
        "pct_left_early": ratio(row.left_early, games),
        "dominant_arm": dominant_arm(row.left or 0, row.right or 0),
        "pct_left_arm": ratio(row.left, (row.left or 0) + (row.right or 0)),
        "payload_push_s": round(row.push or 0, 1),
        "payload_block_s": round(row.block or 0, 1),
        "in_bounds_frames": row.in_bounds or 0,
        "avg_packet_loss": ratio(row.loss, row.present, 5),
        "emote_count": row.emotes or 0,
    }


@router.get("/compare/{user_ids}")
def compare_players(request: Request, user_ids: str, period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$")):
    """Profiles of 2-4 players side by side + head-to-head record of the first two."""
    return cached(request, "compare", (user_ids, period), lambda: _compare_players(request, user_ids, period))


def _compare_players(request: Request, user_ids: str, period: str) -> dict:
    ids = [u for u in user_ids.split(",") if u][:4]
    if len(ids) < 2:
        raise ApiError(400, "need_two", "Give at least two user ids, comma-separated")
    with request.app.state.sessionmaker() as db:
        players = {p.user_id: p for p in db.scalars(select(Player).where(Player.user_id.in_(ids)))}
        missing = [u for u in ids if u not in players]
        if missing:
            raise ApiError(404, "not_found", f"Player(s) not found: {', '.join(missing)}")
        profiles = [{"user_id": u, "name": players[u].name, "stats": _profile(db, _filters(players[u].id, period, None))}
                    for u in ids]
        a, b = players[ids[0]].id, players[ids[1]].id
        h2h = {"together": [0, 0, 0], "against": [0, 0, 0]}  # games, wins, losses for the first player
        for other, same, won, decided in _together(db, a):
            if other != b:
                continue
            entry = h2h["together" if same else "against"]
            entry[0] += 1
            if decided:
                entry[1 if won else 2] += 1
    return {"period": period, "players": profiles, "head_to_head": {
        k: {"games": g, "wins": w, "losses": l} for k, (g, w, l) in h2h.items()}}


@router.get("/{user_id}")
def get_player(
    request: Request,
    user_id: str,
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    map: str | None = None,
):
    return cached(request, "player", (user_id, period, map), lambda: _get_player(request, user_id, period, map))


def _get_player(request: Request, user_id: str, period: str, map: str | None) -> dict:
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        where = _filters(player.id, period, map)
        stats = _profile(db, where)
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
        "loadouts": [loadout(r.weapon, r.tacmod, r.ordnance, r.frames, total_frames) for r in loadout_rows],
        "recent_matches": [
            match_summary(m) | {
                "team": mp.team,
                "result": None if m.winner is None else ("win" if m.winner == mp.team else "loss"),
                "deaths_est": mp.deaths_est,
                "play_time_s": mp.play_time_s,
            }
            for m, mp in recent
        ],
    }


HEATMAP_MODES = heatmaps.TRACK_MODES + ("deaths",)


@lru_cache(maxsize=64)
def _player_heatmap(sessions, processed_dir: str, player_id: int, user_ids: frozenset, map_: str, mode: str,
                    period: str, last: int, cell: float, stamp: tuple) -> dict:
    """Cached per data stamp (done count + last processed_at): any import change recomputes."""
    layout = HEATMAP_LAYOUTS[map_]
    with sessions() as db:
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
        decoded = (d for d in (tracks.read(tracks.tracks_path(Path(processed_dir), r.replay_id)) for r in rows) if d)
        layers, labels = heatmaps.build_layers(layout, decoded, set(user_ids), mode, cell)
    return heatmaps.response(map_, layers, labels, matches=len(rows), cell_m=cell, mode=mode)


@router.get("/{user_id}/heatmap")
def get_player_heatmap(
    request: Request,
    user_id: str,
    map: str = Query(..., pattern="^(" + "|".join(HEATMAP_LAYOUTS) + ")$"),
    mode: str = Query("team", pattern="^(" + "|".join(HEATMAP_MODES) + ")$"),
    period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
    last: int = Query(200, ge=1, le=5000, description="most recent N matches"),
    cell: float = Query(heatmaps.CELL_M, description="cell size in metres: 0.1, 0.25, 0.5 or 1"),
):
    if cell not in heatmaps.CELL_SIZES:
        raise ApiError(400, "bad_cell", f"cell must be one of {heatmaps.CELL_SIZES}")
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        stamp = data_stamp(db)
    settings = request.app.state.settings
    with request.app.state.sessionmaker() as db:
        user_ids = frozenset(ids_of(db, user_id))
    return json_response(_player_heatmap(request.app.state.sessionmaker, str(settings.processed_dir), player.id, user_ids,
                                        map, mode, period, last, cell, stamp + (len(user_ids),)))


@router.get("/{user_id}/trends")
def get_trends(request: Request, user_id: str, bucket: str = Query("month", pattern="^(week|month|year)$")):
    return cached(request, "trends", (user_id, bucket), lambda: _get_trends(request, user_id, bucket))


def _get_trends(request: Request, user_id: str, bucket: str) -> dict:
    """Per-period aggregates for trend charts."""
    expr = {"week": func.strftime("%Y-%W", Match.started_at), "month": func.substr(Match.started_at, 1, 7),
            "year": func.substr(Match.started_at, 1, 4)}[bucket]
    s = func.sum
    won = case((Match.winner == MatchPlayer.team, 1), else_=0)
    lost = case((and_(Match.winner.is_not(None), Match.winner != MatchPlayer.team), 1), else_=0)
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        rows = db.execute(
            select(expr.label("period"), func.count().label("games"), s(won).label("wins"), s(lost).label("losses"),
                   s(MatchPlayer.deaths_est).label("deaths"), s(MatchPlayer.speed_sum).label("speed"),
                   s(MatchPlayer.frames_in_bounds).label("in_bounds"), s(MatchPlayer.ping_sum).label("ping"),
                   s(MatchPlayer.ping_frames).label("ping_frames"), func.max(MatchPlayer.top_speed).label("top"))
            .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
            .where(MatchPlayer.player_id == player.id).group_by("period").order_by("period")
        ).all()
    return {"bucket": bucket, "items": [{
        "period": r.period, "games": r.games,
        "win_rate": ratio(r.wins, (r.wins or 0) + (r.losses or 0)),
        "deaths_per_game_est": ratio(r.deaths, r.games, 2),
        "avg_speed": ratio(r.speed, r.in_bounds, 2),
        "top_speed": round(r.top or 0, 2),
        "avg_ping": ratio(r.ping, r.ping_frames, 1),
    } for r in rows]}


def _together(db, player_id: int):
    """Rows of (other_player_id, same_team, won) for every match shared with another player."""
    me = select(MatchPlayer.match_id, MatchPlayer.team).where(MatchPlayer.player_id == player_id).subquery()
    return db.execute(
        select(MatchPlayer.player_id, MatchPlayer.team == me.c.team, Match.winner == me.c.team, Match.winner.is_not(None))
        .join(me, me.c.match_id == MatchPlayer.match_id).join(Match, Match.id == MatchPlayer.match_id)
        .where(MatchPlayer.player_id != player_id)
    ).all()


@router.get("/{user_id}/companions")
def get_companions(request: Request, user_id: str, limit: int = Query(10, ge=1, le=50)):
    """Most frequent teammates and opponents, with the record together / against."""
    return cached(request, "companions", (user_id, limit), lambda: _get_companions(request, user_id, limit))


def _get_companions(request: Request, user_id: str, limit: int) -> dict:
    with request.app.state.sessionmaker() as db:
        player = db.scalar(select(Player).where(Player.user_id == user_id))
        if player is None:
            raise ApiError(404, "not_found", f"Player {user_id} not found")
        rows = _together(db, player.id)
        people = dict(db.execute(select(Player.id, Player.user_id)).all())
        names = dict(db.execute(select(Player.id, Player.name)).all())
    stats: dict[tuple[int, bool], list[int]] = {}
    for other, same, won, decided in rows:
        entry = stats.setdefault((other, bool(same)), [0, 0, 0])  # games, wins, losses (from this player's view)
        entry[0] += 1
        if decided:
            entry[1 if won else 2] += 1

    def top(same: bool):
        items = [(pid, v) for (pid, s), v in stats.items() if s == same]
        items.sort(key=lambda kv: -kv[1][0])
        return [{"user_id": people[pid], "name": names[pid], "games": g, "wins": w, "losses": l}
                for pid, (g, w, l) in items[:limit]]

    return {"teammates": top(True), "opponents": top(False)}
