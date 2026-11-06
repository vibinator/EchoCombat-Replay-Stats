"""Console page (D45): admin.bat on the website, for Discord members with a role from ECHOVR_DISCORD_PREVIEW_ROLES.
Runs the admin console's own commands (app/admin_console.py) on the server's database and returns what they print,
so the page and admin.bat always do the same thing. The page asks for confirmation; commands run with --yes.
Who gets the preview / admin / console is managed on the Permissions page (api/permissions.py)."""

import contextlib
import io
import json
import logging
import re
import threading

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, not_, select

import admin_console as console

from .. import admin_actions as actions
from .. import auth, icons
from .. import merge_suggestions as suggestions
from ..admin_actions import hidden_failure, unrepairable
from ..models import Player, PlayerAlias, Replay
from .. import mega_prizes
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
    discord_id: str = ""
    hide_win_loss: bool = False
    show_win_loss: bool = False
    player: str = ""
    visible: str = ""  # challenge: "everyone", "preview" or "hidden"; empty = keep
    mode: str = ""  # remote: "server", "remote" or "both"; empty = only show the setting


def _required(value: str, what: str) -> str:
    if not value.strip():
        raise console.ConsoleError(f"Enter {what}")
    return value.strip()


COMMANDS = {  # name as in admin.bat -> (sessions, settings, args) -> None
    "find": lambda s, st, a: console.cmd_find(s, _required(a.term, "a name or id")),
    "merge": lambda s, st, a: console.cmd_merge(s, _required(a.main, "the player to keep"),
                                                [o.strip() for o in a.others if o.strip()], yes=True, interactive=False),
    "merges": lambda s, st, a: console.cmd_merges(s),
    "link-profile": lambda s, st, a: console.cmd_link_profile(s, _required(a.player, "the player"), _required(a.discord_id, "a Discord user id"), yes=True),
    "unlink-profile": lambda s, st, a: console.cmd_unlink_profile(s, _required(a.player or a.discord_id, "a player or Discord id"), yes=True),
    "profile-links": lambda s, st, a: console.cmd_profile_links(s),
    "unmerge": lambda s, st, a: console.cmd_unmerge(s, _required(a.alias, "the merged id"), yes=True),
    "challenge": lambda s, st, a: console.cmd_challenge(s, a.start, a.end, a.clear, a.visible or None),
    "mega-period": lambda s, st, a: console.cmd_mega_period(s, a.start, a.end, a.clear, a.visible or None),
    "status": lambda s, st, a: console.cmd_status(s),
    "repair-failed": lambda s, st, a: console.cmd_repair_failed(s, yes=True),
    "cannot-repair": lambda s, st, a: console.cmd_cannot_repair(s, a.hide, yes=True),
    "hidden": lambda s, st, a: console.cmd_hidden(s, a.unhide or None, a.unhide_all, yes=True),
    "reprocess": lambda s, st, a: console.cmd_reprocess(s, _required(a.replay, "a replay id or path")),
    "repair": lambda s, st, a: console.cmd_repair(s, _required(a.replay, "a replay id or path")),
    "repair-aggressive": lambda s, st, a: console.cmd_repair_aggressive(s, _required(a.replay, "a replay id or path")),
    "repair-aggressive-failed": lambda s, st, a: console.cmd_repair_aggressive_failed(s, yes=True),
    "scan": lambda s, st, a: console.cmd_scan(s, st),
    "process-missing": lambda s, st, a: console.cmd_process_missing(s, st),
    "reprocess-all": lambda s, st, a: console.cmd_reprocess_all(s, st, yes=True),
    "hide-stats": lambda s, st, a: console.cmd_hide_stats(s, "win_loss" if a.hide_win_loss else None,
                                                          "win_loss" if a.show_win_loss else None, a.player),
    "remote": lambda s, st, a: console.cmd_remote_mode(s, a.mode or None),
    "remote-on": lambda s, st, a: console.cmd_remote_processing(s, True),
    "remote-off": lambda s, st, a: console.cmd_remote_processing(s, False),
    "remote-status": lambda s, st, a: console.cmd_remote_processing(s, None),
    "discord-check": lambda s, st, a: console.cmd_discord_check(s, st, _required(a.user_id, "a Discord user id")),
}


