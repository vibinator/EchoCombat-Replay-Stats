import base64
import json
import threading
import time
from collections import Counter
from concurrent.futures import CancelledError, Future
from concurrent.futures import TimeoutError as BuildTimeout
from concurrent.futures.process import BrokenProcessPool
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from .. import gear_use, heatmaps, heatmaps3d, tracks, tracks3d
from ..aliases import alias_map, ids_of
from ..cache import cached_response
from ..duplicates import counted
from ..errors import ApiError
from ..gear import ORDNANCES, TACMODS, WEAPONS
from ..gear import lookup as gear_lookup
from ..stats.map_objects import CAPTURE_POINTS, PAYLOAD_ROUTES
from ..stats.maps import HEATMAP_LAYOUTS, minimap_url
from ..models import AggressiveRepair, CombatMatch, DuplicateMatch, Event, Match, MatchPlayer, MatchPlayerLoadout, Player, RepairRequest, Replay
from ..version import VERSION
from .derived import ID_MAX, MAP_PATTERN, MODE_PATTERN, TEXT_MAX, dominant_arm, loadout, match_summary, ratio
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
    map: str | None = Query(None, pattern=MAP_PATTERN),
    mode: str | None = Query(None, pattern=MODE_PATTERN),
    player: str | None = Query(None, max_length=ID_MAX, description="user_id"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    private: bool | None = None,
    min_players: int | None = Query(None, ge=1),
    result: str | None = Query(None, pattern="^(attack_win|defence_win|unknown|blue|orange)$"),
    player_name: str | None = Query(None, max_length=TEXT_MAX, description="matches with a player whose name contains this"),
    with_players: bool = Query(False, description="include player names per match (match cards)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    params = (map, mode, player, from_, to, private, min_players, result, player_name, with_players, limit, offset)
    return cached_response(request, "matches", params, lambda: _list_matches(request, *params))


def _list_matches(request: Request, map, mode, player, from_, to, private, min_players, result, player_name,
                  with_players, limit, offset) -> dict:
    query = select(Match).where(counted(Match.id))  # a copy of a match recorded twice is listed once (D13)
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
        big_enough = select(MatchPlayer.match_id).group_by(MatchPlayer.match_id).having(func.count() >= min_players)
        query = query.where(Match.id.in_(big_enough))
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


MAX_THUMBNAILS = 48  # two pages of match cards


# Declared before /{match_id}: otherwise "thumbnails" would be read as a match id.
@router.get("/thumbnails")
def get_thumbnails(request: Request, ids: str = Query(..., pattern=r"^\d+(,\d+)*$", description="match ids, comma-separated")):
    """Team heat over the minimap for a page of match cards, as PNG data URLs keyed by match id (matches without
    position data are left out). One ordinary request for the whole page, not a heavy heatmap request per card."""
    wanted = tuple(sorted({int(i) for i in ids.split(",")}))
    if len(wanted) > MAX_THUMBNAILS:
        raise ApiError(400, "too_many", f"At most {MAX_THUMBNAILS} matches at once")
    return cached_response(request, "match-thumbnails", wanted, lambda: _thumbnails(request, wanted))


def _thumbnails(request: Request, ids: tuple[int, ...]) -> dict:
    with request.app.state.sessionmaker() as db:
        rows = db.execute(select(Match.id, Match.map, Match.replay_id).where(Match.id.in_(ids))).all()
    processed = request.app.state.settings.processed_dir
    out = {}
    for match_id, map_, replay_id in rows:
        if map_ in HEATMAP_LAYOUTS and (url := _thumbnail(tracks.tracks_path(processed, replay_id), map_)):
            out[str(match_id)] = url
    return {"thumbnails": out}


def _thumbnail(path: Path, map_: str) -> str | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None  # still importing
    return _thumbnail_for(str(path), stat.st_mtime_ns, stat.st_size, map_)


@lru_cache(maxsize=512)  # ~5 KB each; keyed on the file's mtime and size, so a reprocessed replay is drawn again
def _thumbnail_for(path: str, _mtime_ns: int, _size: int, map_: str) -> str | None:
    data = tracks.read(Path(path))
    png = heatmaps.thumbnail_png(HEATMAP_LAYOUTS[map_], data) if data else None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii") if png else None


def player_row(mp: MatchPlayer, user_id: str, loadouts: list[MatchPlayerLoadout], picks=None) -> dict:
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
        # per weapon / ordnance / tac mod: times picked and share of time held in this match
        "gear": gear_use.summarize([picks or gear_use.count_picks([])], loadouts, games=False),
    }


@router.get("/{match_id}")
def get_match(request: Request, match_id: int):
    return cached_response(request, "match", (match_id,), lambda: match_detail(request, match_id))


def match_detail(request: Request, match_id: int) -> dict:
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
        # other recordings of this same match (D13); back-to-back matches in the lobby share the session but are not copies
        duplicate_of = db.scalar(select(DuplicateMatch.counted_match_id).where(DuplicateMatch.match_id == match_id))
        root = duplicate_of or match_id
        copies = db.scalars(select(DuplicateMatch.match_id).where(DuplicateMatch.counted_match_id == root)).all()
        also = sorted({root, *copies} - {match_id})
        repaired = repair_note(db.scalar(select(Replay.warnings).where(Replay.id == match.replay_id)))
        source_path = db.scalar(select(Replay.source_path).where(Replay.id == match.replay_id)) or ""
        replay_name = source_path.rsplit("/", 1)[-1].rsplit(".", 1)[0] or None  # the replay file's name = its match id

        picks = gear_use.picks_in_match(db, match_id)
        teams: dict[str, list] = {"blue": [], "orange": []}
        for mp, user_id in rows:
            teams.setdefault(mp.team, []).append(
                player_row(mp, user_id, loadouts.get(mp.player_id, []), picks.get(mp.player_id)))
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
            "duplicate_of": duplicate_of,  # another recording of this match counts in the stats instead (D13)
            "repaired": repaired,
            "replay_name": replay_name,
            # the recorder's combat report exists: the page shows the Combat tab and asks for it only then (Review BUG-7)
            "has_combat": db.scalar(select(CombatMatch.id).where(CombatMatch.session_id == match.session_id).limit(1)) is not None,
        }


