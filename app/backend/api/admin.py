"""Staff endpoints under /api/admin: the Status page (admins and console users) and achievement icons (D43, changed
from the Console page's achievement export). The old Admin tab (achievement list + Excel) was removed (user,
2026-10-30): the Console export replaces it."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import auth, icons
from ..errors import ApiError
from .achievements import ranking_state
from .imports import import_status

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_icon_editor(request: Request) -> None:
    """Icons are changed from the Console page's achievement export: console access, asked from Discord every time."""
    if not auth.has_console(request, fresh=True):
        raise ApiError(403, "console_only", "Only console users can change icons")


@router.get("/status")
def status(request: Request):
    """Status page (admins and console users): live progress of replay processing and everything built from it
    (match stats, players, timeline events, position tracks / heatmaps, leaderboard, achievements)."""
    if not (auth.is_admin(request) or auth.has_console(request)):
        raise ApiError(403, "admin_only", "Only admins and console users can see the status")
    return import_status(request) | {"achievement_ranking": ranking_state(request.app.state.sessionmaker)}


@router.get("/icons")
def icon_choices(request: Request):
    """Icons an admin can pick: built-in badge art and earlier uploads (served under /achievements/)."""
    require_icon_editor(request)
    return icons.available(request.app.state.settings)


class IconChoice(BaseModel):
    icon: str | None  # None = back to the default


@router.put("/achievements/{rule_id}/icon")
def set_icon(request: Request, rule_id: int, choice: IconChoice):
    require_icon_editor(request)
    with request.app.state.sessionmaker() as db:
        try:
            icons.set_icon(db, request.app.state.settings, rule_id, choice.icon)
        except icons.IconError as e:
            raise ApiError(400, "bad_icon", str(e)) from None
    return {"id": rule_id, "icon": choice.icon or icons.default(rule_id)}


@router.post("/achievements/{rule_id}/icon")
async def upload_icon(request: Request, rule_id: int):
    """Body = the PNG file itself (Content-Type: image/png). Stored, then used for this achievement."""
    require_icon_editor(request)
    data = await request.body()
    settings = request.app.state.settings
    try:
        icon = icons.save_upload(settings, data)
        with request.app.state.sessionmaker() as db:
            icons.set_icon(db, settings, rule_id, icon)
    except icons.IconError as e:
        raise ApiError(400, "bad_icon", str(e)) from None
    return {"id": rule_id, "icon": icon}
