"""Admin console: the only place data is changed (the website is read-only). Player merges, the challenge
period, re-processing / repairing replays, scanning the share and hiding replays that cannot be repaired.

Works directly on the database, so it needs no password and works whether or not the server is running.
Replays it queues go to the front of the queue and are picked up by a running server within a few seconds,
otherwise on its next start. The actions themselves live in backend/admin_actions.py. A merge is saved as a
rule and the affected replays are re-processed from the original files, so it can always be undone.

    admin.bat                          interactive menu
    admin.bat find <name or id>
    admin.bat merge <main> <other> [<other> ...] [--yes]
    admin.bat merges
    admin.bat unmerge <merged id> [--yes]
    admin.bat challenge [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--clear]
    admin.bat preview-roles [--server] [--add <role id>] [--remove <role id>]   Discord roles: achievements early
    admin.bat admin-roles [--server] [--add <role id>] [--remove <role id>]     Discord roles: admins (Status page)
    admin.bat admin-users [--add <user id>] [--remove <user id>]   Discord users that are admins (no role needed)
    admin.bat discord-check <discord user id>   what the bot sees for one person: in the server, roles, access
    admin.bat status
    admin.bat repair-failed [--yes]
    admin.bat cannot-repair [--hide] [--yes]   failed replays repair cannot fix; --hide hides them on the website
    admin.bat hidden [--unhide <path> | --unhide-all] [--yes]
    admin.bat reprocess <replay id or path>
    admin.bat repair <replay id or path>
    admin.bat scan
    admin.bat reprocess-all [--yes]        rescan the folder, then read every replay again
"""

import argparse
import socket
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, event, func, not_, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from backend import admin_actions as actions  # noqa: E402
from backend import aliases, auth  # noqa: E402
from backend.admin_actions import REPAIRABLE, AdminError, hidden_failure, unrepairable  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.version import APP_VERSION  # noqa: E402
from backend.models import HiddenReplay, Match, MatchPlayer, Player, PlayerAlias, Replay  # noqa: E402

REASONS = {  # error codes -> why repair cannot help
    "unsupported": "not an Echo Combat replay", "unreadable": "file could not be read (network / locked)",
}
SERVER = ("127.0.0.1", 8000)


ConsoleError = AdminError  # one error type: a message for the person


# --- database ---------------------------------------------------------------------------------

