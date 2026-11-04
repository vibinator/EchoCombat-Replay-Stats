"""Public Echo Arena match counts (arena.py), for the hidden Mega Prizes tab. Preview role only; separate from Combat."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from .. import auth
from ..errors import ApiError
from ..achievements import RULES, icon_file
from ..admin_actions import challenge_window
from ..achievements import in_window
from ..models import Player
from .achievements import _games
from ..models import ArenaPlayer, PlayerProfile

router = APIRouter(prefix="/api/arena", tags=["arena"])
TARGET = 750  # Mega Prize: OG High Quality Jack Model


@router.get("/progress")
def progress(request: Request, limit: int = Query(10, ge=1, le=100)):
    if not auth.has_preview(request):
        raise ApiError(403, "no_access", "Mega Prizes are only for the Preview role")
    with request.app.state.sessionmaker() as db:
        rows = db.scalars(select(ArenaPlayer).order_by(ArenaPlayer.matches.desc()).limit(limit)).all()
    combat = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r), "estimated": False,
               "new": r.new, "group": r.group, "levels": list(r.levels), "unit": r.unit, "prize": r.prize}
              for r in RULES if r.prize]  # the Combat Mega Prize challenges (kept out of the public lists)
    return {"target": TARGET, "min_minutes": 4, "combat": combat, "me": _me(request),
            "players": [{"user_id": r.user_id, "name": r.display_name or r.username, "matches": r.matches,
                         "completed": r.matches >= TARGET} for r in rows]}


def _me(request: Request) -> dict | None:
    """The visitor's own progress, from the set challenge period on: Arena matches (by Discord id on the Nakama list) and
    Combat games (the player their Discord account is linked to on the website). None = not logged in."""
    viewer = auth.viewer(request)
    if viewer is None:
        return None
    with request.app.state.sessionmaker() as db:
        arena = db.scalar(select(ArenaPlayer.matches).where(ArenaPlayer.discord_id == viewer["id"]))
        user_id = db.scalar(select(PlayerProfile.user_id).where(PlayerProfile.discord_id == viewer["id"]))
    combat = None
    if user_id:  # Combat games started inside the set challenge period (no start date set = none yet)
        with request.app.state.sessionmaker() as db:
            start, end = challenge_window(db)
            player = db.scalar(select(Player).where(Player.user_id == user_id))
            games = _games(db, [player.id]).get(player.id, []) if player and start else []
        combat = len(in_window(games, start, end))
    return {"name": viewer["name"], "arena": arena or 0, "combat": combat, "combat_linked": user_id is not None}