def repair_note(warnings: str | None) -> dict | None:
    """Read from a damaged file by a repair (D36, D36b): {"aggressive": bool, "frames": n}, else None."""
    try:
        first = (json.loads(warnings) if warnings else [None])[0]
    except (ValueError, IndexError, TypeError):
        return None
    if not isinstance(first, str) or not first.startswith("Repaired"):
        return None
    frames = first.split(": ", 1)[1].split(" ", 1)[0].replace(",", "") if ": " in first else ""
    return {"aggressive": first.startswith("Repaired (aggressive)"), "frames": int(frames) if frames.isdigit() else None}


@router.get("/{match_id}/events")
def get_events(request: Request, match_id: int, type: str | None = None):  # also called directly: plain default
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
    return cached_response(request, "timeline", (match_id,), lambda: _timeline(request, match_id))


def _timeline(request: Request, match_id: int) -> dict:
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
    player: str | None = Query(None, max_length=ID_MAX, description="user_id"),
    mode: str = Query("team", pattern="^(" + "|".join(MATCH_HEATMAP_MODES) + ")$"),
    cell: float = Query(heatmaps.HEATMAP_CELL_M, description="cell size in metres: 0.1 only"),
):
    """One layer per team, player, weapon, ordnance, tac mod, loadout or speed band; `player` = one player."""
    if cell not in heatmaps.CELL_SIZES:
        raise ApiError(400, "bad_cell", f"cell must be one of {heatmaps.CELL_SIZES}")
    return cached_response(request, "match-heatmap", (match_id, player, mode, cell),
                           lambda: _match_heatmap(request, match_id, player, mode, cell))


def _match_heatmap(request: Request, match_id: int, player: str | None, mode: str, cell: float) -> dict:
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


@router.get("/{match_id}/heatmap3d")
def get_match_heatmap3d(
    request: Request,
    match_id: int,
    player: str | None = Query(None, max_length=ID_MAX, description="user_id"),
    mode: str = Query("team", pattern="^(" + "|".join(MATCH_HEATMAP_MODES) + ")$"),
):
    """The 3D version of /heatmap: the same layers as voxels in world space (heatmaps3d). The match's 3D tracks are
    built on first view when missing, as for 3D playback."""
    return cached_response(request, "match-heatmap3d", (match_id, player, mode),
                           lambda: _match_heatmap3d(request, match_id, player, mode))


