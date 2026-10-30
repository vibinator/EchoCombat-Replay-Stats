"""Everything that changes data. The website is read-only (user, 2026-10-30): these run from the admin console
(app/admin_console.py), on the database directly. Each function validates, writes and commits; AdminError carries
a message for the person. Replays they queue go to the front of the worker's queue (priority_replays) and are
picked up by a running server within seconds, otherwise on its next start."""

from datetime import date

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from . import aliases
from .config import Settings
from .db import utcnow
from .models import AppSetting, HiddenReplay, Player, PlayerAlias, PriorityReplay, RepairRequest, Replay

REPAIRABLE = ("corrupt", "incomplete", "internal", "crashed")  # not: unsupported (not Combat), unreadable (I/O)
WINDOW_KEYS = ("challenge_start", "challenge_end")
# Discord ids, comma-separated, per permission (D41, D42, D45; Permissions page, user 2026-10-30): "<permission>" =
# role ids, "<permission>_user" = people's user ids. preview = achievements before the launch, admin = the Admin
# tab, console = the Console and Permissions pages. ECHOVR_DISCORD_PREVIEW_ROLES (YAML) adds fixed console ids.
PERMISSIONS = ("admin", "console", "preview")
ROLE_KEYS = {"preview": "discord_preview_roles", "admin": "discord_admin_roles", "admin_user": "discord_admin_users",
             "preview_user": "discord_preview_users", "console": "discord_console_roles",
             "console_user": "discord_console_users"}
ROLE_LABELS = {"preview": "a preview role", "admin": "an admin role", "admin_user": "an admin user",
               "preview_user": "a preview user", "console": "a console role", "console_user": "a console user"}


class AdminError(Exception):
    pass


# --- queries shared with the read-only API --------------------------------------------------------

def hidden_failure():
    """Failed replays hidden by an admin (a hidden file that later imports fine shows again)."""
    return and_(Replay.status == "failed", Replay.source_path.in_(select(HiddenReplay.source_path)))


def unrepairable():
    """Failed, and repair cannot help: not a repairable error, or repair was already tried."""
    return and_(Replay.status == "failed", or_(
        Replay.error_code.is_(None), Replay.error_code.not_in(REPAIRABLE),
        Replay.source_path.in_(select(RepairRequest.source_path)),
    ))


# --- queue ---------------------------------------------------------------------------------------

def prioritise(db: Session, replay_ids) -> None:
    """Process these before the backlog (the worker reads priority_replays first). Caller commits."""
    for rid in set(replay_ids):
        db.merge(PriorityReplay(replay_id=rid))


def _replay(db: Session, replay_id: int) -> Replay:
    replay = db.get(Replay, replay_id)
    if replay is None:
        raise AdminError(f"Replay {replay_id} not found")
    if replay.status in ("queued", "processing"):
        raise AdminError(f"{replay.source_path} is already queued or processing")
    return replay


def reprocess(db: Session, replay_id: int) -> Replay:
    """Read the file again (e.g. after a fix in the app)."""
    replay = _replay(db, replay_id)
    replay.status = "queued"
    prioritise(db, [replay.id])
    db.commit()
    return replay


def _request_repair(db: Session, replay: Replay) -> None:
    db.merge(RepairRequest(source_path=replay.source_path, requested_at=utcnow()))
    replay.status = "queued"


def repair(db: Session, replay_id: int) -> Replay:
    """Re-process a failed replay in repair (salvage) mode (D36): recover every readable frame. Reads the
    original only; the share is never written to. The match is marked as repaired."""
    replay = _replay(db, replay_id)
    if replay.error_code not in REPAIRABLE:
        raise AdminError("Only damaged or incomplete replays can be repaired" if replay.error_code
                         else "This replay was processed successfully")
    _request_repair(db, replay)
    prioritise(db, [replay.id])
    db.commit()
    return replay


def repairable_failures(db: Session) -> list[Replay]:
    """Damaged / incomplete replays not tried in repair mode yet (and not hidden)."""
    return db.scalars(select(Replay).where(
        Replay.status == "failed", Replay.error_code.in_(REPAIRABLE), ~hidden_failure(),
        Replay.source_path.not_in(select(RepairRequest.source_path)),
    )).all()


def repair_all_failed(db: Session) -> list[int]:
    failed = repairable_failures(db)
    for replay in failed:
        _request_repair(db, replay)
    prioritise(db, [r.id for r in failed])
    db.commit()
    return [r.id for r in failed]


def reprocess_all(db: Session) -> int:
    """Queue every finished replay (done and failed) to be read again. Results already on the website stay until
    each replay is replaced; nothing is deleted first. Not prioritised: it is the whole archive."""
    n = db.execute(update(Replay).where(Replay.status.in_(("done", "failed"))).values(status="queued")).rowcount
    db.commit()
    return n


def scan(sessions: sessionmaker, settings: Settings):
    """Look for new / changed files in the share now (the server also does this every few minutes)."""
    from .scanner import ScanState, scan_once

    state = ScanState()
    scan_once(sessions, settings, state)
    return state


