"""Mega Prizes tab data (Preview role only; Arena counting is separate from Combat, see arena.py)."""

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from .. import auth
from ..achievements import MEGA_COMBAT, icon_file, mega_combat_games
from ..admin_actions import challenge_window
from ..errors import ApiError
from ..models import ArenaPlayer, Player
from .achievements import _games

router = APIRouter(prefix="/api/arena", tags=["arena"])
TARGET = 750  # Mega Prize: OG High Quality Jack Model
SEARCH_LIMIT = 10
IMAGES = {"jack.jpg": "image/jpeg", "biomass.jpg": "image/jpeg"}  # exact names only: nothing from the visitor reaches a path
IMAGE_DIR = Path(__file__).resolve().parent.parent / "private_assets"


def _require_preview(request: Request) -> None:
    if not auth.has_preview(request):
        raise ApiError(403, "no_access", "You do not have access")


@router.get("/image/{name}")
def image(request: Request, name: str):
    """The prize pictures. Not in the public folder: only the Preview role can load them."""
    _require_preview(request)
    if name not in IMAGES:
        raise ApiError(404, "not_found", "Not found")
    return FileResponse(IMAGE_DIR / name, media_type=IMAGES[name])


@router.get("/progress")
def progress(request: Request, limit: int = Query(10, ge=1, le=100)):
    _require_preview(request)
    with request.app.state.sessionmaker() as db:
        rows = db.scalars(select(ArenaPlayer).order_by(ArenaPlayer.matches.desc()).limit(limit)).all()
    r = MEGA_COMBAT  # kept out of RULES, so no public list or ranking has it
    combat = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r), "estimated": False,
               "new": r.new, "group": r.group, "levels": list(r.levels), "unit": r.unit, "prize": r.prize}]
    return {"target": TARGET, "min_minutes": 4, "combat": combat,
            "players": [{"user_id": r.user_id, "name": r.display_name or r.username, "matches": r.matches,
                         "completed": r.matches >= TARGET} for r in rows]}


@router.get("/search")
def search(request: Request, q: str = Query("", max_length=60)):
    """Players by name with their progress toward a prize, from the set challenge period on (no start date set = 0).
    Combat: games in the replay files. Arena: public matches of 4+ minutes from the live match list."""
    _require_preview(request)
    term = q.strip().lower().replace("%", "").replace("_", "")
    if len(term) < 2:
        return {"target": TARGET, "results": []}
    like = f"%{term}%"
    with request.app.state.sessionmaker() as db:
        start, end = challenge_window(db)
        players = db.scalars(select(Player).where(func.lower(Player.name).like(like))
                             .order_by(Player.last_seen_at.desc()).limit(SEARCH_LIMIT)).all()
        games = _games(db, [p.id for p in players]) if players and start else {}
        arena = db.scalars(select(ArenaPlayer).where(func.lower(ArenaPlayer.username).like(like)
                                                     | func.lower(func.coalesce(ArenaPlayer.display_name, "")).like(like))
                           .order_by(ArenaPlayer.matches.desc()).limit(SEARCH_LIMIT)).all()
    results = [{"kind": "combat", "name": p.name, "user_id": p.user_id,
                "matches": mega_combat_games(games.get(p.id, []), start, end) if start else 0} for p in players]
    results += [{"kind": "arena", "name": a.display_name or a.username, "user_id": a.user_id, "matches": a.matches} for a in arena]
    return {"target": TARGET, "results": results}