def _match_heatmap3d(request: Request, match_id: int, player: str | None, mode: str) -> dict:
    with request.app.state.sessionmaker() as db:
        match = _match_or_404(db, match_id)
        wanted = ids_of(db, player) if player else None
        roster = db.execute(
            select(Player.user_id, MatchPlayer.name, MatchPlayer.team).join(Player)
            .where(MatchPlayer.match_id == match_id).order_by(MatchPlayer.team, MatchPlayer.play_time_s.desc())
        ).all() if mode == "player" else []
    if match.map not in HEATMAP_LAYOUTS:
        raise ApiError(404, "no_heatmap", f"No minimap for map '{match.map}'")
    header, players = _tracks(request, match)
    three = _tracks3d(request, match.replay_id)
    layout = HEATMAP_LAYOUTS[match.map]
    model = f"/maps3d/{match.map}.glb?v={VERSION}" if match.map in MAPS_3D else None
    if mode == "player":
        found = heatmaps3d.player_layers3d(layout, players, three[1], wanted, header.get("hz", 2), three[0].get("hz", 5))
        layers = {uid: found.pop(uid) for uid, _, _ in roster if uid in found} | found  # roster order first
        labels = {uid: name for uid, name, _ in roster}
        teams = {uid: team for uid, _, team in roster}
        return heatmaps3d.response(match.map, layers, labels, matches=1, matches_3d=1, mode=mode, teams=teams, model=model)
    layers, labels, used = heatmaps3d.build_layers3d(layout, [((header, players), three)], wanted, mode)
    return heatmaps3d.response(match.map, layers, labels, matches=1, matches_3d=used, mode=mode, model=model)


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
    match = match_detail(request, match_id)
    players = match["teams"].get("blue", []) + match["teams"].get("orange", [])
    name = f"match-{match_id}-{match['map']}-{match['started_at'][:10]}"
    if format == "json":
        return download_json(match, name)
    return download_csv(export_rows(players), EXPORT_COLUMNS, name)


@router.get("/{match_id}/playback")
def get_playback(request: Request, match_id: int):
    """Player positions at 2 Hz in minimap image space (u, v in 0..1; null = absent / off the image),
    for animating dots over the minimap."""
    return cached_response(request, "playback", (match_id,), lambda: _playback(request, match_id))


def _playback(request: Request, match_id: int) -> dict:
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
    cell_of = heatmaps.cell_mapper(layout)
    out = []
    for uid, t in players.items():
        points = []
        for i, team in enumerate(t["team"]):
            cell = cell_of(t["x"][i] / 10, t["z"][i] / 10) if team else None
            points.append(None if cell is None else [round((cell[0] + 0.5) / cols, 4), round((cell[1] + 0.5) / rows, 4), team])
        main = aliases.get(uid, uid)
        out.append({"user_id": main, "name": names.get(main, uid), "points": points,
                    "speed": _speeds(t, header["hz"]), "loadout": _loadout_runs(t, header)})
    events = [e for e in get_events(request, match_id) if e["type"] in PLAYBACK_EVENTS]
    for e in events:
        e["user_id"] = aliases.get(e["user_id"], e["user_id"]) if e["user_id"] else None
    for e in events:  # where a death happened, in minimap space (None when off the image)
        if e["type"] == "death_est" and e["data"] and "x" in e["data"]:
            cell = cell_of(e["data"]["x"], e["data"]["z"])
            e["data"] |= {"u": None, "v": None} if cell is None else {"u": round((cell[0] + 0.5) / cols, 4), "v": round((cell[1] + 0.5) / rows, 4)}
    return {"map": match.map, "image": minimap_url(match.map), "hz": header["hz"], "samples": header["samples"],
            "mode": match.mode, "attacking_team": match.attacking_team, "duration_s": match.duration_s, "series": header.get("series", {}),
            "gear": {"weapon": _gear_names(header["weapons"], WEAPONS), "ordnance": _gear_names(header["ordnances"], ORDNANCES),
                     "tacmod": _gear_names(header["tacmods"], TACMODS)},
            "events": events, "objects": _map_objects(match.map, cell_of, cols, rows), "players": out}


