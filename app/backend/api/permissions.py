"""Permissions page (user, 2026-10-30): console users give or take away Admin (the Status page), the Console and the Preview,
by Discord role or by a person's user id. Stored in app_settings (kept across rebuilds), the same lists admin.bat
options 14, 15 and 17 edit. The ids in ECHOVR_DISCORD_PREVIEW_ROLES (YAML) are shown as fixed: they always give
the console and cannot be removed here, so nobody can lock the owner out.

The Cloud lists (Cloud view / edit / admin) are not set here (user, 2026-11-16: the Cloud is separate from the
Console): Cloud admins set them on the Cloud page (api/cloud.py, /api/cloud/access), with the same code below."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import auth
from ..admin_actions import (CLOUD_PERMISSIONS, SITE_PERMISSIONS, AdminError, add_discord_role, discord_roles,
                             remove_discord_role)
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


def fixed_ids(settings, kinds: tuple[str, ...]) -> tuple[str, ...]:
    """The YAML ids that cannot be removed on the page: the preview roles give the Console, the Cloud admin ids Cloud admin."""
    return settings.discord_cloud_admins if "cloud_admin" in kinds else settings.discord_preview_roles


def state(request: Request, kinds: tuple[str, ...] = SITE_PERMISSIONS) -> dict:
    """The lists of `kinds`, with names. fixed: the YAML ids (fixed_ids)."""
    settings = request.app.state.settings
    server = _server_roles(settings)
    names = {r["id"]: r["name"] for r in server or []}
    server_ids = set(names)
    with request.app.state.sessionmaker() as db:
        ids = {p: (discord_roles(db, p), discord_roles(db, f"{p}_user")) for p in kinds}
    # without the server's roles the YAML ids cannot be told apart: shown as roles when unsure
    fixed_kind = {i: "user" if server is not None and i not in server_ids else "role" for i in fixed_ids(settings, kinds)}
    people = auth.user_names(settings, [i for _, users in ids.values() for i in users]
                             + [i for i, kind in fixed_kind.items() if kind == "user"])
    lists = {p: {"roles": [{"id": i, "name": names.get(i, "?")} for i in roles],
                 "users": [{"id": i, "name": people.get(i, "?")} for i in users]} for p, (roles, users) in ids.items()}
    fixed = [{"id": i, "name": names.get(i, "?") if kind == "role" else people.get(i, "?"), "type": kind}
             for i, kind in fixed_kind.items()]
    return {"permissions": lists, "fixed": fixed, "server_roles": server}


@router.get("")
def permissions(request: Request):
    require_console(request, "permissions")
    return state(request)


class Change(BaseModel):
    permission: str  # admin | console | preview (here); cloud_view | cloud_edit | cloud_admin (/api/cloud/access)
    type: str  # role | user
    id: str
    remove: bool = False


def apply(request: Request, user: dict, change: Change, kinds: tuple[str, ...], fixed_for: str) -> None:
    """One id added to or removed from a list of `kinds`. fixed_for: the permission the YAML ids always give."""
    settings = request.app.state.settings
    if change.permission not in kinds or change.type not in ("role", "user"):
        raise ApiError(400, "bad_permission", "Unknown permission or type")
    discord_id = change.id.strip()
    if change.permission == fixed_for and discord_id in fixed_ids(settings, kinds):
        name = "ECHOVR_DISCORD_CLOUD_ADMINS" if fixed_for == "cloud_admin" else "ECHOVR_DISCORD_PREVIEW_ROLES"
        raise ApiError(400, "fixed", f"This id is set in {name} (the YAML): change it there")
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


@router.post("")
def change(request: Request, change: Change):
    user = require_console(request, "permissions change")
    if change.permission in CLOUD_PERMISSIONS:
        raise ApiError(400, "cloud_page", "Cloud permissions are set on the Cloud page (All permissions), by Cloud admins")
    apply(request, user, change, SITE_PERMISSIONS, "console")
    return state(request)
