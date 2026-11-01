"""Console page (D45): admin.bat on the website, for Discord members with a role from ECHOVR_DISCORD_PREVIEW_ROLES.
Runs the admin console's own commands (app/admin_console.py) on the server's database and returns what they print,
so the page and admin.bat always do the same thing. The page asks for confirmation; commands run with --yes.
Who gets the preview / admin / console is managed on the Permissions page (api/permissions.py)."""

import contextlib
import io
import logging
import re
import threading

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

import admin_console as console

from .. import auth, icons
from .. import merge_suggestions as suggestions
from ..achievement_sheet import csv_bytes, name_and_rule
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


def require_console(request: Request, what: str) -> dict:
    """The logged-in visitor, if they may use the console; roles are asked from Discord every time."""
    user = auth.viewer(request)
    if not auth.has_console(request, fresh=True):
        if user:
            log.warning("Console %s refused for %s (%s): no console access", what, user["name"], user["id"])
        raise ApiError(403, "console_only", "You do not have access to the console")
    return user


@router.get("/achievements")
def achievements(request: Request):
    """Every achievement and challenge: name, the rule to win it (same text as on the website) and its icon."""
    require_console(request, "achievements")
    with request.app.state.sessionmaker() as db:
        chosen = icons.overrides(db)
    return [r | {"default_icon": icons.default(r["id"]), "icon": chosen.get(r["id"], icons.default(r["id"]))}
            for r in name_and_rule()]


@router.get("/merge-suggestions")
def merge_suggestions(request: Request):
    """Player records that used the same name: candidates for "Merge player records" (only suggestions)."""
    require_console(request, "merge-suggestions")
    with request.app.state.sessionmaker() as db:
        return suggestions.suggestions(db)


@router.get("/achievements.csv")
def achievements_csv(request: Request):
    require_console(request, "achievements.csv")
    return Response(csv_bytes(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="EchoVR-Achievements.csv"'})


@router.post("/{command}")
def run(request: Request, command: str, args: Args):
    user = require_console(request, command)
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