PLAYBACK_EVENTS = {"round_won", "payload_checkpoint", "death_est", "contest_start", "contest_end", "loadout_change"}

MAPS_3D = {"surge", "fission", "dyson", "combustion"}  # app/frontend/public/maps3d/<map>.glb (app/tools/maps3d)
PAYLOAD_MODEL_MAPS = {"surge", "fission"}  # <map>_payload.glb: the flamingo, taken out of the map so it can move with the cart
BUILD_WAIT_S = 25  # a first view waits this long for its 3D tracks (a 10-minute match takes a few seconds)
MAX_BUILD_WAITERS = 8  # requests waiting for a build at once: each holds one of the server's request threads
FAILED_TTL_S = 600  # a replay whose build failed is not read again for this long (a repeated view must not cost a parse)
_building: dict[int, Future] = {}  # replay id -> build in progress: one build per replay however many visitors ask
_failed: dict[int, float] = {}  # replay id -> time.monotonic() of a failed build
_building_lock = threading.Lock()
_waiters = threading.BoundedSemaphore(MAX_BUILD_WAITERS)


def _recently_failed(replay_id: int) -> bool:
    failed_at = _failed.get(replay_id)
    return failed_at is not None and time.monotonic() - failed_at < FAILED_TTL_S


def _remember_failure(replay_id: int) -> None:
    with _building_lock:
        now = time.monotonic()
        if len(_failed) > 1000:  # forget the old ones: bounded however many damaged replays are asked for
            for rid in [r for r, t in _failed.items() if now - t >= FAILED_TTL_S]:
                del _failed[rid]
        _failed[replay_id] = now


def _tracks3d(request: Request, replay_id: int):
    """The match's 3D tracks; built from the replay on first view when missing (matches processed before 3D playback)."""
    settings = request.app.state.settings
    path = tracks3d.tracks3d_path(settings.processed_dir, replay_id)
    data = tracks3d.read(path)
    if data is not None and data[0].get("version") == tracks3d.FORMAT_VERSION:
        return data
    older = data  # a readable file of an older format (no hands / no roll): built again, but used when that cannot be done

    def unavailable(message: str):
        if older is not None:
            return older
        raise ApiError(404, "no_tracks3d", message)

    with request.app.state.sessionmaker() as db:
        replay = db.get(Replay, replay_id)
        source = replay.source_path if replay else None
        repair: bool | str = False
        if source and db.get(AggressiveRepair, source):
            repair = "aggressive"
        elif source and db.get(RepairRequest, source):
            repair = True
    worker = getattr(request.app.state, "worker", None)
    if not source or worker is None:
        return unavailable("3D positions for this match are not available.")
    if _recently_failed(replay_id):
        return unavailable("3D positions for this match are not available (the replay file could not be read).")
    busy = ApiError(503, "tracks3d_building", "The 3D positions for this match are still being prepared. Try again in a moment.")
    if not _waiters.acquire(blocking=False):
        raise busy  # enough requests are already waiting for builds: do not tie up another thread
    try:
        with _building_lock:
            job = _building.get(replay_id)
            if job is None:
                try:
                    job = worker.run_side(tracks3d.build, str(settings.source_dir / source), str(path), repair)
                except RuntimeError:
                    raise busy  # the worker is stopping
                _building[replay_id] = job
                job.add_done_callback(lambda _f: _building.pop(replay_id, None))
        try:
            built = job.result(timeout=BUILD_WAIT_S)
        except BuildTimeout:
            raise busy
        except CancelledError:
            raise busy
        except BrokenProcessPool:  # the replay killed its process (out of memory?): the pool is replaced, this replay is not tried again soon
            built = False
        except Exception:
            built = False
    finally:
        _waiters.release()
    if built:
        data = tracks3d.read(path)
        if data is not None:
            _failed.pop(replay_id, None)
            return data
    _remember_failure(replay_id)
    return unavailable("3D positions for this match are not available (the replay file could not be read).")


