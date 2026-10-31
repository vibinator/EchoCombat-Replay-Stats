"""Player merges (D34): an admin declares that alias user ids belong to a main user id.

Lossless and reversible: a merge records the rule in `player_aliases` (kept across rebuilds), which
`persist.save_match` applies whenever a replay is read. Matches where only one of the player's ids played get their
rows moved to the main player in place (exactly what a re-read would store); the rest are re-processed from the
original files. Undo deletes the rule and re-processes the main player's replays. No stat is ever summed or dropped.
Position tracks keep the raw ids, so track readers look up every id of a player (`ids_of`)."""

from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player, PlayerAlias, Replay


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


@dataclass
class MergeResult:
    moved: list[int] = field(default_factory=list)  # replays updated in place (no re-read)
    requeued: list[int] = field(default_factory=list)  # replays re-processed from the file


def merge(db: Session, main_user_id: str, alias_user_ids: list[str]) -> MergeResult:
    """Record the aliases and apply them to the stored matches. Caller commits.

    Fast path: in a match where exactly one of the main player's ids played (the usual case for an alt), save_match
    would store that player under the main player's row and change nothing else (event players are always match
    players, stats.compute). So its match_players / loadouts / events rows are moved to the main player in place,
    giving the same rows as a re-read. Any other match (the main player and an alias together, or two aliases
    together), or a replay that is not 'done', is re-processed from the file as before, because which raw id a row
    came from is not stored and the rule there depends on it."""
    moved_ids = set(alias_user_ids)
    for alias_id in alias_user_ids:
        moved_ids |= ids_of(db, alias_id)  # aliases of the alias follow it to the new main player
    for alias_id in alias_user_ids:
        db.execute(update(PlayerAlias).where(PlayerAlias.main_user_id == alias_id).values(main_user_id=main_user_id))
        db.merge(PlayerAlias(alias_user_id=alias_id, main_user_id=main_user_id, created_at=utcnow()))
    db.flush()

    pid = dict(db.execute(select(Player.user_id, Player.id).where(Player.user_id.in_(ids_of(db, main_user_id)))).all())
    main_pid = pid.get(main_user_id)
    moved_pids = {pid[u] for u in moved_ids if u in pid}
    if main_pid is None or not moved_pids:
        return MergeResult(requeued=_requeue_list(db, _replays_of(db, moved_ids)))

    candidates = select(MatchPlayer.match_id).where(MatchPlayer.player_id.in_(moved_pids))
    rows = db.execute(
        select(MatchPlayer.match_id, MatchPlayer.player_id, MatchPlayer.name, Match.replay_id, Match.started_at,
               Replay.status)
        .join(Match, Match.id == MatchPlayer.match_id).join(Replay, Replay.id == Match.replay_id)
        .where(MatchPlayer.match_id.in_(candidates), MatchPlayer.player_id.in_(set(pid.values())))
    ).all()
    by_match: dict[int, list] = {}
    for r in rows:
        by_match.setdefault(r.match_id, []).append(r)

    fast, slow = [], set()
    for match_rows in by_match.values():
        if len(match_rows) == 1 and match_rows[0].status == "done":
            fast.append(match_rows[0])
        else:
            slow.add(match_rows[0].replay_id)

    for old_pid, group in _group_by_pid(fast).items():
        match_ids = [r.match_id for r in group]
        for chunk in _chunks(match_ids):
            for table in (MatchPlayer, MatchPlayerLoadout, Event):
                db.execute(update(table).where(table.match_id.in_(chunk), table.player_id == old_pid)
                           .values(player_id=main_pid))
    if fast:
        _touch_main_player(db, main_pid, fast)
        now = utcnow()
        for chunk in _chunks([r.replay_id for r in fast]):  # new data stamp: cached pages recompute (cache.py)
            db.execute(update(Replay).where(Replay.id.in_(chunk)).values(processed_at=now))
    return MergeResult(moved=sorted(r.replay_id for r in fast), requeued=_requeue_list(db, sorted(slow)))


def _group_by_pid(rows) -> dict[int, list]:
    out: dict[int, list] = {}
    for r in rows:
        out.setdefault(r.player_id, []).append(r)
    return out


def _chunks(values: list, size: int = 500):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _touch_main_player(db: Session, main_pid: int, rows) -> None:
    """As persist._upsert_player would for each moved match: earliest first seen; latest last seen and its name."""
    player = db.get(Player, main_pid)
    player.first_seen_at = min(player.first_seen_at, *(r.started_at for r in rows))
    latest = max(rows, key=lambda r: r.started_at)
    if latest.started_at >= player.last_seen_at:
        player.last_seen_at, player.name = latest.started_at, latest.name


def _requeue_list(db: Session, replay_ids: list[int]) -> list[int]:
    """Re-queue for a re-read; the worker takes merge replays newest match first (worker._claim)."""
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
