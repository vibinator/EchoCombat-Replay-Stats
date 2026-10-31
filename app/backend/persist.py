"""MatchStats -> database rows. Callers commit, so a match is stored completely or not at all."""

import json
from collections import Counter
from dataclasses import replace
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from parser import ReplayMeta

from . import duplicates
from .aliases import alias_map
from .models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player
from .stats import MatchStats, PlayerStats


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def delete_match(db: Session, replay_id: int) -> None:
    """Remove a replay's derived rows (cascades to match_players, loadouts, events). Players are kept."""
    sessions = db.scalars(select(Match.session_id).where(Match.replay_id == replay_id)).all()
    db.execute(delete(Match).where(Match.replay_id == replay_id))
    duplicates.refresh(db, sessions)  # another copy of the match may count now


def _upsert_player(db: Session, p: PlayerStats, seen_at: str) -> Player:
    player = db.scalar(select(Player).where(Player.user_id == p.user_id))
    if player is None:
        player = Player(user_id=p.user_id, name=p.name, first_seen_at=seen_at, last_seen_at=seen_at)
        db.add(player)
        db.flush()
    else:
        player.first_seen_at = min(player.first_seen_at, seen_at)
        if seen_at >= player.last_seen_at:
            player.last_seen_at, player.name = seen_at, p.name
    return player


def save_match(db: Session, replay_id: int, meta: ReplayMeta, stats: MatchStats, has_tracks: bool = False) -> Match:
    delete_match(db, replay_id)
    started_at = _iso(stats.started_at)
    match = Match(
        replay_id=replay_id,
        session_id=meta.session_id,
        map_code=meta.map_code,
        map=stats.map,
        mode=stats.mode,
        private_match=meta.private_match,
        tournament_match=meta.tournament_match,
        recorded_by=meta.client_name,
        started_at=started_at,
        ended_at=_iso(stats.ended_at),
        duration_s=stats.duration_s,
        frame_count=stats.frame_count,
        frame_rate_hz=stats.frame_rate_hz,
        blue_rounds=stats.blue_rounds,
        orange_rounds=stats.orange_rounds,
        final_blue_points=stats.final_blue_points,
        final_orange_points=stats.final_orange_points,
        final_payload_checkpoint=stats.final_payload_checkpoint,
        final_payload_distance=stats.final_payload_distance,
        contested_s=stats.contested_s,
        winner=stats.winner,
        has_tracks=has_tracks,
        attacking_team=stats.attacking_team,
        final_game_timer=stats.final_game_timer,
        blue_capture_s=stats.blue_capture_s,
        orange_capture_s=stats.orange_capture_s,
    )
    db.add(match)
    db.flush()

    aliases = alias_map(db)
    ids_per_main = Counter(aliases.get(q.user_id, q.user_id) for q in stats.players)
    player_ids: dict[str, int] = {}
    for p in stats.players:
        main_id = aliases.get(p.user_id, p.user_id)
        # merged (D34); two ids of the same person in one match (main + alias, or two aliases) stay separate
        if main_id != p.user_id and ids_per_main[main_id] == 1:
            p = replace(p, user_id=main_id)
        player_ids[p.user_id] = player_id = _upsert_player(db, p, started_at).id
        fields = {k: v for k, v in vars(p).items() if k not in ("user_id", "loadouts")}
        db.add(MatchPlayer(match_id=match.id, player_id=player_id, **fields))
        for (weapon, tacmod, ordnance), frames in p.loadouts.items():
            db.add(MatchPlayerLoadout(match_id=match.id, player_id=player_id, weapon=weapon,
                                      tacmod=tacmod, ordnance=ordnance, frames=frames))

    for e in stats.events:
        db.add(Event(match_id=match.id, frame=e.frame, t_s=e.t_s, type=e.type,
                     player_id=(player_ids.get(e.user_id) or player_ids.get(aliases.get(e.user_id, e.user_id)))
                     if e.user_id else None, team=e.team,
                     data=json.dumps(e.data) if e.data is not None else None))
    db.flush()
    duplicates.refresh(db, [match.session_id])
    return match
