import json
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .. import heatmaps, tracks
from ..aliases import alias_map, ids_of
from ..errors import ApiError
from ..gear import ORDNANCES, TACMODS, WEAPONS
from ..gear import lookup as gear_lookup
from ..stats.maps import HEATMAP_LAYOUTS
from ..models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player
from .derived import dominant_arm, loadout, match_summary, ratio
from .downloads import download_csv, download_json

router = APIRouter(prefix="/api/matches", tags=["matches"])


def player_counts(db, match_ids: list[int]) -> dict[int, int]:
    rows = db.execute(
        select(MatchPlayer.match_id, func.count()).where(MatchPlayer.match_id.in_(match_ids)).group_by(MatchPlayer.match_id)
    )
    return dict(rows.all())


@router.get("")
def list_matches(
    request: Request,
    map: str | None = None,
    mode: str | None = None,
    player: str | None = Query(None, description="user_id"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    private: bool | None = None,
    min_players: int | None = Query(None, ge=1),
    result: str | None = Query(None, pattern="^(attack_win|defence_win|unknown|blue|orange)$"),
    player_name: str | None = Query(None, description="matches with a player whose name contains this"),
    with_players: bool = Query(False, description="include player names per match (match cards)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Match)
    if private is not None:
        query = query.where(Match.private_match == private)
    if result == "attack_win":
        query = query.where(Match.winner.is_not(None), Match.winner == Match.attacking_team)
    elif result == "defence_win":
        query = query.where(Match.attacking_team.is_not(None), Match.winner.is_not(None),
                            Match.winner != Match.attacking_team)
    elif result == "unknown":
        query = query.where(Match.winner.is_(None))
    elif result in ("blue", "orange"):
        query = query.where(Match.winner == result)
    if min_players:
        counted = select(MatchPlayer.match_id).group_by(MatchPlayer.match_id).having(func.count() >= min_players)
        query = query.where(Match.id.in_(counted))
    if player_name:
        named = select(MatchPlayer.match_id).join(Player).where(Player.name.ilike(f"%{player_name.strip()}%"))
        query = query.where(Match.id.in_(named))
    if map:
        query = query.where(Match.map == map)
    if mode:
        query = query.where(Match.mode == mode)
    if from_:
        query = query.where(Match.started_at >= from_.isoformat())
    if to:
        query = query.where(Match.started_at < (to + timedelta(days=1)).isoformat())
    if player:
        query = query.join(MatchPlayer, MatchPlayer.match_id == Match.id).join(Player).where(Player.user_id == player)
    with request.app.state.sessionmaker() as db:
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        matches = db.scalars(query.order_by(Match.started_at.desc()).limit(limit).offset(offset)).all()
        counts = player_counts(db, [m.id for m in matches])
        names: dict[int, list] = {}
        if with_players and matches:
            for match_id, uid, name, team in db.execute(
                select(MatchPlayer.match_id, Player.user_id, MatchPlayer.name, MatchPlayer.team).join(Player)
                .where(MatchPlayer.match_id.in_([m.id for m in matches])).order_by(MatchPlayer.play_time_s.desc())
            ):
                names.setdefault(match_id, []).append({"user_id": uid, "name": name, "team": team})
    items = [match_summary(m, counts.get(m.id, 0)) | ({"players": names.get(m.id, [])} if with_players else {})
             for m in matches]
    return {"items": items, "total": total}


def player_row(mp: MatchPlayer, user_id: str, loadouts: list[MatchPlayerLoadout]) -> dict:
    in_bounds = mp.frames_in_bounds
    return {
        "user_id": user_id,
        "name": mp.name,
        "team": mp.team,
        "number": mp.number,
        "level": mp.level,
        "play_time_s": mp.play_time_s,
        "left_early": mp.left_early,
        "avg_ping": ratio(mp.ping_sum, mp.ping_frames, 1),
        "avg_speed": ratio(mp.speed_sum, in_bounds, 2),
        "top_speed": round(mp.top_speed, 2),
        "pct_stopped": ratio(mp.frames_stopped, in_bounds),
        "pct_upside_down": ratio(mp.frames_upside_down, in_bounds),
        "pct_near_mate": ratio(mp.frames_near_mate, in_bounds),
        "pct_near_enemy": ratio(mp.frames_near_enemy, in_bounds),
        "dominant_arm": dominant_arm(mp.frames_left_arm, mp.frames_right_arm),
        "deaths_est": mp.deaths_est,
        "payload_push_s": mp.payload_push_s,
        "payload_block_s": mp.payload_block_s,
        "avg_packet_loss": ratio(mp.packet_loss_sum, mp.frames_present, 5),
        "emote_count": mp.emote_count,
        "loadouts": sorted(
            (loadout(lo.weapon, lo.tacmod, lo.ordnance, lo.frames, in_bounds) for lo in loadouts),
            key=lambda x: -x["frames"],
        ),
    }


@router.get("/{match_id}")
def get_match(request: Request, match_id: int):
    with request.app.state.sessionmaker() as db:
        match = db.get(Match, match_id)
        if match is None:
            raise ApiError(404, "not_found", f"Match {match_id} not found")
        rows = db.execute(
            select(MatchPlayer, Player.user_id).join(Player).where(MatchPlayer.match_id == match_id)
        ).all()
        loadouts: dict[int, list] = {}
        for lo in db.scalars(select(MatchPlayerLoadout).where(MatchPlayerLoadout.match_id == match_id)):
            loadouts.setdefault(lo.player_id, []).append(lo)
        also = db.scalars(
            select(Match.id).where(Match.session_id == match.session_id, Match.id != match.id)
        ).all()

        teams: dict[str, list] = {"blue": [], "orange": []}
        for mp, user_id in rows:
            teams.setdefault(mp.team, []).append(player_row(mp, user_id, loadouts.get(mp.player_id, [])))
        for players in teams.values():
            players.sort(key=lambda p: -p["play_time_s"])

        return match_summary(match, len(rows)) | {
            "ended_at": match.ended_at,
            "frame_rate_hz": match.frame_rate_hz,
            "recorded_by": match.recorded_by,
            "private_match": match.private_match,
            "final_blue_points": match.final_blue_points,
            "final_orange_points": match.final_orange_points,
            "final_payload_distance": match.final_payload_distance,
            "final_game_timer": match.final_game_timer,
            "contested_s": match.contested_s,
            "blue_capture_s": match.blue_capture_s,
            "orange_capture_s": match.orange_capture_s,
            "teams": teams,
            "also_recorded_in": list(also),
        }


@router.get("/{match_id}/events")
def get_events(request: Request, match_id: int, type: str | None = None):
    with request.app.state.sessionmaker() as db:
        if db.get(Match, match_id) is None:
            raise ApiError(404, "not_found", f"Match {match_id} not found")
        query = (
            select(Event, Player.user_id, Player.name)
            .outerjoin(Player, Player.id == Event.player_id)
            .where(Event.match_id == match_id)
        )
        if type:
            query = query.where(Event.type == type)
        rows = db.execute(query.order_by(Event.frame, Event.id)).all()
    return [
        {"frame": e.frame, "t_s": e.t_s, "type": e.type, "team": e.team, "user_id": uid, "name": name,
         "data": _event_data(e)}
        for e, uid, name in rows
    ]


def _event_data(e: Event) -> dict | None:
    data = json.loads(e.data) if e.data else None
    if data and e.type == "loadout_change":  # codes -> in-game names
        for key, table in (("weapon", WEAPONS), ("tacmod", TACMODS), ("ordnance", ORDNANCES)):
            data[key] = gear_lookup(table, data.get(key, "")).display_name
    return data


def _match_or_404(db, match_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise ApiError(404, "not_found", f"Match {match_id} not found")
    return match


def _tracks(request: Request, match: Match):
    data = tracks.read(tracks.tracks_path(request.app.state.settings.processed_dir, match.replay_id))
    if data is None:
        raise ApiError(404, "no_tracks", "Position data for this match is not available yet (still importing?)")
    return data


@router.get("/{match_id}/timeline")
def get_timeline(request: Request, match_id: int):
    """Objective progress (2 Hz) + events, for the match timeline."""
    with request.app.state.sessionmaker() as db:
        match = _match_or_404(db, match_id)
    events = get_events(request, match_id)
    data = tracks.read(tracks.tracks_path(request.app.state.settings.processed_dir, match.replay_id))
    header = data[0] if data else {"hz": tracks.HZ, "series": {}}
    return {"hz": header["hz"], "duration_s": match.duration_s, "series": header["series"], "events": events}


MATCH_HEATMAP_MODES = heatmaps.TRACK_MODES + ("player",)


@router.get("/{match_id}/heatmap")
def get_match_heatmap(
    request: Request,
    match_id: int,
    player: str | None = Query(None, description="user_id"),
    mode: str = Query("team", pattern="^(" + "|".join(MATCH_HEATMAP_MODES) + ")$"),
    cell: float = Query(heatmaps.CELL_M, description="cell size in metres: 0.1, 0.25, 0.5 or 1"),
):
    """One layer per team, player, weapon, ordnance, tac mod, loadout or speed band; `player` = one player."""
    if cell not in heatmaps.CELL_SIZES:
        raise ApiError(400, "bad_cell", f"cell must be one of {heatmaps.CELL_SIZES}")
    with request.app.state.sessionmaker() as db:
        match = _match_or_404(db, match_id)
        wanted = ids_of(db, player) if player else None
        roster = db.execute(
            select(Player.user_id, MatchPlayer.name, MatchPlayer.team).join(Player)
            .where(MatchPlayer.match_id == match_id).order_by(MatchPlayer.team, MatchPlayer.play_time_s.desc())
        ).all() if mode == "player" else []
    if match.map not in HEATMAP_LAYOUTS:
        raise ApiError(404, "no_heatmap", f"No minimap for map '{match.map}'")
    data = _tracks(request, match)
    layout = HEATMAP_LAYOUTS[match.map]
    if mode == "player":
        found = heatmaps.player_layers(layout, data[1], wanted, cell)
        layers = {uid: found.pop(uid) for uid, _, _ in roster if uid in found} | found  # roster order first
        labels = {uid: name for uid, name, _ in roster}
        teams = {uid: team for uid, _, team in roster}
        return heatmaps.response(match.map, layers, labels, matches=1, cell_m=cell, mode=mode, teams=teams)
    layers, labels = heatmaps.build_layers(layout, [data], wanted, mode, cell)
    return heatmaps.response(match.map, layers, labels, matches=1, cell_m=cell, mode=mode)


EXPORT_COLUMNS = [
    "team", "name", "user_id", "play_time_s", "left_early", "deaths_est", "avg_ping", "avg_packet_loss",
    "avg_speed", "top_speed", "pct_stopped", "pct_upside_down", "pct_near_mate", "pct_near_enemy",
    "dominant_arm", "payload_push_s", "payload_block_s", "emote_count", "main_weapon", "main_ordnance", "main_tacmod",
]


def export_rows(players: list[dict]) -> list[dict]:
    rows = []
    for p in players:
        main = p["loadouts"][0] if p["loadouts"] else None
        row = {k: p.get(k) for k in EXPORT_COLUMNS}
        row["main_weapon"] = main and main["weapon"]["name"]
        row["main_ordnance"] = main and main["ordnance"]["name"]
        row["main_tacmod"] = main and main["tacmod"]["name"]
        rows.append(row)
    return rows


@router.get("/{match_id}/export")
def export_match(request: Request, match_id: int, format: str = Query("csv", pattern="^(csv|json)$")):
    match = get_match(request, match_id)
    players = match["teams"].get("blue", []) + match["teams"].get("orange", [])
    name = f"match-{match_id}-{match['map']}-{match['started_at'][:10]}"
    if format == "json":
        return download_json(match, name)
    return download_csv(export_rows(players), EXPORT_COLUMNS, name)


@router.get("/{match_id}/playback")
def get_playback(request: Request, match_id: int):
    """Player positions at 2 Hz in minimap image space (u, v in 0..1; null = absent / off the image),
    for animating dots over the minimap."""
    with request.app.state.sessionmaker() as db:
        match = _match_or_404(db, match_id)
        names = dict(db.execute(
            select(Player.user_id, MatchPlayer.name).join(Player).where(MatchPlayer.match_id == match_id)
        ).all())
        aliases = alias_map(db)
    if match.map not in HEATMAP_LAYOUTS:
        raise ApiError(404, "no_heatmap", f"No minimap for map '{match.map}'")
    header, players = _tracks(request, match)
    layout = HEATMAP_LAYOUTS[match.map]
    cols, rows = heatmaps.grid_size(layout)
    out = []
    for uid, t in players.items():
        points = []
        for i, team in enumerate(t["team"]):
            cell = heatmaps.to_cell(layout, t["x"][i] / 10, t["z"][i] / 10) if team else None
            points.append(None if cell is None else [round((cell[0] + 0.5) / cols, 4), round((cell[1] + 0.5) / rows, 4), team])
        main = aliases.get(uid, uid)
        out.append({"user_id": main, "name": names.get(main, uid), "points": points})
    return {"map": match.map, "image": f"/minimaps/{match.map}.png", "hz": header["hz"], "samples": header["samples"],
            "players": out}