@router.get("/{match_id}/playback3d")
def get_playback3d(request: Request, match_id: int):
    """Head positions (decimetres), facing (yaw 0-255, pitch degrees), team and hands (relative to the head, 2 cm steps:
    lx, ly, lz, rx, ry, rz) at 5 Hz, in world space, for the 3D view.
    Derived data only (tracks3d.bin), never replay frames. Events, gear and objective series come from /playback."""
    return cached_response(request, "playback3d", (match_id,), lambda: _playback3d(request, match_id))


def _playback3d(request: Request, match_id: int) -> dict:
    with request.app.state.sessionmaker() as db:
        match = _match_or_404(db, match_id)
        names = dict(db.execute(
            select(Player.user_id, MatchPlayer.name).join(Player).where(MatchPlayer.match_id == match_id)
        ).all())
        aliases = alias_map(db)
    header, players = _tracks3d(request, match.replay_id)
    out = []
    for uid, t in players.items():
        main = aliases.get(uid, uid)
        out.append({"user_id": main, "name": names.get(main, uid), "x": t["x"].tolist(), "y": t["y"].tolist(),
                    "z": t["z"].tolist(), "yaw": list(t["yaw"]), "pitch": t["pitch"].tolist(), "roll": list(t["roll"]), "team": list(t["team"]),
                    "hands": [t[k].tolist() for k in tracks3d.HAND_KEYS]})
    objects: dict = {}
    if route := PAYLOAD_ROUTES.get(match.map):
        objects["route"] = route
    if point := CAPTURE_POINTS.get(match.map):
        objects["point"] = point
    layout = HEATMAP_LAYOUTS.get(match.map)  # the play area (x min, x max, z min, z max): where the camera looks first
    extent = [layout.x_min, layout.x_max, layout.z_min, layout.z_max] if layout else None
    return {"map": match.map, "model": f"/maps3d/{match.map}.glb?v={VERSION}" if match.map in MAPS_3D else None,
            "payload_model": f"/maps3d/{match.map}_payload.glb?v={VERSION}" if match.map in PAYLOAD_MODEL_MAPS else None, "extent": extent, "hz": header["hz"],
            "samples": header["samples"], "duration_s": match.duration_s, "payload": header.get("payload"),
            "objects": objects, "players": out}


def _map_objects(map_: str, cell_of, cols: int, rows: int) -> dict:
    """Payload route (minimap space, one point per metre of payload distance) or capture point, for drawing."""
    out: dict = {}
    if route := PAYLOAD_ROUTES.get(map_):
        pts = []
        for x, z in route:
            cell = cell_of(x, z)
            pts.append(None if cell is None else [round((cell[0] + 0.5) / cols, 4), round((cell[1] + 0.5) / rows, 4)])
        out["route"] = pts
    if point := CAPTURE_POINTS.get(map_):
        cell = cell_of(point[0], point[1])
        if cell is not None:
            out["point"] = {"u": round((cell[0] + 0.5) / cols, 4), "v": round((cell[1] + 0.5) / rows, 4),
                            "r": round(point[2] / heatmaps.CELL_M / cols, 4)}  # radius as a share of the image width
    return out


def _gear_names(codes: list[str], table) -> list[dict]:
    return [{"code": c, "name": gear_lookup(table, c).display_name, "cut": gear_lookup(table, c).cut} for c in codes]


def _speeds(t: dict, hz: int) -> list[float | None]:
    """Speed in m/s between consecutive 2 Hz samples (None when absent, or after a respawn jump)."""
    out: list[float | None] = [None]
    for i in range(1, len(t["team"])):
        if t["team"][i] and t["team"][i - 1]:
            d = ((t["x"][i] - t["x"][i - 1]) ** 2 + (t["z"][i] - t["z"][i - 1]) ** 2) ** 0.5 / 10  # decimetres -> metres
            v = d * hz
            out.append(round(v, 1) if v < 40 else None)
        else:
            out.append(None)
    return out


def _loadout_runs(t: dict, header: dict) -> list[list[int]]:
    """Run-length list [sample, weapon, ordnance, tacmod] (indexes into `gear`, -1 = none), one row per change."""
    runs: list[list[int]] = []
    last = None
    for i in range(len(t["team"])):
        cur = tuple(-1 if t[k][i] == tracks.NO_WEAPON else t[k][i] for k in ("weapon", "ordnance", "tacmod"))
        if cur != last:
            runs.append([i, *cur])
            last = cur
    return runs
