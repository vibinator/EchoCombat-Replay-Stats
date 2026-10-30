"""Console page (D45): admin.bat on the website, for Discord members with a role from ECHOVR_DISCORD_PREVIEW_ROLES.
Runs the admin console's own commands (app/admin_console.py) on the server's database and returns what they print,
so the page and admin.bat always do the same thing. The page asks for confirmation; commands run with --yes.
Who gets the preview / admin is not changed here: those lists are shown, but edited in admin.bat only."""

import contextlib
import io
import logging
import threading

from fastapi import APIRouter, Request
from pydantic import BaseModel

import admin_console as console

from .. import auth
from ..errors import ApiError

router = APIRouter(prefix="/api/admin/console", tags=["console"])
log = logging.getLogger("uvicorn.error")
_lock = threading.Lock()  # one command at a time: print() is captured for the whole process


class Args(BaseModel):
    term: str = ""
    main: str = ""
    others: list[str] = []
    alias: str = ""
    start: str | None = None  # None = keep, "" = no limit
    end: str | None = None
    clear: bool = False
    hide: bool = False
    unhide: str | None = None
    unhide_all: bool = False
    replay: str = ""
    user_id: str = ""


def _required(value: str, what: str) -> str:
    if not value.strip():
        raise console.ConsoleError(f"Enter {what}")
    return value.strip()


COMMANDS = {  # name as in admin.bat -> (sessions, settings, args) -> None
    "find": lambda s, st, a: console.cmd_find(s, _required(a.term, "a name or id")),
    "merge": lambda s, st, a: console.cmd_merge(s, _required(a.main, "the player to keep"),
                                                [o.strip() for o in a.others if o.strip()], yes=True, interactive=False),
    "merges": lambda s, st, a: console.cmd_merges(s),
    "unmerge": lambda s, st, a: console.cmd_unmerge(s, _required(a.alias, "the merged id"), yes=True),
    "challenge": lambda s, st, a: console.cmd_challenge(s, a.start, a.end, a.clear),
    "status": lambda s, st, a: console.cmd_status(s),
    "repair-failed": lambda s, st, a: console.cmd_repair_failed(s, yes=True),
    "cannot-repair": lambda s, st, a: console.cmd_cannot_repair(s, a.hide, yes=True),
    "hidden": lambda s, st, a: console.cmd_hidden(s, a.unhide or None, a.unhide_all, yes=True),
    "reprocess": lambda s, st, a: console.cmd_reprocess(s, _required(a.replay, "a replay id or path")),
    "repair": lambda s, st, a: console.cmd_repair(s, _required(a.replay, "a replay id or path")),
    "scan": lambda s, st, a: console.cmd_scan(s, st),
    "reprocess-all": lambda s, st, a: console.cmd_reprocess_all(s, st, yes=True),
    "preview-roles": lambda s, st, a: console.cmd_discord_roles(s, st, "preview", show_server=True),
    "admin-roles": lambda s, st, a: console.cmd_discord_roles(s, st, "admin", show_server=True),
    "admin-users": lambda s, st, a: console.cmd_admin_users(s, st),
    "discord-check": lambda s, st, a: console.cmd_discord_check(s, st, _required(a.user_id, "a Discord user id")),
}


@router.post("/{command}")
def run(request: Request, command: str, args: Args):
    if not auth.has_console(request):
        raise ApiError(403, "console_only", "Log in with Discord with a role from ECHOVR_DISCORD_PREVIEW_ROLES")
    if command not in COMMANDS:
        raise ApiError(404, "unknown_command", f"No console command '{command}'")
    user = auth.viewer(request)
    log.info("Console %s by %s (%s): %s", command, user["name"], user["id"], args.model_dump(exclude_defaults=True))
    out, ok = io.StringIO(), True
    with _lock, contextlib.redirect_stdout(out):
        try:
            COMMANDS[command](request.app.state.sessionmaker, request.app.state.settings, args)
        except console.ConsoleError as e:
            print(f"! {e}")
            ok = False
    return {"ok": ok, "output": out.getvalue()}
