"""Stored counts -> display stats (DataModel.MD "Derived"). Shared by match and player endpoints."""

from datetime import date, datetime, timedelta

from ..gear import ORDNANCES, TACMODS, WEAPONS, lookup
from ..models import Match


def ratio(numerator: float | None, denominator: float | None, digits: int = 4) -> float | None:
    return round(numerator / denominator, digits) if numerator is not None and denominator else None


def dominant_arm(left: int, right: int) -> str | None:
    if not left and not right:
        return None
    return "Right" if right >= left else "Left"


def gear(code: str, table) -> dict:
    g = lookup(table, code)
    return {"code": code, "name": g.display_name, "cut": g.cut}


def loadout(weapon: str, tacmod: str, ordnance: str, frames: int, total: int) -> dict:
    return {
        "weapon": gear(weapon, WEAPONS),
        "tacmod": gear(tacmod, TACMODS),
        "ordnance": gear(ordnance, ORDNANCES),
        "frames": frames,
        "share": ratio(frames, total),
    }


def match_summary(m: Match, player_count: int | None = None) -> dict:
    return {
        "id": m.id,
        "replay_id": m.replay_id,
        "session_id": m.session_id,
        "map": m.map,
        "mode": m.mode,
        "started_at": m.started_at,
        "duration_s": m.duration_s,
        "blue_rounds": m.blue_rounds,
        "orange_rounds": m.orange_rounds,
        "final_payload_checkpoint": m.final_payload_checkpoint,
        "attacking_team": m.attacking_team,
        "winner": m.winner,
        "player_count": player_count,
    }


PERIODS = ("day", "week", "month", "all")


def period_start(period: str, today: date | None = None) -> str | None:
    """Calendar period start in recorder-local time (D17), as an ISO prefix comparable to started_at."""
    today = today or datetime.now().date()
    if period == "day":
        start = today
    elif period == "week":
        start = today - timedelta(days=today.weekday())
    elif period == "month":
        start = today.replace(day=1)
    else:
        return None
    return start.isoformat()