# The console names its own commands; on the page they are buttons (labels in ConsolePage.tsx). Each phrase must
# still appear in admin_console.py (checked by a test), so a changed console message cannot slip through unrenamed.
WEB_WORDING = (
    ("Use the merged id from 'merges'.", "Use the merged id from “List merges”."),
    ("'cannot-repair' lists them", "“Replays that cannot be repaired” lists them"),
    ("show up under 'cannot-repair'", "show up under “Replays that cannot be repaired”"),
    ("'repair-aggressive-failed' tries harder", "“Aggressive repair of broken replays” tries harder"),
    ("can be tried with 'repair-aggressive-failed'", "can be tried with “Aggressive repair of broken replays”"),
    ("run 'repair-failed' first", "run “Repair all failed replays” first"),
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


def require_console(request: Request, what: str, fresh: bool = True) -> dict:
    """The logged-in visitor, if they may use the console; roles are asked from Discord every time (fresh), except
    for the views the page refreshes by itself (dashboard, lists): those use the roles remembered for 5 minutes."""
    user = auth.viewer(request)
    if not auth.has_console(request, fresh=fresh):
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


def _log_row(r) -> dict:
    return {"id": r.id, "at": r.at, "source": r.source, "who": r.who_name, "who_id": r.who_id, "command": r.command,
            "args": json.loads(r.args) if r.args else {}, "ok": r.ok, "output": r.output or ""}


@router.get("/overview")
def overview(request: Request):
    """Dashboard facts the Status page does not have: players, merges, failures, hidden stats, the challenge period
    and the latest console commands. Processing progress comes from /api/admin/status."""
    require_console(request, "overview", fresh=False)
    tracker = getattr(request.app.state, "arena", None)  # only started with auto_scan
    with request.app.state.sessionmaker() as db:
        start, end = actions.challenge_window(db)
        mega_start, mega_end = actions.mega_window_own(db)
        hidden = actions.hidden_stats(db)
        hidden_players = {g: [{"user_id": u, "name": console.name_of(db, u)} for u in actions.hidden_players(db, g)]
                          for g in actions.STAT_GROUPS}
        return {
            "players": db.scalar(select(func.count()).select_from(Player)),
            "merges": db.scalar(select(func.count()).select_from(PlayerAlias)),
            "cannot_repair": db.scalar(select(func.count()).select_from(Replay).where(unrepairable(), not_(hidden_failure()))),
            "repairable": len(actions.repairable_failures(db)),
            "aggressive_repairable": len(actions.aggressive_failures(db)),
            "hidden_replays": db.scalar(select(func.count()).select_from(Replay).where(hidden_failure())),
            "challenge": {"start": start, "end": end, "launched": actions.achievements_launched(db),
                          "visibility": actions.achievements_visibility(db)},
            "mega_period": {"start": mega_start, "end": mega_end, "visibility": actions.mega_visibility(db)},  # none set = the prizes follow the challenge period
            "stat_groups": [{"key": g, "label": label, "hidden": g in hidden, "players": hidden_players[g]}
                            for g, label in actions.STAT_GROUPS.items()],
            "recent": [_log_row(r) for r in actions.command_log(db, 8)],
            "arena_status": tracker.status() if tracker else {"state": "off"},  # from memory: no request, no wait
        }


@router.get("/players")
def players(request: Request, q: str = Query("", max_length=100)):
    """Player tools: players matching a name or id, with their merges and whether their win-loss is hidden."""
    require_console(request, "players", fresh=False)
    q = q.strip()
    if not q:
        return []
    with request.app.state.sessionmaker() as db:
        hidden = set(actions.hidden_players(db, "win_loss"))
        rows = []
        for p in console.find_players(db, q, 20):
            alias = db.get(PlayerAlias, p.user_id)
            merged = db.scalars(select(PlayerAlias.alias_user_id).where(PlayerAlias.main_user_id == p.user_id)).all()
            rows.append({
                "user_id": p.user_id, "name": p.name, "games": console.games(db, p.id),
                "first_seen_at": p.first_seen_at, "last_seen_at": p.last_seen_at,
                "merged_into": {"user_id": alias.main_user_id, "name": console.name_of(db, alias.main_user_id)} if alias else None,
                "merged_ids": [{"user_id": u, "name": console.name_of(db, u)} for u in merged],
                "win_loss_hidden": (alias.main_user_id if alias else p.user_id) in hidden,
            })
        return rows


@router.get("/log")
def command_log(request: Request, q: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=500),
                before: int | None = Query(None, ge=1)):
    """Audit log: console commands, newest first (`before`: the id to continue from)."""
    require_console(request, "log", fresh=False)
    with request.app.state.sessionmaker() as db:
        return [_log_row(r) for r in actions.command_log(db, limit, q.strip(), before)]


@router.get("/achievements.csv")
def achievements_csv(request: Request):
    require_console(request, "achievements.csv")
    return Response(csv_bytes(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="EchoVR-Achievements.csv"'})


@router.get("/mega-prizes")
def mega_prize_winners(request: Request):
    """Who has reached each Mega Prize target inside the Mega Prize period (the prizes are given out by hand)."""
    require_console(request, "mega-prizes")
    with request.app.state.sessionmaker() as db:
        return mega_prizes.report(db)


@router.get("/mega-prizes.csv")
def mega_prize_winners_csv(request: Request):
    require_console(request, "mega-prizes.csv")
    with request.app.state.sessionmaker() as db:
        data = mega_prizes.report(db)
    return Response(mega_prizes.csv_bytes(data), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="EchoVR-Mega-Prize-Winners.csv"'})


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
    output = for_the_page(out.getvalue()).strip()
    try:  # the audit log must never make a command fail
        with request.app.state.sessionmaker() as db:
            actions.log_command(db, "website", user["name"], command, args.model_dump(exclude_defaults=True), ok, output,
                                who_id=user["id"])
    except Exception:
        log.exception("Could not write the console audit log")
    return {"ok": ok, "output": output}
