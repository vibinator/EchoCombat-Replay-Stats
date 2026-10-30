"""Player merges (D34): an admin declares that alias user ids belong to a main user id.

Lossless and reversible: a merge only records the rule in `player_aliases` (kept across rebuilds) and
re-processes the affected replays from the original files, where `persist.save_match` applies the rule.
Undo deletes the rule and re-processes the same replays again. No row is ever rewritten, summed or dropped.
Position tracks keep the raw ids, so track readers look up every id of a player (`ids_of`)."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Match, MatchPlayer, Player, PlayerAlias, Replay


def alias_map(db: Session) -> dict[str, str]:
    """alias user_id -> main user_id."""
    return dict(db.execute(select(PlayerAlias.alias_user_id, PlayerAlias.main_user_id)).all())


def ids_of(db: Session, user_id: str) -> set[str]:
    """Every raw user id that belongs to this (main) player."""
    aliases = db.scalars(select(PlayerAlias.alias_user_id).where(PlayerAlias.main_user_id == user_id)).all()
    return {user_id, *aliases}


def _replays_of(db: Session, user_ids: set[str]) -> list[int]:
    return list(db.scalars(
        select(Match.replay_id).join(MatchPlayer, MatchPlayer.match_id == Match.id).join(Player)
        .where(Player.user_id.in_(user_ids)).distinct()
    ))


def _requeue(db: Session, replay_ids: list[int]) -> None:
    if replay_ids:
        db.execute(update(Replay).where(Replay.id.in_(replay_ids), Replay.status != "processing").values(status="queued"))


def merge(db: Session, main_user_id: str, alias_user_ids: list[str]) -> list[int]:
    """Record the aliases and re-queue every replay they appear in. Returns the replay ids. Caller commits."""
    for alias_id in alias_user_ids:
        # aliases of the alias follow it to the new main player
        db.execute(update(PlayerAlias).where(PlayerAlias.main_user_id == alias_id).values(main_user_id=main_user_id))
        db.merge(PlayerAlias(alias_user_id=alias_id, main_user_id=main_user_id, created_at=utcnow()))
    affected = set(alias_user_ids)
    for alias_id in alias_user_ids:
        affected |= ids_of(db, alias_id)
    replay_ids = _replays_of(db, affected)
    _requeue(db, replay_ids)
    return replay_ids


def unmerge(db: Session, alias_user_id: str) -> list[int]:
    """Forget the alias and re-queue the main player's replays, so the original records are rebuilt
    from the files. Returns the replay ids. Caller commits."""
    row = db.get(PlayerAlias, alias_user_id)
    if row is None:
        return []
    replay_ids = _replays_of(db, {row.main_user_id, alias_user_id})
    db.delete(row)
    _requeue(db, replay_ids)
    return replay_ids