def open_sessions(settings: Settings) -> sessionmaker:
    """Plain connection: never creates or rebuilds tables (that is the server's job)."""
    if not settings.db_path.exists():
        raise ConsoleError(f"No database at {settings.db_path}. Start the server (run.bat) once first.")
    engine = create_engine(f"sqlite:///{settings.db_path}", connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return sessionmaker(engine, expire_on_commit=False)


def server_running() -> bool:
    try:
        with socket.create_connection(SERVER, timeout=0.3):
            return True
    except OSError:
        return False


def when_applied() -> str:
    return ("The running server picks them up within a few seconds." if server_running()
            else "The server is not running: they are processed on its next start (run.bat).")


# --- players ----------------------------------------------------------------------------------

def games(db: Session, player_id: int) -> int:
    return db.scalar(select(func.count()).select_from(MatchPlayer).where(MatchPlayer.player_id == player_id))


def find_players(db: Session, term: str, limit: int = 15) -> list[Player]:
    """Exact user id first, then names containing `term` (most recently seen first)."""
    exact = db.scalar(select(Player).where(Player.user_id == term))
    named = db.scalars(select(Player).where(Player.name.ilike(f"%{term}%"), Player.user_id != term)
                       .order_by(Player.last_seen_at.desc()).limit(limit)).all()
    return ([exact] if exact else []) + list(named)


def describe(db: Session, p: Player) -> str:
    alias = db.get(PlayerAlias, p.user_id)
    note = f"  [merged into {name_of(db, alias.main_user_id)}]" if alias else ""
    return f"{p.name:<24} id {p.user_id:<20} {games(db, p.id):>5} games  last seen {p.last_seen_at[:10]}{note}"


def name_of(db: Session, user_id: str) -> str:
    return db.scalar(select(Player.name).where(Player.user_id == user_id)) or user_id


def resolve(db: Session, term: str, interactive: bool) -> Player:
    """One player from a user id or a name. Ambiguous names: pick from a list (interactive) or fail."""
    found = find_players(db, term)
    if not found:
        raise ConsoleError(f"No player matches '{term}'")
    if found[0].user_id == term or len(found) == 1:
        return found[0]
    if not interactive:
        lines = "\n  ".join(describe(db, p) for p in found)
        raise ConsoleError(f"'{term}' matches several players; use the id:\n  {lines}")
    print(f"Several players match '{term}':")
    for i, p in enumerate(found, 1):
        print(f"  {i:>2}. {describe(db, p)}")
    while True:
        choice = input("Number (Enter to cancel): ").strip()
        if not choice:
            raise ConsoleError("Cancelled")
        if choice.isdigit() and 1 <= int(choice) <= len(found):
            return found[int(choice) - 1]


def confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        raise ConsoleError("Not running in a terminal: add --yes to confirm")
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


# --- commands ---------------------------------------------------------------------------------

def cmd_find(sessions, term: str) -> None:
    with sessions() as db:
        found = find_players(db, term)
        if not found:
            print(f"No player matches '{term}'.")
        for p in found:
            print(describe(db, p))


def cmd_merge(sessions, main_term: str, other_terms: list[str], yes: bool, interactive: bool) -> None:
    with sessions() as db:
        main = resolve(db, main_term, interactive)
        if db.get(PlayerAlias, main.user_id):
            raise ConsoleError(f"{main.name} is itself merged into {name_of(db, db.get(PlayerAlias, main.user_id).main_user_id)}. "
                               "Pick that player as the main one, or undo that merge first.")
        others = []
        for term in other_terms:
            p = resolve(db, term, interactive)
            if p.user_id == main.user_id:
                raise ConsoleError(f"{p.name} is the main player; choose a different record to merge")
            if p.user_id not in {o.user_id for o in others}:
                others.append(p)
        if not others:
            raise ConsoleError("Choose at least one other player")
        print(f"\nKeep:   {describe(db, main)}")
        for o in others:
            print(f"Merge:  {describe(db, o)}")
            moved = db.scalars(select(PlayerAlias.alias_user_id).where(PlayerAlias.main_user_id == o.user_id)).all()
            if moved:
                print(f"        (its own merged records follow it: {', '.join(moved)})")
        affected = {u for o in others for u in aliases.ids_of(db, o.user_id)}
        print(f"{len(aliases._replays_of(db, affected))} replays will be updated.")
        if not confirm(f"Merge {len(others)} record(s) into {main.name}?", yes):
            print("Nothing changed.")
            return
        result = actions.merge_players(db, main.user_id, [o.user_id for o in others])
    print(f"Merged. {len(result.moved)} replays updated now.", end=" ")
    if result.requeued:  # several of the player's ids in one match: read again from the file
        print(f"{len(result.requeued)} queued for re-processing. {when_applied()}")
    else:
        print()


def list_merges(db: Session) -> list[PlayerAlias]:
    return db.scalars(select(PlayerAlias).order_by(PlayerAlias.created_at.desc())).all()


def cmd_merges(sessions) -> list[PlayerAlias]:
    with sessions() as db:
        rows = list_merges(db)
        if not rows:
            print("No merges yet.")
        for i, r in enumerate(rows, 1):
            print(f"  {i:>2}. {name_of(db, r.alias_user_id):<24} id {r.alias_user_id:<20} -> "
                  f"{name_of(db, r.main_user_id):<24} id {r.main_user_id:<20} {r.created_at[:16].replace('T', ' ')} UTC")
    return rows


def cmd_unmerge(sessions, alias_term: str, yes: bool) -> None:
    with sessions() as db:
        row = db.get(PlayerAlias, alias_term)
        if row is None:  # allow a name too
            matches = [r for r in list_merges(db) if alias_term.lower() in name_of(db, r.alias_user_id).lower()]
            if len(matches) != 1:
                raise ConsoleError(f"No single merge matches '{alias_term}'. Use the merged id from 'merges'.")
            row = matches[0]
        print(f"Undo: {name_of(db, row.alias_user_id)} (id {row.alias_user_id}) becomes separate from "
              f"{name_of(db, row.main_user_id)} again.")
        if not confirm("Undo this merge?", yes):
            print("Nothing changed.")
            return
        replay_ids = actions.unmerge_player(db, row.alias_user_id)
    print(f"Undone. {len(replay_ids)} replays queued for re-processing. {when_applied()}")


def cmd_challenge(sessions, start: str | None, end: str | None, clear: bool) -> None:
    """start / end: None = keep, "" = no limit."""
    with sessions() as db:
        current = actions.challenge_window(db)
        if clear or start is not None or end is not None:
            new = (None, None) if clear else (current[0] if start is None else start, current[1] if end is None else end)
            current = actions.set_challenge_window(db, *new)
            print("Saved. The website uses the new period straight away.")
    print(f"Flamingo Challenge period: {current[0] or 'no start date'} -> {current[1] or 'open-ended'}")
    with sessions() as db:
        launched = actions.achievements_launched(db)
    if launched:
        print(f"Website: achievements and challenges are live, counting matches from {current[0]}.")
    elif current[0]:
        print(f"Website: \"Coming soon\" until {current[0]}; from that day they go live and count matches from it.")
    else:
        print("Website: \"Coming soon\". Set a start date to launch achievements and challenges.")


def _server_roles(settings: Settings) -> list[dict] | None:
    """The Discord server's roles via the bot, or None when the bot token is not set / Discord cannot be asked."""
    if not settings.discord_bot_token:
        return None
    try:
        return auth.server_roles(settings)
    except Exception:  # network, bad token, bot not in the server: the role ids still work without names
        return None


ROLE_KINDS = {  # kind -> (heading, what the members get)
    "preview": ("Preview roles", "see achievements and challenges before the launch date"),
    "admin": ("Admin roles", "get the Status page and the preview"),
}


def cmd_discord_roles(sessions, settings: Settings, kind: str, add: str | None = None, remove: str | None = None,
                      show_server: bool = False) -> list[dict]:
    """Discord roles for `kind` ("preview" D41, "admin" D42). Returns the server's roles (numbered as printed) when
    show_server and the bot could list them."""
    heading, gets = ROLE_KINDS[kind]
    if add:
        server = _server_roles(settings)
        if server is not None and add.strip() not in {r["id"] for r in server}:
            raise ConsoleError(f"{add.strip()} is not a role in the Discord server. A person's id (Copy User ID) goes "
                               "in admin users instead: option 17 / admin.bat admin-users --add <user id>.")
    with sessions() as db:
        if add:
            actions.add_discord_role(db, kind, add)
            print(f"Added. Members with role {add} {gets} within 5 minutes.")
        if remove:
            actions.remove_discord_role(db, kind, remove)
            print(f"Removed. Members with only role {remove} lose it within 5 minutes.")
        roles = actions.discord_roles(db, kind)
    server = _server_roles(settings)
    names = {r["id"]: r["name"] for r in server or []}
    from_env = [r for r in settings.discord_preview_roles if r not in roles] if kind == "preview" else []
    print(f"{heading} (members {gets}):")
    for r in roles:
        print(f"  {names.get(r, '?'):<28} {r}")
    for r in from_env:
        print(f"  {names.get(r, '?'):<28} {r}   (from ECHOVR_DISCORD_PREVIEW_ROLES, change it there)")
    if not roles and not from_env:
        print("  none yet")
    if not auth.enabled(settings):
        print("Note: Discord login is off on this computer / container: the client secret or bot token is not set "
              "(Setup.MD, Discord login).")
    if not show_server:
        return []
    if server is None:
        print("Server roles could not be listed (bot token not set here, or Discord / the bot not reachable). "
              "Copy the role id in Discord instead: right-click the role > Copy Role ID.")
        return []
    print(f"All roles in the Discord server, to pick from ([{kind}] = already set):")
    for i, r in enumerate(server, 1):
        mark = f"  [{kind}]" if r["id"] in roles or r["id"] in from_env else ""
        print(f"  {i:>3}  {r['name']:<28} {r['id']}{mark}")
    return server


def _discord_user(settings: Settings, user_id: str) -> str:
    return auth.user_name(settings, user_id)


def cmd_admin_users(sessions, settings: Settings, add: str | None = None, remove: str | None = None) -> list[str]:
    """Discord users that are admins themselves (Status page + preview), whatever their roles."""
    with sessions() as db:
        if add:
            server = _server_roles(settings)
            if server is not None and add.strip() in {r["id"] for r in server}:
                raise ConsoleError(f"{add.strip()} is a role, not a person: use admin roles (option 15) for it.")
            actions.add_discord_role(db, "admin_user", add)
            print(f"Added. {_discord_user(settings, add)} is an admin (Status page) at their next page load.")
        if remove:
            actions.remove_discord_role(db, "admin_user", remove)
            print(f"Removed. {remove.strip()} is no longer an admin at their next page load (unless an admin role gives it).")
        users = actions.discord_roles(db, "admin_user")
    print("Admin users (Status page and preview, no role needed):")
    for u in users:
        print(f"  {_discord_user(settings, u):<28} {u}")
    if not users:
        print("  none yet")
    return users


def cmd_discord_check(sessions, settings: Settings, user_id: str) -> dict:
    """Asks Discord (with the bot token) what the website sees for one person, step by step."""
    user_id = user_id.strip()
    if not auth.is_discord_id(user_id):  # it goes into a Discord API path called with the bot token
        raise ConsoleError(f"'{user_id}' is not a Discord user id (17-20 digits: right-click the person > Copy User ID)")
    if not settings.discord_bot_token:
        raise ConsoleError("The bot token is not set here (ECHOVR_DISCORD_BOT_TOKEN), so Discord cannot be asked. "
                           "On the NAS run this in the container; on Windows put it in settings.local.bat.")
    try:
        r = auth._bot_get(settings, f"/guilds/{settings.discord_guild_id}/members/{user_id}")
    except Exception as e:
        raise ConsoleError(f"Discord could not be reached: {e}") from None
    if r.status_code == 401:
        raise ConsoleError("Discord refused the bot token (401): it is wrong or was reset. Copy it again from the "
                           "Developer Portal > Bot, put it in ECHOVR_DISCORD_BOT_TOKEN and restart / Recreate.")
    if r.status_code == 403:
        raise ConsoleError(f"The bot is not in server {settings.discord_guild_id} (403): invite it to the server.")
    if r.status_code not in (200, 404):  # 404: not in the server (or not a Discord user id)
        raise ConsoleError(f"Discord answered {r.status_code}: {r.text[:200]}")
    member = r.json() if r.status_code == 200 else None
    roles = set(member.get("roles", [])) if member else set()
    with sessions() as db:
        is_admin, has_console, has_preview = (auth.allowed(settings, db, user_id, kind, lambda: frozenset(roles))
                                              for kind in ("admin", "console", "preview"))
    user = (member or {}).get("user", {})
    name = user.get("global_name") or user.get("username") or _discord_user(settings, user_id)
    print(f"{name} ({user_id})" + ("" if member else ": not in the Discord server"))
    for label, ok in (("Admin", is_admin), ("Preview", has_preview), ("Console page", has_console)):
        print(f"  {label:<14}{'yes' if ok else 'no'}")
    if not auth.enabled(settings):
        print("Note: the Discord login is off here (client secret or bot token missing).")
    print("A change shows on the website within 5 minutes, or at once after logging out and in again.")
    return {"member": bool(member), "admin": is_admin, "preview": has_preview, "console": has_console}


RATE_WINDOW_MIN = 10


def cmd_status(sessions) -> None:
    """Server, import progress (the website has no Import page), failures, players."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=RATE_WINDOW_MIN)).isoformat(timespec="seconds")
    with sessions() as db:
        counts = dict(db.execute(select(Replay.status, func.count()).group_by(Replay.status)).all())
        redo = db.scalar(select(func.count()).select_from(Replay)
                         .where(Replay.status == "queued", Replay.parser_version.is_not(None)))
        recent = db.scalar(select(func.count()).select_from(Replay).where(Replay.processed_at >= since))
        last = db.scalar(select(func.max(Replay.processed_at)))
        matches = db.scalar(select(func.count()).select_from(Match))
        failed = dict(db.execute(select(Replay.error_code, func.count()).where(Replay.status == "failed")
                                 .group_by(Replay.error_code)).all())
        hidden = db.scalar(select(func.count()).select_from(Replay).where(hidden_failure()))
        stuck = db.scalar(select(func.count()).select_from(Replay).where(unrepairable(), not_(hidden_failure())))
        merges = db.scalar(select(func.count()).select_from(PlayerAlias))
        players = db.scalar(select(func.count()).select_from(Player))
    print(f"Server: {'running' if server_running() else 'not running'} (http://{SERVER[0]}:{SERVER[1]})")
    print("Replays: " + ", ".join(f"{k} {counts.get(k, 0)}" for k in ("done", "queued", "processing", "failed")))
    total = sum(counts.values())
    waiting = counts.get("queued", 0) + counts.get("processing", 0)
    if total:
        finished = counts.get("done", 0) + counts.get("failed", 0)
        print(f"Import: {finished / total:.1%} finished ({finished:,} / {total:,}), {matches:,} matches"
              + (f", {redo:,} being redone after an update" if redo else ""))
    per_min = recent / RATE_WINDOW_MIN
    if waiting:
        eta = f", about {waiting / per_min / 60:.1f} h left" if per_min else ""
        print(f"Speed: {per_min:.1f} replays/min over the last {RATE_WINDOW_MIN} min{eta}")
    if last:
        print(f"Last replay finished: {last.replace('T', ' ')[:19]} UTC")
    if failed:
        print("Failed by reason: " + ", ".join(f"{k or 'unknown'} {n}" for k, n in sorted(failed.items(), key=lambda kv: -kv[1])))
    if stuck or hidden:
        print(f"Cannot be repaired: {stuck} shown on the website, {hidden} hidden")
    print(f"Players: {players}  ·  merges: {merges}")


def cmd_repair_failed(sessions, yes: bool) -> None:
    with sessions() as db:
        failed = actions.repairable_failures(db)
        if not failed:
            print("No damaged or incomplete replays left to try (each one gets one repair attempt here).")
            stuck = db.scalar(select(func.count()).select_from(Replay).where(unrepairable(), not_(hidden_failure())))
            if stuck:
                print(f"{stuck} failed replays cannot be repaired: 'cannot-repair' lists them and can hide them.")
            return
        if not confirm(f"Re-process {len(failed)} damaged / incomplete replays in repair (salvage) mode?", yes):
            print("Nothing changed.")
            return
        actions.repair_all_failed(db)
    print(f"{len(failed)} replays queued for repair. {when_applied()}")
    print("Any that still fail afterwards show up under 'cannot-repair', where they can be hidden.")


def describe_replay(r: Replay) -> str:
    if r.error_code in REPAIRABLE:
        why = f"{r.error_code}, still failing after repair"
    else:
        why = REASONS.get(r.error_code, r.error_code or "unknown error")
    return f"{r.source_path:<60} {why}"


def cmd_cannot_repair(sessions, hide: bool, yes: bool) -> list[Replay]:
    with sessions() as db:
        rows = db.scalars(select(Replay).where(unrepairable(), not_(hidden_failure()))
                          .order_by(Replay.source_mtime.desc())).all()
        if not rows:
            print("No failed replays that cannot be repaired (hidden ones excluded).")
            return []
        if not hide:
            print(f"{len(rows)} failed replays cannot be repaired:")
            for r in rows:
                print(f"  {describe_replay(r)}")
            return rows
        if not confirm(f"Hide these {len(rows)} replays (left out of the failed lists and counts)?", yes):
            print("Nothing changed.")
            return rows
        actions.hide_unrepairable(db)
    print(f"Hidden {len(rows)}. Nothing is deleted: 'hidden' lists them and can show them again. "
          "A hidden file that is replaced on the share and then imports fine shows up normally.")
    return rows


def cmd_hidden(sessions, unhide: str | None, unhide_all: bool, yes: bool) -> list[str]:
    """Lists hidden replays (returns their paths), or shows one / all of them on the website again."""
    with sessions() as db:
        rows = db.scalars(select(HiddenReplay).order_by(HiddenReplay.source_path)).all()
        if unhide_all or unhide:
            if not rows:
                print("Nothing is hidden.")
                return []
            count = len(rows) if unhide_all else 1
            if not confirm(f"Show {count} replay(s) on the website again?", yes):
                print("Nothing changed.")
                return []
            n = actions.unhide(db, None if unhide_all else [unhide])
            print(f"{n} replay(s) visible again.")
            return []
        if not rows:
            print("Nothing is hidden.")
        replays = {r.source_path: r for r in db.scalars(
            select(Replay).where(Replay.source_path.in_([h.source_path for h in rows])))}
        for i, h in enumerate(rows, 1):
            r = replays.get(h.source_path)
            if r is not None and r.status == "failed":
                state = describe_replay(r)
            else:
                state = f"{h.source_path:<60} " + (f"now {r.status} (shown)" if r else "file no longer in the share")
            print(f"  {i:>3}. {state}   hidden {h.hidden_at[:10]}")
        return [h.source_path for h in rows]


def find_replay(db: Session, term: str) -> Replay:
    """A replay by id, by exact path, or by a unique part of its path."""
    if term.isdigit() and (replay := db.get(Replay, int(term))):
        return replay
    term = term.replace("\\", "/")
    exact = db.scalar(select(Replay).where(Replay.source_path == term))
    if exact:
        return exact
    found = db.scalars(select(Replay).where(Replay.source_path.ilike(f"%{term}%")).limit(6)).all()
    if len(found) == 1:
        return found[0]
    if not found:
        raise ConsoleError(f"No replay matches '{term}'")
    raise ConsoleError(f"'{term}' matches several replays:\n  " + "\n  ".join(r.source_path for r in found[:5]))


def cmd_reprocess(sessions, term: str) -> None:
    with sessions() as db:
        replay = actions.reprocess(db, find_replay(db, term).id)
    print(f"Queued {replay.source_path}. {when_applied()}")


def cmd_repair(sessions, term: str) -> None:
    with sessions() as db:
        replay = actions.repair(db, find_replay(db, term).id)
    print(f"Queued {replay.source_path} for repair (salvage mode). {when_applied()}")


def cmd_scan(sessions, settings: Settings) -> None:
    print(f"Scanning {settings.source_dir} ...")
    state = actions.scan(sessions, settings)
    if state.error:
        raise ConsoleError(f"Scan failed: {state.error}")
    print(f"{state.files} files, {state.added} new, {state.changed} changed, {state.settling} still being written. "
          + (when_applied() if state.added or state.changed else ""))


REPLAYS_PER_MIN = 160  # full archive (~29k) in about 3 hours with 8 workers (docs/Setup.MD)


def cmd_reprocess_all(sessions, settings: Settings, yes: bool) -> None:
    with sessions() as db:
        counts = dict(db.execute(select(Replay.status, func.count()).group_by(Replay.status)).all())
    finished = counts.get("done", 0) + counts.get("failed", 0)
    hours = finished / REPLAYS_PER_MIN / 60
    print(f"This rescans {settings.source_dir} for new / changed files, then reads all {finished:,} replays again "
          f"(done and failed): roughly {hours:.1f} hours. Current results stay on the website until each replay is "
          "replaced; merges, hidden replays and the challenge period are kept.")
    if not confirm("Rescan and re-process every replay?", yes):
        print("Nothing changed.")
        return
    cmd_scan(sessions, settings)
    with sessions() as db:
        n = actions.reprocess_all(db)
    print(f"{n:,} replays queued for re-processing. {when_applied()} Progress: 'admin.bat status'.")


# --- interactive menu -------------------------------------------------------------------------

MENU = f"""
EchoVR Replay Stats - admin console ({APP_VERSION})
  1  Find a player
  2  Merge player records
  3  List merges
  4  Undo a merge
  5  Achievements launch / Flamingo Challenge period
  6  Status and import progress
  7  Repair failed replays
  8  Replays that cannot be repaired (hide them)
  9  Hidden replays (show again)
  10 Re-process a replay
  11 Repair a replay
  12 Scan the replay folder now
  13 Rescan and re-process every replay
  14 Discord preview roles (see achievements before the launch)
  15 Discord admin roles (Status page)
  16 Check a Discord member's access (Admin, Preview, Console)
  17 Discord admin users (admins by user id)
  q  Quit"""


def ask(prompt: str) -> str:
    return input(prompt).strip()


def interactive(sessions, settings: Settings) -> None:
    cmd_status(sessions)
    while True:
        print(MENU)
        choice = ask("> ").lower()
        try:
            if choice in ("q", "quit", "exit", ""):
                return
            if choice == "1":
                term = ask("Name or id: ")
                if term:
                    cmd_find(sessions, term)
            elif choice == "2":
                print("A merge is for one person who appears under several player ids.")
                main = ask("Player to KEEP (name or id): ")
                if not main:
                    continue
                others = []
                while True:
                    other = ask(f"Record to merge into it{' (Enter when done)' if others else ''}: ")
                    if not other:
                        break
                    others.append(other)
                if others:
                    cmd_merge(sessions, main, others, yes=False, interactive=True)
            elif choice == "3":
                cmd_merges(sessions)
            elif choice == "4":
                rows = cmd_merges(sessions)
                if rows:
                    pick = ask("Number or merged id to undo (Enter to cancel): ")
                    if pick:
                        alias = rows[int(pick) - 1].alias_user_id if pick.isdigit() and 1 <= int(pick) <= len(rows) else pick
                        cmd_unmerge(sessions, alias, yes=False)
            elif choice == "5":
                cmd_challenge(sessions, None, None, False)
                print("New dates: YYYY-MM-DD, '-' to clear, Enter to keep. Start = launch date: achievements and")
                print("challenges are \"Coming soon\" on the website until then and only count matches from it.")
                start, end = ask("Start: "), ask("End: ")
                if start or end:
                    cmd_challenge(sessions, None if not start else ("" if start == "-" else start),
                                  None if not end else ("" if end == "-" else end), False)
            elif choice == "6":
                cmd_status(sessions)
            elif choice == "7":
                cmd_repair_failed(sessions, yes=False)
            elif choice == "8":
                if cmd_cannot_repair(sessions, hide=False, yes=False):
                    cmd_cannot_repair(sessions, hide=True, yes=False)
            elif choice == "9":
                paths = cmd_hidden(sessions, None, False, False)
                if paths:
                    pick = ask("Number to show again, 'all', or Enter to go back: ").lower()
                    if pick == "all":
                        cmd_hidden(sessions, None, True, False)
                    elif pick.isdigit() and 1 <= int(pick) <= len(paths):
                        cmd_hidden(sessions, paths[int(pick) - 1], False, False)
            elif choice in ("10", "11"):
                term = ask("Replay id or file path: ")
                if term:
                    (cmd_reprocess if choice == "10" else cmd_repair)(sessions, term)
            elif choice == "12":
                cmd_scan(sessions, settings)
            elif choice == "13":
                cmd_reprocess_all(sessions, settings, yes=False)
            elif choice in ("14", "15"):
                kind = "preview" if choice == "14" else "admin"
                server = cmd_discord_roles(sessions, settings, kind, show_server=True)
                pick = ask("Add: number or role id. Remove: '-' + number or role id. Enter to go back: ")
                if pick:
                    remove = pick.startswith("-")
                    value = pick.lstrip("-").strip()
                    if value.isdigit() and 1 <= int(value) <= len(server):
                        value = server[int(value) - 1]["id"]
                    if remove:
                        cmd_discord_roles(sessions, settings, kind, remove=value)
                    else:
                        cmd_discord_roles(sessions, settings, kind, add=value)
            elif choice == "16":
                uid = ask("Discord user id (right-click the person > Copy User ID): ")
                if uid:
                    cmd_discord_check(sessions, settings, uid)
            elif choice == "17":
                cmd_admin_users(sessions, settings)
                pick = ask("Add: user id. Remove: '-' + user id. Enter to go back: ")
                if pick.startswith("-"):
                    cmd_admin_users(sessions, settings, remove=pick[1:])
                elif pick:
                    cmd_admin_users(sessions, settings, add=pick)
            else:
                print("Choose 1-17 or q.")
        except ConsoleError as e:
            print(f"! {e}")


# --- entry point ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="admin.bat", description=f"EchoVR Replay Stats admin console ({APP_VERSION})")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("find", help="find players by name or id").add_argument("term")
    p = sub.add_parser("merge", help="merge duplicate player records into one")
    p.add_argument("main", help="player to keep (name or id)")
    p.add_argument("others", nargs="+", help="records to merge into it")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sub.add_parser("merges", help="list merges")
    p = sub.add_parser("unmerge", help="undo a merge")
    p.add_argument("alias", help="the merged id (see 'merges')")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("challenge", help="show or set the Flamingo Challenge period")
    p.add_argument("--start", help="YYYY-MM-DD, or '' for no limit")
    p.add_argument("--end", help="YYYY-MM-DD, or '' for no limit")
    p.add_argument("--clear", action="store_true", help="remove both dates")
    for kind, help_ in (("preview", "Discord roles that see achievements before the launch date"),
                        ("admin", "Discord roles that are admins (Status page)")):
        p = sub.add_parser(f"{kind}-roles", help=help_)
        p.add_argument("--add", metavar="ROLE_ID", help="add this role")
        p.add_argument("--remove", metavar="ROLE_ID", help="remove this role")
        p.add_argument("--server", action="store_true", help="also list every role in the Discord server (needs the bot token)")
    sub.add_parser("discord-check", help="what the bot sees for one Discord member").add_argument("user_id")
    p = sub.add_parser("admin-users", help="Discord users that are admins (no role needed)")
    p.add_argument("--add", metavar="USER_ID", help="make this person an admin")
    p.add_argument("--remove", metavar="USER_ID", help="remove this person")
    sub.add_parser("status", help="import progress, replay and player counts")
    p = sub.add_parser("repair-failed", help="re-process damaged / incomplete replays in repair mode")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("cannot-repair", help="list failed replays that repair cannot fix")
    p.add_argument("--hide", action="store_true", help="hide them on the website")
    p.add_argument("--yes", action="store_true")
    p = sub.add_parser("hidden", help="list hidden replays")
    p.add_argument("--unhide", metavar="PATH", help="show this replay again")
    p.add_argument("--unhide-all", action="store_true", help="show every hidden replay again")
    p.add_argument("--yes", action="store_true")
    sub.add_parser("reprocess", help="read one replay again").add_argument("replay", help="replay id or file path")
    sub.add_parser("repair", help="re-process one damaged replay in repair mode").add_argument("replay", help="replay id or file path")
    sub.add_parser("scan", help="look for new / changed files in the replay folder now")
    p = sub.add_parser("reprocess-all", help="rescan the folder, then read every replay again (hours)")
    p.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
        sessions = open_sessions(settings)
        match args.command:
            case None:
                interactive(sessions, settings)
            case "find":
                cmd_find(sessions, args.term)
            case "merge":
                cmd_merge(sessions, args.main, args.others, args.yes, interactive=sys.stdin.isatty())
            case "merges":
                cmd_merges(sessions)
            case "unmerge":
                cmd_unmerge(sessions, args.alias, args.yes)
            case "challenge":
                cmd_challenge(sessions, args.start, args.end, args.clear)
            case "preview-roles" | "admin-roles":
                cmd_discord_roles(sessions, settings, args.command.removesuffix("-roles"), args.add, args.remove, args.server)
            case "admin-users":
                cmd_admin_users(sessions, settings, args.add, args.remove)
            case "discord-check":
                cmd_discord_check(sessions, settings, args.user_id)
            case "status":
                cmd_status(sessions)
            case "repair-failed":
                cmd_repair_failed(sessions, args.yes)
            case "cannot-repair":
                cmd_cannot_repair(sessions, args.hide, args.yes)
            case "hidden":
                cmd_hidden(sessions, args.unhide, args.unhide_all, args.yes)
            case "reprocess":
                cmd_reprocess(sessions, args.replay)
            case "repair":
                cmd_repair(sessions, args.replay)
            case "scan":
                cmd_scan(sessions, settings)
            case "reprocess-all":
                cmd_reprocess_all(sessions, settings, args.yes)
    except ConsoleError as e:
        print(f"! {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
