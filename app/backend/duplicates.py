"""Duplicate recordings (D13, revised 2026-10-31): the same match saved in more than one file. The copies share a
session id and a time span; every copy keeps its match page, but only the most complete one counts towards stats
(totals, leaderboard, profiles, achievements, heatmaps, match lists). Back-to-back matches in one lobby share a
session id too, but do not overlap: they are separate matches and all count.

In the 2026 archive 437 pairs overlap by 95 % or more and 156 do not overlap at all, so the threshold is not delicate."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from .models import DuplicateMatch, Match, MatchPlayer

OVERLAP = 0.5  # same recording: overlapping for more than this share of the shorter one


def counted(match_id_column):
    """Condition for every stat query: leave out copies another file already counts."""
    return match_id_column.not_in(select(DuplicateMatch.match_id))


def _span(started_at: str, duration_s: float) -> tuple[float, float]:
    start = datetime.fromisoformat(started_at).timestamp()
    return start, start + duration_s


def _overlaps(a, b) -> bool:
    (a0, a1), (b0, b1) = _span(a.started_at, a.duration_s), _span(b.started_at, b.duration_s)
    shorter = min(a1 - a0, b1 - b0)
    return shorter > 0 and min(a1, b1) - max(a0, b0) > OVERLAP * shorter


def _groups(recordings: list) -> list[list]:
    """Recordings of one session -> groups of copies of the same match (overlap is chained: A~B, B~C)."""
    group_of = {r.id: [r] for r in recordings}
    for i, a in enumerate(recordings):
        for b in recordings[i + 1:]:
            ga, gb = group_of[a.id], group_of[b.id]
            if ga is not gb and _overlaps(a, b):
                ga.extend(gb)
                for r in gb:
                    group_of[r.id] = ga
    return list({id(g): g for g in group_of.values()}.values())


def _most_complete(group: list):
    """Longest recording, then most players, then most frames; ties: the file found first (replay ids are stable,
    match ids change on every re-read)."""
    return max(group, key=lambda r: (r.duration_s, r.players, r.frame_count, -r.replay_id))


def _refresh(db: Session, sessions_query) -> None:
    players = select(func.count()).where(MatchPlayer.match_id == Match.id).scalar_subquery()
    rows = db.execute(select(Match.id, Match.replay_id, Match.session_id, Match.started_at, Match.duration_s,
                             Match.frame_count, players.label("players")).where(Match.session_id.in_(sessions_query))).all()
    db.execute(delete(DuplicateMatch).where(DuplicateMatch.match_id.in_([r.id for r in rows])))
    by_session = defaultdict(list)
    for r in rows:
        by_session[r.session_id].append(r)
    for recordings in by_session.values():
        for group in _groups(recordings) if len(recordings) > 1 else ():
            best = _most_complete(group)
            db.add_all(DuplicateMatch(match_id=r.id, counted_match_id=best.id) for r in group if r is not best)


def refresh(db: Session, session_ids: Iterable[str]) -> None:
    """After a match of these sessions was saved or deleted: decide again which copies count. Caller commits."""
    ids = sorted(set(session_ids))
    if ids:
        _refresh(db, ids)


def refresh_all(sessions: sessionmaker) -> None:
    """Startup: every session recorded more than once (also fills the table on a database from before D13's revision)."""
    with sessions() as db:
        db.execute(delete(DuplicateMatch))
        _refresh(db, select(Match.session_id).group_by(Match.session_id).having(func.count() > 1))
        db.commit()
