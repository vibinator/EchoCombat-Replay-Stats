"""Public Echo Arena match counts (arena.py), for the hidden Mega Prizes tab. Preview role only; separate from Combat."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from .. import auth
from ..errors import ApiError
from ..achievements import RULES, icon_file
from ..models import ArenaPlayer

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
    return {"target": TARGET, "min_minutes": 3, "combat": combat,
            "players": [{"user_id": r.user_id, "name": r.display_name or r.username, "matches": r.matches,
                         "completed": r.matches >= TARGET} for r in rows]}
