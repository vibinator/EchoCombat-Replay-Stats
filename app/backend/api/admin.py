"""Admin tab (D42): Discord members with an admin role. Read-only like the rest of the website: changes are still
made in admin.bat. Built from the achievement rules on every request, so the list and the Excel file are always
current. The one change made here instead of admin.bat: achievement icons (D43), for admins only."""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .. import auth, icons
from ..achievement_sheet import COLUMNS, rows, workbook_bytes
from ..errors import ApiError
from ..version import APP_VERSION

router = APIRouter(prefix="/api/admin", tags=["admin"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def require_admin(request: Request) -> None:
    if not auth.is_admin(request):
        raise ApiError(403, "admin_only", "Admins only: log in with Discord with an admin role")


@router.get("/achievements")
def achievement_list(request: Request):
    """Every achievement / challenge with how to get it (the same rows as the Excel file)."""
    require_admin(request)
    with request.app.state.sessionmaker() as db:
        chosen = icons.overrides(db)
    items = [r | {"default_icon": icons.default(r["id"]), "icon": chosen.get(r["id"], icons.default(r["id"]))}
             for r in rows()]
    return {"columns": [{"key": k, "label": label} for k, label, _ in COLUMNS], "items": items}


@router.get("/icons")
def icon_choices(request: Request):
    """Icons an admin can pick: built-in badge art and earlier uploads (served under /achievements/)."""
    require_admin(request)
    return icons.available(request.app.state.settings)


class IconChoice(BaseModel):
    icon: str | None  # None = back to the default


@router.put("/achievements/{rule_id}/icon")
def set_icon(request: Request, rule_id: int, choice: IconChoice):
    require_admin(request)
    with request.app.state.sessionmaker() as db:
        try:
            icons.set_icon(db, request.app.state.settings, rule_id, choice.icon)
        except icons.IconError as e:
            raise ApiError(400, "bad_icon", str(e)) from None
    return {"id": rule_id, "icon": choice.icon or icons.default(rule_id)}


@router.post("/achievements/{rule_id}/icon")
async def upload_icon(request: Request, rule_id: int):
    """Body = the PNG file itself (Content-Type: image/png). Stored, then used for this achievement."""
    require_admin(request)
    data = await request.body()
    settings = request.app.state.settings
    try:
        icon = icons.save_upload(settings, data)
        with request.app.state.sessionmaker() as db:
            icons.set_icon(db, settings, rule_id, icon)
    except icons.IconError as e:
        raise ApiError(400, "bad_icon", str(e)) from None
    return {"id": rule_id, "icon": icon}


@router.get("/achievements.xlsx")
def achievement_workbook(request: Request):
    require_admin(request)
    return Response(workbook_bytes(APP_VERSION), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="EchoVR-Achievements.xlsx"'})
