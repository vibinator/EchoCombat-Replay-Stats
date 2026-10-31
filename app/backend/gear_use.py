"""Gear use per player: how many times each weapon / ordnance / tac mod was picked, in how many games, and its share
of the time held. Replays have no shot or use counts (docs/ReplayData.MD), only the equipped gear per frame.

A pick = switching to a piece of gear from a different one, plus the first one equipped. Frames with nothing
equipped (common around respawns) do not end a pick: Pulsar -> none -> Pulsar is 1 pick, Pulsar -> Nova -> Pulsar
is 2 Pulsar picks. Counted from the stored `loadout_change` events (stats/player.py: written whenever the
in-bounds weapon / tac mod / ordnance combination changes), so no replay has to be read again. Time held comes
from match_player_loadouts (in-bounds frames)."""

import json
from collections import Counter
from collections.abc import Iterable

from sqlalchemy import select

from parser.frames import gear_code

from .api.derived import gear, ratio
from .gear import ORDNANCES, TACMODS, WEAPONS
from .models import Event

KINDS = (("weapon", "weapons", WEAPONS), ("ordnance", "ordnances", ORDNANCES), ("tacmod", "tacmods", TACMODS))


def count_picks(changes: Iterable[dict]) -> dict[str, Counter]:
    """One player's loadout_change data in one match, in frame order -> {kind: Counter(code -> picks)}."""
    held = {kind: "" for kind, _, _ in KINDS}
    picks = {kind: Counter() for kind, _, _ in KINDS}
    for data in changes:
        for kind, _, _ in KINDS:
            code = gear_code(data.get(kind) or "")
            if code and code != held[kind]:
                picks[kind][code] += 1
                held[kind] = code
    return picks


def _picks(db, *where) -> dict[tuple[int, int], dict[str, Counter]]:
    rows = db.execute(
        select(Event.match_id, Event.player_id, Event.data)
        .where(Event.type == "loadout_change", Event.data.is_not(None), Event.player_id.is_not(None), *where)
        .order_by(Event.match_id, Event.player_id, Event.frame, Event.id)
    ).all()
    grouped: dict[tuple[int, int], list[dict]] = {}
    for match_id, player_id, data in rows:
        grouped.setdefault((match_id, player_id), []).append(json.loads(data))
    return {key: count_picks(changes) for key, changes in grouped.items()}


def picks_in_match(db, match_id: int) -> dict[int, dict[str, Counter]]:
    """player_id -> picks in this match."""
    return {player_id: p for (_, player_id), p in _picks(db, Event.match_id == match_id).items()}


def picks_of_player(db, player_id: int, match_ids) -> list[dict[str, Counter]]:
    """One player's picks per match, for the matches `match_ids` (a select of match ids) returns."""
    return list(_picks(db, Event.player_id == player_id, Event.match_id.in_(match_ids)).values())


def summarize(picks_per_match: Iterable[dict[str, Counter]], loadout_rows, games: bool = True) -> dict:
    """-> {"weapons" | "ordnances" | "tacmods": [{code, name, cut, picks, games?, share}]}, most time held first.
    `loadout_rows`: rows with weapon, tacmod, ordnance, frames (one player, one or many matches)."""
    picks_per_match = list(picks_per_match)
    out = {}
    for kind, key, table in KINDS:
        picks, played, frames = Counter(), Counter(), Counter()
        for m in picks_per_match:
            picks.update(m[kind])
            played.update(m[kind].keys())
        for r in loadout_rows:
            if code := gear_code(getattr(r, kind) or ""):
                frames[code] += r.frames
        total = sum(frames.values())
        items = []
        for code in sorted(set(picks) | set(frames), key=lambda c: (-frames[c], -picks[c], c)):
            item = gear(code, table) | {"picks": picks[code], "share": ratio(frames[code], total)}
            if games:
                item["games"] = played[code]
            items.append(item)
        out[key] = items
    return out
