"""Console page (D45): admin.bat on the website, for Discord members with a role from ECHOVR_DISCORD_PREVIEW_ROLES.
Runs the admin console's own commands (app/admin_console.py) on the server's database and returns what they print,
so the page and admin.bat always do the same thing. The page asks for confirmation; commands run with --yes.
Who gets the preview / admin is not changed here: those lists are shown, but edited in admin.bat only."""

import contextlib
import io
import logging
import re
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
    # only the roles that are set: the console's list of every server role is for picking one, not possible here
    "preview-roles": lambda s, st, a: console.cmd_discord_roles(s, st, "preview"),
    "admin-roles": lambda s, st, a: console.cmd_discord_roles(s, st, "admin"),
    "admin-users": lambda s, st, a: console.cmd_admin_users(s, st),
    "discord-check": lambda s, st, a: console.cmd_discord_check(s, st, _required(a.user_id, "a Discord user id")),
}


# The console names its own commands; on the page they are buttons (labels in ConsolePage.tsx). Each phrase must
# still appear in admin_console.py (checked by a test), so a changed console message cannot slip through unrenamed.
WEB_WORDING = (
    ("Use the merged id from 'merges'.", "Use the merged id from “List merges”."),
    ("'cannot-repair' lists them", "“Replays that cannot be repaired” lists them"),
    ("show up under 'cannot-repair'", "show up under “Replays that cannot be repaired”"),
    ("'hidden' lists them", "“Hidden replays” lists them"),
    ("Progress: 'admin.bat status'.", "Progress: “Status and import progress”."),
)
SERVER_LINE = re.compile(r"^Server: running \(http://[^)]*\)$", re.M)
OPTION = re.compile(r"(?<!admin\.bat )option (1[4-7])")  # access settings: changed in admin.bat only


def for_the_page(text: str) -> str:
    for old, new in WEB_WORDING:
        text = text.replace(old, new)
    text = SERVER_LINE.sub("Server: running", text)
    return OPTION.sub(r"admin.bat option \1", text).replace(" -> ", " → ")


@router.post("/{command}")
def run(request: Request, command: str, args: Args):
    user = auth.viewer(request)
    if not auth.has_console(request, fresh=True):  # roles asked from Discord on every command
        if user:
            log.warning("Console %s refused for %s (%s): no console access", command, user["name"], user["id"])
        raise ApiError(403, "console_only", "You do not have access to the console")
    if command not in COMMANDS:
        raise ApiError(404, "unknown_command", f"No console command '{command}'")
    log.info("Console %s by %s (%s): %s", command, user["name"], user["id"], args.model_dump(exclude_defaults=True))
    out, ok = io.StringIO(), True
    running = console.server_running
    with _lock, contextlib.redirect_stdout(out):
        console.server_running = lambda: True  # this is the server: queued replays are picked up at once
        try:
            COMMANDS[command](request.app.state.sessionmaker, request.app.state.settings, args)
        except console.ConsoleError as e:
            print(e)
            ok = False
        finally:
            console.server_running = running
    return {"ok": ok, "output": for_the_page(out.getvalue()).strip()}
