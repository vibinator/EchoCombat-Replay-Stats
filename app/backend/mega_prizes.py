"""Mega Prize winners report for the Console (user, 2026-11-04): the prizes are handed out by hand, so this lists who has
reached the target inside the set challenge period. Echo Combat: 750 games from the replay files (Delta Squad BioMass
Chassis). Public Arena: 750 matches of 4+ minutes counted from the live Nakama match list (arena.py; OG High Quality
Jack Model)."""

import csv
from io import StringIO

from sqlalchemy import select

from .achievements import RULES, in_window
from .admin_actions import challenge_window
from .api.achievements import _games
from .api.arena import TARGET as ARENA_TARGET
from .models import ArenaPlayer, Player, PlayerProfile

ARENA_PRIZE = "OG High Quality Jack Model"


def report(db) -> dict:
    start, end = challenge_window(db)
    combat_rule = next(r for r in RULES if r.prize)
    target = int(combat_rule.levels[-1])
    combat: list[dict] = []
    arena: list[dict] = []
    if start:  # no start date set = no period yet, nobody has won anything
        games = _games(db)
        discord = dict(db.execute(select(PlayerProfile.user_id, PlayerProfile.discord_id)).all())
        for p in db.scalars(select(Player)):
            n = len(in_window(games.get(p.id, []), start, end))
            if n >= target:
                combat.append({"name": p.name, "user_id": p.user_id, "discord_id": discord.get(p.user_id), "count": n})
        combat.sort(key=lambda w: -w["count"])
        arena = [{"name": r.display_name or r.username, "user_id": r.user_id, "discord_id": r.discord_id, "count": r.matches}
                 for r in db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches >= ARENA_TARGET).order_by(ArenaPlayer.matches.desc()))]
    return {"period": {"start": start, "end": end},
            "prizes": [{"prize": combat_rule.prize, "challenge": "Play 750 Echo Combat Matches", "target": target, "winners": combat},
                       {"prize": ARENA_PRIZE, "challenge": "Play 750 Public Arena Matches", "target": ARENA_TARGET, "winners": arena}]}


def csv_bytes(data: dict) -> bytes:
    """One row per winner; UTF-8 with BOM so Excel shows names correctly."""
    out = StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["Prize", "Challenge", "Name", "Player id", "Discord id", "Matches", "Period start", "Period end"])
    for p in data["prizes"]:
        for w in p["winners"]:
            writer.writerow([p["prize"], p["challenge"], w["name"], w["user_id"], w["discord_id"] or "", w["count"],
                             data["period"]["start"] or "", data["period"]["end"] or ""])
    return out.getvalue().encode("utf-8-sig")
