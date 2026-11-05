"""Mega Prize winners report for the Console (user, 2026-11-04): the prizes are handed out by hand, so this lists who has
reached the target inside the set challenge period. Echo Combat: 1000 games of 4+ minutes from the replay files (Delta-13 from Lone Echo 2).
Public Arena: 1000 matches of 4+ minutes counted from the live Nakama match list (arena.py; Jack Series 11 from
Lone Echo 1/2). Counted inside the Mega Prize period (its own Start-End dates, apart from the achievements')."""

import csv
from io import StringIO

from sqlalchemy import select

from .achievements import MEGA_COMBAT, mega_combat_games
from .admin_actions import mega_window
from .api.achievements import _games
from .api.arena import TARGET as ARENA_TARGET
from .models import ArenaPlayer, Player, PlayerProfile

ARENA_PRIZE = "Jack Series 11 from Lone Echo 1/2"


def report(db) -> dict:
    start, end = mega_window(db)
    combat_rule = MEGA_COMBAT
    target = int(combat_rule.levels[-1])
    combat: list[dict] = []
    arena: list[dict] = []
    if start:  # no start date set = no period yet, nobody has won anything
        games = _games(db)
        discord = dict(db.execute(select(PlayerProfile.user_id, PlayerProfile.discord_id)).all())
        for p in db.scalars(select(Player)):
            n = mega_combat_games(games.get(p.id, []), start, end)
            if n >= target:
                combat.append({"name": p.name, "user_id": p.user_id, "discord_id": discord.get(p.user_id), "count": n})
        combat.sort(key=lambda w: -w["count"])
        arena = [{"name": r.display_name or r.username, "user_id": r.user_id, "discord_id": r.discord_id, "count": r.matches}
                 for r in db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches >= ARENA_TARGET).order_by(ArenaPlayer.matches.desc()))]
    return {"period": {"start": start, "end": end},
            "prizes": [{"prize": combat_rule.prize, "challenge": f"Play {target} Echo Combat Matches", "target": target, "winners": combat},
                       {"prize": ARENA_PRIZE, "challenge": f"Play {ARENA_TARGET} Public Arena Matches", "target": ARENA_TARGET, "winners": arena}]}


def _cell(value) -> str:
    """Spreadsheet formula injection: a name starting with = + - @ (or a tab / CR) would run as a formula when the CSV is
    opened in Excel or Sheets, so such a cell gets a leading apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_bytes(data: dict) -> bytes:
    """One row per winner; UTF-8 with BOM so Excel shows names correctly."""
    out = StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["Prize", "Challenge", "Name", "Player id", "Discord id", "Matches", "Period start", "Period end"])
    for p in data["prizes"]:
        for w in p["winners"]:
            writer.writerow([_cell(x) for x in (p["prize"], p["challenge"], w["name"], w["user_id"], w["discord_id"] or "", w["count"],
                                                data["period"]["start"] or "", data["period"]["end"] or "")])
    return out.getvalue().encode("utf-8-sig")
