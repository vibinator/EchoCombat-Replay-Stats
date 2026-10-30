"""Permissions page (user, 2026-10-30): console users give or take away Admin (the Status page), the Console and the Preview,
by Discord role or by a person's user id. Stored in app_settings (kept across rebuilds), the same lists admin.bat
options 14, 15 and 17 edit. The ids in ECHOVR_DISCORD_PREVIEW_ROLES (YAML) are shown as fixed: they always give
the console and cannot be removed here, so nobody can lock the owner out."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import auth
from ..admin_actions import PERMISSIONS, AdminError, add_discord_role, discord_roles, remove_discord_role
from ..errors import ApiError
from .console import require_console

router = APIRouter(prefix="/api/admin/permissions", tags=["permissions"])
log = logging.getLogger("uvicorn.error")


def _server_roles(settings) -> list[dict] | None:
    """The Discord server's roles, or None when the bot cannot list them (ids still work, without names)."""
    if not settings.discord_bot_token:
        return None
    try:
        return auth.server_roles(settings)
    except Exception:
        return None


def _state(request: Request) -> dict:
    settings = request.app.state.settings
    server = _server_roles(settings)
    names = {r["id"]: r["name"] for r in server or []}
    server_ids = set(names)

    def entry(i: str, kind: str) -> dict:
        return {"id": i, "name": names.get(i, "?") if kind == "role" else auth.user_name(settings, i)}

    with request.app.state.sessionmaker() as db:
        lists = {p: {"roles": [entry(i, "role") for i in discord_roles(db, p)],
                     "users": [entry(i, "user") for i in discord_roles(db, f"{p}_user")]} for p in PERMISSIONS}
    # without the server's roles the YAML ids cannot be told apart: shown as roles when unsure
    fixed = [entry(i, "user" if server is not None and i not in server_ids else "role")
             | {"type": "user" if server is not None and i not in server_ids else "role"}
             for i in settings.discord_preview_roles]
    return {"permissions": lists, "fixed": fixed, "server_roles": server}


@router.get("")
def permissions(request: Request):
    require_console(request, "permissions")
    return _state(request)


class Change(BaseModel):
    permission: str  # admin | console | preview
    type: str  # role | user
    id: str
    remove: bool = False


@router.post("")
def change(request: Request, change: Change):
    user = require_console(request, "permissions change")
    settings = request.app.state.settings
    if change.permission not in PERMISSIONS or change.type not in ("role", "user"):
        raise ApiError(400, "bad_permission", "Unknown permission or type")
    discord_id = change.id.strip()
    if change.permission == "console" and discord_id in settings.discord_preview_roles:
        raise ApiError(400, "fixed", "This id is set in ECHOVR_DISCORD_PREVIEW_ROLES (the YAML): change it there")
    server = _server_roles(settings)
    if not change.remove and server is not None:  # a person's id is not a role, and the other way round
        is_role = discord_id in {r["id"] for r in server}
        if change.type == "role" and not is_role:
            raise ApiError(400, "not_a_role", f"{discord_id} is not a role in the Discord server. For a person, choose User.")
        if change.type == "user" and is_role:
            raise ApiError(400, "not_a_user", f"{discord_id} is a role, not a person. Choose Role for it.")
    kind = change.permission if change.type == "role" else f"{change.permission}_user"
    with request.app.state.sessionmaker() as db:
        try:
            (remove_discord_role if change.remove else add_discord_role)(db, kind, discord_id)
        except AdminError as e:
            raise ApiError(400, "bad_id", str(e)) from None
    log.warning("Permissions: %s %s %s %s by %s (%s)", "removed" if change.remove else "added", change.permission,
                change.type, discord_id, user["name"], user["id"])
    return _state(request)
