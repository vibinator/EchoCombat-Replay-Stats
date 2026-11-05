"""Mega Prizes tab data (Preview role only; Arena counting is separate from Combat, see arena.py)."""

from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from .. import auth
from ..achievements import MEGA_COMBAT, icon_file
from ..admin_actions import mega_window
from ..errors import ApiError
from ..models import ArenaPlayer, NakamaCombatCounted, NakamaCombatPlayer

router = APIRouter(prefix="/api/arena", tags=["arena"])
TARGET = 1000  # Mega Prize: Jack Series 11 from Lone Echo 1/2
SEARCH_LIMIT = 10
CLOSEST = 2  # players shown as "closest to the prize"
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
        rows = db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches >= TARGET)
                         .order_by(ArenaPlayer.matches.desc()).limit(limit)).all()  # only those who reached it (user, 2026-11-04)
        near_arena = db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches < TARGET)
                                .order_by(ArenaPlayer.matches.desc()).limit(CLOSEST)).all()
        combat_target = int(MEGA_COMBAT.levels[-1])
        near_combat = _closest_combat(db, combat_target)
        won_arena = db.scalar(select(func.count()).select_from(ArenaPlayer).where(ArenaPlayer.matches >= TARGET)) or 0
        won_combat = _combat_winners(db, combat_target)
        period = mega_window(db)
    r = MEGA_COMBAT  # kept out of RULES, so no public list or ranking has it
    combat = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r), "estimated": False,
               "new": r.new, "group": r.group, "levels": list(r.levels), "unit": r.unit, "prize": r.prize}]
    today = date.today().isoformat()
    return {"target": TARGET, "min_minutes": 4, "combat": combat,
            # the Mega Prize period (its own dates, or the challenge period): the cards show a live dot while it is running
            "period": {"start": period[0], "end": period[1], "active": bool(period[0]) and period[0] <= today and (not period[1] or today <= period[1])},
            "players": [{"user_id": r.user_id, "name": r.display_name or r.username, "matches": r.matches,
                         "completed": r.matches >= TARGET} for r in rows],
            # the two players nearest to the prize who have not reached it yet (user, 2026-11-04)
            "winners_combat": won_combat, "winners_arena": won_arena,
            "closest_combat": near_combat,
            "closest_arena": [{"user_id": a.user_id, "name": a.display_name or a.username, "matches": a.matches} for a in near_arena]}


def combat_totals(db, start: str | None, end: str | None) -> list[dict]:
    """Echo Combat matches per player for the Mega Prize (user, 2026-11-05): counted from the Nakama match list only, like
    Arena. The replay files are not part of it (the prizes launch later, so no history is merged). Counted inside the Mega
    Prize period, most matches first."""
    if not start:
        return []
    lo = datetime.fromisoformat(start).timestamp()
    hi = datetime.fromisoformat(end).timestamp() + 86400 if end else None
    n = func.count().label("n")
    q = (select(NakamaCombatCounted.user_id, NakamaCombatPlayer.display_name, NakamaCombatPlayer.username,
                NakamaCombatPlayer.discord_id, n)
         .join(NakamaCombatPlayer, NakamaCombatPlayer.user_id == NakamaCombatCounted.user_id)
         .where(NakamaCombatCounted.counted_at >= lo).group_by(NakamaCombatCounted.user_id).order_by(n.desc()))
    if hi:
        q = q.where(NakamaCombatCounted.counted_at < hi)
    return [{"name": display or username, "user_id": user_id, "discord_id": discord_id, "count": count}
            for user_id, display, username, discord_id, count in db.execute(q)]


def _closest_combat(db, target: int) -> list[dict]:
    """The CLOSEST players below the Combat target."""
    start, end = mega_window(db)
    below = [w for w in combat_totals(db, start, end) if w["count"] < target][:CLOSEST]
    return [{"user_id": w["user_id"], "name": w["name"], "matches": w["count"]} for w in below]


def _combat_winners(db, target: int) -> int:
    """How many players reached the Combat target inside the challenge period."""
    start, end = mega_window(db)
    return sum(1 for w in combat_totals(db, start, end) if w["count"] >= target)


@router.get("/search")
def search(request: Request, q: str = Query("", max_length=60)):
    """Players by name with their progress toward a prize, from the set challenge period on (no start date set = 0).
    Combat and Arena: public matches of 4+ minutes from the live match list. Arena: public matches of 4+ minutes from the live match list."""
    _require_preview(request)
    term = q.strip().lower().replace("%", "").replace("_", "")
    if len(term) < 2:
        return {"target": TARGET, "results": []}
    like = f"%{term}%"
    with request.app.state.sessionmaker() as db:
        start, end = mega_window(db)
        combat = [w for w in combat_totals(db, start, end) if term in (w["name"] or "").lower()][:SEARCH_LIMIT]
        arena = db.scalars(select(ArenaPlayer).where(func.lower(ArenaPlayer.username).like(like)
                                                     | func.lower(func.coalesce(ArenaPlayer.display_name, "")).like(like))
                           .order_by(ArenaPlayer.matches.desc()).limit(SEARCH_LIMIT)).all()
    results = [{"kind": "combat", "name": w["name"], "user_id": w["user_id"], "matches": w["count"]} for w in combat]
    results += [{"kind": "arena", "name": a.display_name or a.username, "user_id": a.user_id, "matches": a.matches} for a in arena]
    return {"target": TARGET, "results": results}