# --- hidden replays ------------------------------------------------------------------------------

def hide_unrepairable(db: Session) -> list[str]:
    paths = db.scalars(select(Replay.source_path).where(unrepairable(), ~hidden_failure())).all()
    now = utcnow()
    for path in paths:
        db.merge(HiddenReplay(source_path=path, hidden_at=now))
    db.commit()
    return list(paths)


def unhide(db: Session, paths: list[str] | None) -> int:
    """Show these hidden replays again; None = all."""
    query = delete(HiddenReplay)
    if paths is not None:
        missing = set(paths) - set(db.scalars(select(HiddenReplay.source_path).where(HiddenReplay.source_path.in_(paths))))
        if missing:
            raise AdminError(f"Not hidden: {', '.join(sorted(missing))} (use the path exactly as listed)")
        query = query.where(HiddenReplay.source_path.in_(paths))
    n = db.execute(query).rowcount
    db.commit()
    return n


# --- players -------------------------------------------------------------------------------------

def merge_players(db: Session, main: str, others: list[str]) -> list[int]:
    """Merge `others` into `main` (D34: same person, several player ids). Returns the replays re-queued."""
    others = [u for u in dict.fromkeys(others) if u and u != main]
    if not others:
        raise AdminError("Choose at least one other player")
    if db.scalar(select(Player).where(Player.user_id == main)) is None:
        raise AdminError(f"Player {main} not found")
    if (row := db.get(PlayerAlias, main)) is not None:
        raise AdminError(f"{main} is itself merged into {row.main_user_id}. Pick that player as the main one, "
                         "or undo that merge first.")
    unknown = set(others) - set(db.scalars(select(Player.user_id).where(Player.user_id.in_(others))))
    if unknown:
        raise AdminError(f"Player(s) not found: {', '.join(sorted(unknown))}")
    replay_ids = aliases.merge(db, main, others)
    prioritise(db, replay_ids)
    db.commit()
    return replay_ids


def unmerge_player(db: Session, alias_user_id: str) -> list[int]:
    """Undo a merge: the main player's replays are re-processed to split the records again."""
    if db.get(PlayerAlias, alias_user_id) is None:
        raise AdminError(f"No merge for {alias_user_id}")
    replay_ids = aliases.unmerge(db, alias_user_id)
    prioritise(db, replay_ids)
    db.commit()
    return replay_ids


# --- challenge period ----------------------------------------------------------------------------

def challenge_window(db: Session) -> tuple[str | None, str | None]:
    values = dict(db.execute(select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_(WINDOW_KEYS))).all())
    return values.get("challenge_start"), values.get("challenge_end")


def discord_roles(db: Session, kind: str) -> list[str]:
    """Discord role ids set in the admin console for `kind` ("preview" / "admin")."""
    value = db.scalar(select(AppSetting.value).where(AppSetting.key == ROLE_KEYS[kind]))
    return [r for r in (value or "").split(",") if r]


def _role_id(value: str) -> str:
    value = value.strip()
    if not (value.isdigit() and 17 <= len(value) <= 20):
        raise AdminError(f"'{value}' is not a Discord id (17-20 digits: right-click > Copy Role ID / Copy User ID)")
    return value


def add_discord_role(db: Session, kind: str, role_id: str) -> list[str]:
    roles = discord_roles(db, kind)
    role_id = _role_id(role_id)
    if role_id not in roles:
        roles.append(role_id)
    return _save_discord_roles(db, kind, roles)


def remove_discord_role(db: Session, kind: str, role_id: str) -> list[str]:
    roles = discord_roles(db, kind)
    if role_id.strip() not in roles:
        raise AdminError(f"{role_id} is not {ROLE_LABELS[kind]}")
    return _save_discord_roles(db, kind, [r for r in roles if r != role_id.strip()])


def _save_discord_roles(db: Session, kind: str, roles: list[str]) -> list[str]:
    db.merge(AppSetting(key=ROLE_KEYS[kind], value=",".join(roles) or None, updated_at=utcnow()))
    db.commit()
    return roles


def achievements_launched(db: Session) -> bool:
    """Achievements and challenges are public from the challenge start date on (user, 2026-10-30). No start date,
    or one still to come: the website shows "Coming soon" and the API returns none of their data."""
    start = challenge_window(db)[0]
    return bool(start) and start <= date.today().isoformat()


def set_challenge_window(db: Session, start: str | None, end: str | None) -> tuple[str | None, str | None]:
    """The Flamingo Challenge period (D33): only matches inside it count. start = launch date (achievements are
    "Coming soon" on the website until then, see achievements_launched); end None = open-ended."""
    for value in (start, end):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise AdminError(f"'{value}' is not a date (YYYY-MM-DD)") from None
    if start and end and start > end:
        raise AdminError("Start date must be on or before the end date")
    for key, value in zip(WINDOW_KEYS, (start or None, end or None)):
        db.merge(AppSetting(key=key, value=value, updated_at=utcnow()))
    db.commit()
    return start or None, end or None
