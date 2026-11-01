"""Merge suggestions for the Console (D34 merges): player records that used the same name, which is how one person
on several player ids usually shows. Only suggestions: an admin still decides and runs the merge.

Every name an id was seen with counts (match_players.name), not only its latest one, so an old account whose name was
taken over by a new one is found too. Names match ignoring case and anything but letters and digits ("Vibinator" and
"Vibinator-"); keys shorter than MIN_KEY_CHARS are skipped (too many unrelated players). Ids already merged into
another player are left out; a player that already has merged ids is suggested as the one to keep. Two ids that
played in the same match are flagged: usually two different people with one name."""

import re
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import MatchPlayer, Player, PlayerAlias

MIN_KEY_CHARS = 3
MAX_GROUPS = 500  # the full archive had 258 (2026-11-01)
_NOT_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


def name_key(name: str) -> str:
    return _NOT_ALNUM.sub("", name.casefold())


def suggestions(db: Session) -> list[dict]:
    merged_away = set(db.scalars(select(PlayerAlias.alias_user_id)))
    mains_with_aliases = Counter(db.scalars(select(PlayerAlias.main_user_id)))
    players = {pid: (uid, name, first, last) for pid, uid, name, first, last in db.execute(
        select(Player.id, Player.user_id, Player.name, Player.first_seen_at, Player.last_seen_at))
        if uid not in merged_away}

    names_of: dict[int, set[str]] = defaultdict(set)
    for pid, name in db.execute(select(MatchPlayer.player_id, MatchPlayer.name).distinct()):
        if pid in players and name:
            names_of[pid].add(name)
    for pid, (_, name, _, _) in players.items():
        names_of[pid].add(name)

    # ids sharing any name key are one group (union-find over keys)
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = x = parent[parent[x]]
        return x

    by_key: dict[str, list[int]] = defaultdict(list)
    for pid, names in names_of.items():
        for key in {name_key(n) for n in names}:
            if len(key) >= MIN_KEY_CHARS:
                by_key[key].append(pid)
    for pids in by_key.values():
        for other in pids[1:]:
            parent[find(other)] = find(pids[0])
    groups: dict[int, set[int]] = defaultdict(set)
    for pids in by_key.values():
        if len(pids) > 1:
            for pid in pids:
                groups[find(pid)].add(pid)
    if not groups:
        return []

    candidates = {pid for g in groups.values() for pid in g}
    games = dict(db.execute(select(MatchPlayer.player_id, func.count()).where(MatchPlayer.player_id.in_(candidates))
                            .group_by(MatchPlayer.player_id)).all())
    group_of = {pid: root for root, g in groups.items() for pid in g}
    together: Counter = Counter()  # group -> matches where two of its ids played
    per_match: dict[tuple[int, int], int] = Counter()
    for match_id, pid in db.execute(select(MatchPlayer.match_id, MatchPlayer.player_id)
                                    .where(MatchPlayer.player_id.in_(candidates))):
        key = (group_of[pid], match_id)
        per_match[key] += 1
        if per_match[key] == 2:
            together[group_of[pid]] += 1

    out = []
    for root, pids in groups.items():
        rows = []
        for pid in pids:
            uid, name, first, last = players[pid]
            rows.append({"user_id": uid, "name": name, "names": sorted(names_of[pid] - {name}),
                         "games": games.get(pid, 0), "first_seen_at": first, "last_seen_at": last,
                         "merged_ids": mains_with_aliases.get(uid, 0)})
        # keep: a player that already has merged ids, then the most games, then the earliest seen
        rows.sort(key=lambda r: (-r["merged_ids"], -r["games"], r["first_seen_at"]))
        exact = len({r["name"] for r in rows}) == 1
        out.append({"name": rows[0]["name"], "exact": exact, "played_together": together[root],
                    "keep": rows[0]["user_id"], "players": rows})
    # safest and biggest first: no shared matches, exact names, then the most games
    out.sort(key=lambda g: (g["played_together"] > 0, not g["exact"], -sum(r["games"] for r in g["players"])))
    return out[:MAX_GROUPS]
