"""Open Cloud endpoints (cloud.py): Discord login + the Cloud view / Cloud edit permission (Permissions page).
Changes are POSTs with the X-EchoVR header (middleware.py WRITES); the download link is opened by the browser itself
and is exempt from that header (guard.py), the session cookie (SameSite=Lax) still decides who may have the file.

Audit log (user, 2026-11-10): every upload, download, new folder, rename and delete goes into cloud_log with who did
it, and so does every refusal of a logged-in person (no permission, no space, a bad name). Anonymous refusals are not
logged: there is nobody to name. Console users read it at /api/cloud/log (Console > Audit log > Cloud audit log)."""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import antivirus, auth, cloud, cloud_acl, guard
from ..cloud import CloudError
from ..errors import ApiError
from .permissions import _server_roles

router = APIRouter(prefix="/api/cloud", tags=["cloud"])
log = logging.getLogger("uvicorn.error")
WRITE_BLOCK = 1024 * 1024  # upload data is written in 1 MB blocks (one disk write and thread hop each, not one per 64 KB)


class BigBlockFileResponse(FileResponse):
    chunk_size = 1024 * 1024  # downloads read and sent in 1 MB blocks instead of Starlette's 64 KB: 16x fewer reads


def _audit(request: Request, user: dict, action: str, path: str, ok: bool = True, detail: str | None = None,
           size: int | None = None) -> None:
    cloud.log(request.app.state.sessionmaker, user, action, path, ok, detail, size, guard.client_ip(request))
    log.warning("Cloud: %s (%s) %s %s%s%s", user["name"], user["id"], action if ok else f"{action} refused", path or "/",
                f" -> {detail}" if detail else "", f" ({size} bytes)" if size is not None else "")


def _enter(request: Request, action: str, path: str, fresh: bool = False) -> tuple[dict, cloud_acl.Access]:
    """The logged-in person and what they may do (cloud_acl.py). Refused when nothing in the cloud is open to them;
    what they may do with `path` itself is the endpoint's own check (_deny)."""
    user = auth.viewer(request)
    if not user:
        raise ApiError(401, "login_required", "Log in with Discord to use the cloud")
    acl = cloud_acl.access(request, fresh)
    if not acl.best():
        _audit(request, user, "denied", path, False, f"{action}: no Cloud access")
        raise ApiError(403, "cloud_only", "You do not have access to the cloud")
    return user, acl


def _deny(request: Request, user: dict, action: str, path: str, level: str | None, edit: bool = True):
    """This person may not do this with this folder or file: logged and refused."""
    if edit and level:
        why, message = "needs Cloud edit", "You do not have permission to change this file or folder"
    else:
        why, message = "no access to this item", "You do not have access to this file or folder"
    _audit(request, user, "denied", path, False, f"{action}: {why}")
    raise ApiError(403, "cloud_only", message)


def _fail(request: Request, user: dict, action: str, path: str, e: CloudError, size: int | None = None):
    _audit(request, user, action, path, False, e.message, size)
    raise ApiError(e.status, e.code, e.message) from None


@router.get("/list")
def listing(request: Request, path: str = "", as_type: str = "", as_id: str = ""):
    """as_type + as_id (console users, "View as"): the folder as that role ("role") or person ("user") sees it."""
    user, acl = _enter(request, "list", path)
    settings = request.app.state.settings
    viewing_as = None
    if as_id:
        try:
            mine = acl.level(cloud_acl.clean(path))
        except CloudError as e:
            raise ApiError(e.status, e.code, e.message) from None
        if mine != "admin":
            raise ApiError(403, "admin_only", "Only an admin of this folder can view it as someone else")
        if as_type not in ("role", "user") or not auth.is_discord_id(as_id):
            raise ApiError(400, "bad_id", "Choose a role or a person to view as")
        with request.app.state.sessionmaker() as db:
            acl = cloud_acl.access_as(settings, db, as_type, as_id, acl.rules)
        viewing_as = {"type": as_type, "id": as_id, "name": _names(settings)(as_type, as_id)}
    try:
        rel = cloud_acl.clean(path)
        if not acl.visible(rel):
            if viewing_as:  # the admin looking, not the person trying: not a refusal for the log
                raise ApiError(403, "cloud_only", f"{viewing_as['name']} has no access to this folder" if rel
                               else f"{viewing_as['name']} has no access to the cloud: no Cloud tab")
            _deny(request, user, "list", path, None, edit=False)
        result = cloud.listing(settings, rel)
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None  # browsing is not logged, only refusals of access
    level = acl.level(rel)
    admin = level == "admin" and not viewing_as  # sets permissions here: sees what has rules, and what is inherited
    if admin:  # what the folders above (and this one) pass down to every row here
        above = cloud_acl.chain(acl.rules, rel)
        passed = next((r for r in reversed(above) if r["private"]), None) or next(
            (r for r in reversed(above) if r["grants"]), None)
        result["inherited"] = passed and {"path": passed["path"], "private": passed["private"]}
    result["viewing_as"] = viewing_as
    entries = []
    for e in result["entries"]:
        item = cloud_acl.join(rel, e["name"])
        if not (acl.visible(item) if e["dir"] else acl.level(item)):
            continue  # not for this person: not even its name
        e["can_edit"] = acl.can_change(item)  # rename / delete
        if not viewing_as and acl.level(item) == "admin":  # its admin sets its permissions, and sees whether it has any
            e["can_manage"] = True
            rule = acl.rules.get(item.casefold())
            if rule:
                e["private"], e["shared"] = rule["private"], len(rule["grants"])
        entries.append(e)
    # limited: only what is shared with them shows here (they have no access to the folder itself)
    # manages: admin somewhere in the cloud (the page offers the list of all permissions they control)
    return result | {"entries": entries, "can_edit": cloud_acl.edits(level), "can_manage": admin,
                     "manages": not viewing_as and acl.manages(), "limited": level is None}


@router.get("/download")
def download(request: Request, path: str):
    user, acl = _enter(request, "download", path)
    settings = request.app.state.settings
    try:
        rel = cloud_acl.clean(path)
        if not acl.level(rel):
            _deny(request, user, "download", path, None, edit=False)
        file = cloud.file_for_download(settings, rel)
    except CloudError as e:
        folder, _, name = path.strip("/").rpartition("/")
        if e.code == "not_found" and any(p["name"] == name for p in antivirus.pending_in(settings, folder)):
            e = CloudError(409, "scanning", "This file is still being checked for viruses. Try again in a moment.")
        _fail(request, user, "download", path, e)
    # a resumed download or a video player asks for parts: logged once, for the request from the start
    span = request.headers.get("range", "")
    if not span or span.replace(" ", "").startswith("bytes=0-"):
        _audit(request, user, "download", path, size=file.stat().st_size)
    # always a download, never shown as a page: an uploaded .html or .svg cannot run on this site (sandbox, octet-stream)
    return BigBlockFileResponse(file, filename=file.name, media_type="application/octet-stream",
                        content_disposition_type="attachment",
                        headers={"Content-Security-Policy": "sandbox", "Content-Encoding": "identity"})  # identity: no gzip of big files


class Target(BaseModel):
    path: str = ""
    name: str = ""
    parents: bool = False  # folder: make the missing folders above it too
    private: bool = False  # folder (console users): private from the moment it exists


@router.post("/folder")
def make_folder(request: Request, body: Target):
    where = cloud.relative_join(body.path, body.name)
    user, acl = _enter(request, "folder", where, fresh=True)
    sessions = request.app.state.sessionmaker
    try:
        folder = cloud_acl.clean(body.path)
        target = cloud_acl.join(folder, cloud.check_name(body.name))
        level = acl.level(target)
        if not cloud_acl.edits(level):
            _deny(request, user, "folder", where, level)
        if body.private and level != "admin":
            _audit(request, user, "denied", where, False, "private folder: needs Cloud admin")
            raise ApiError(403, "admin_only", "Only an admin of this folder can make a private folder in it")
        if body.private:  # the rule first: the folder is never there without it
            if cloud.resolve(request.app.state.settings, target).exists():
                raise CloudError(409, "exists", f"'{body.name.strip()}' already exists here")
            cloud_acl.save(sessions, target, True, [], user)
        try:
            result = cloud.make_folder(request.app.state.settings, folder, body.name, body.parents)
        except CloudError:
            if body.private:
                cloud_acl.save(sessions, target, False, [], user)
            raise
    except CloudError as e:
        _fail(request, user, "folder", where, e)
    _audit(request, user, "folder", result["path"], detail="private" if body.private else None)
    return result


def _whole(request: Request, user: dict, acl: cloud_acl.Access, action: str, path: str, rel: str) -> None:
    """Rename / delete: edit on the item and on everything inside it that has its own permissions."""
    if not acl.can_change(rel):
        level = acl.level(rel)
        if cloud_acl.edits(level):
            _audit(request, user, "denied", path, False, f"{action}: holds items this person cannot change")
            raise ApiError(403, "cloud_only", "This folder holds items you do not have permission to change")
        _deny(request, user, action, path, level)


@router.post("/rename")
def rename(request: Request, body: Target):
    user, acl = _enter(request, "rename", body.path, fresh=True)
    sessions = request.app.state.sessionmaker
    try:
        rel = cloud_acl.clean(body.path)
        _whole(request, user, acl, "rename", body.path, rel)
        level = acl.level(cloud_acl.join(rel.rpartition("/")[0], cloud.check_name(body.name)))
        if not cloud_acl.edits(level):  # the new name has permissions of its own that keep this person out
            _deny(request, user, "rename", body.path, level)
        result = cloud.rename(request.app.state.settings, rel, body.name)
        if rel and result["path"] != rel:
            cloud_acl.move(sessions, rel, result["path"], user)  # its permissions go with it
    except CloudError as e:
        _fail(request, user, "rename", body.path, e)
    _audit(request, user, "rename", body.path, detail=result["path"])
    return result


@router.post("/delete")
def delete(request: Request, body: Target):
    user, acl = _enter(request, "delete", body.path, fresh=True)
    try:
        rel = cloud_acl.clean(body.path)
        _whole(request, user, acl, "delete", body.path, rel)
        gone = cloud.delete(request.app.state.settings, rel, user, cloud_acl.stash(acl, rel) if rel else None)
        cloud_acl.forget(request.app.state.sessionmaker, rel)  # kept in the recycle bin note, back with a restore
    except CloudError as e:
        _fail(request, user, "delete", body.path, e)
    _audit(request, user, "delete", body.path, detail="to the recycle bin", size=gone["size"])
    return {"ok": True}


# --- recycle bin: console users (user, 2026-11-10: a Delete can be undone easily in the Console) -----------------------

def _require_console(request: Request, action: str, fresh: bool = False) -> dict:
    user = auth.viewer(request)
    if not user:
        raise ApiError(401, "login_required", "Log in with Discord")
    if not auth.has_console(request, fresh=fresh):
        _audit(request, user, "denied", "", False, f"{action}: console only")
        raise ApiError(403, "console_only", "Only console users can use the cloud recycle bin")
    return user


@router.get("/trash")
def trash(request: Request):
    _require_console(request, "recycle bin")
    settings = request.app.state.settings
    expired = cloud.purge_expired(settings)
    if expired:
        log.warning("Cloud: %d recycle bin item(s) older than %d days removed for good", len(expired), settings.cloud_trash_days)
    items = cloud.trash_items(settings)
    return {"items": items, "bytes": sum(i["size"] for i in items), "days": settings.cloud_trash_days}


class TrashChoice(BaseModel):
    id: str = ""
    all: bool = False  # purge: empty the whole recycle bin


@router.post("/trash/restore")
def trash_restore(request: Request, body: TrashChoice):
    user = _require_console(request, "restore", fresh=True)
    sessions = request.app.state.sessionmaker
    try:  # its folder / file permissions come back with it (set just before it is back in the cloud)
        result = cloud.restore(request.app.state.settings, body.id,
                               lambda path, rules: cloud_acl.put_back(sessions, path, rules, user))
    except CloudError as e:
        _fail(request, user, "restore", body.id, e)
    _audit(request, user, "restore", result["path"], detail="from the recycle bin", size=result["size"])
    return result


@router.post("/trash/purge")
def trash_purge(request: Request, body: TrashChoice):
    user = _require_console(request, "remove for good", fresh=True)
    settings = request.app.state.settings
    try:
        if body.all:
            result = cloud.purge_all(settings)
            _audit(request, user, "purge", "(whole recycle bin)", detail=f"{result['count']} items", size=result["size"])
        else:
            result = cloud.purge(settings, body.id)
            _audit(request, user, "purge", result["path"], detail="removed for good", size=result["size"])
    except CloudError as e:
        _fail(request, user, "purge", body.id, e)
    return result


@router.get("/upload/status")
def upload_status(request: Request, upload: str, total: int):
    """How much of this upload the server already has (user, 2026-11-10: an interrupted upload continues where it
    stopped). The page derives the upload id from the file and where it goes, so choosing the same file again resumes."""
    user, _ = _enter(request, "upload", "")  # only this person's own upload; starting one checks the folder (below)
    try:
        part = cloud.part_path(request.app.state.settings, user["id"], upload, total)
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None
    return {"received": part.stat().st_size if part.is_file() else 0}


def _may_upload(request: Request, where: str, path: str, name: str, total: int) -> dict:
    """Edit on the file's own path: the folder's permissions, or the file's own when it has any."""
    user, acl = _enter(request, "upload", where)
    try:
        level = acl.level(cloud_acl.join(cloud_acl.clean(path), cloud.check_name(name)))
    except CloudError as e:
        _fail(request, user, "upload", where, e, total)
    if not cloud_acl.edits(level):
        _deny(request, user, "upload", where, level)
    return user


@router.post("/upload")
async def upload(request: Request, name: str, upload: str, offset: int, total: int, path: str = "",
                 overwrite: bool = False, folders: bool = False):
    """One chunk of a file (the body, at most cloud.CHUNK_MAX bytes) at `offset` of `total`. The page sends the chunks
    in order with the same random `upload` id; the last one moves the file into the folder. Logged when the file is
    complete, or refused (a refusal only once: at the first chunk)."""
    settings = request.app.state.settings
    where = cloud.relative_join(path, name)
    first = offset == 0
    if first:  # Cloud edit checked when a file starts (roles remembered up to 5 minutes, not a Discord request per file: a
        # folder of 300 files was 300 Discord requests); its part file is then this person's. Rename / delete ask fresh
        user = await run_in_threadpool(_may_upload, request, where, path, name, total)
    else:  # later chunks: the login only (no permission queries per 16 MB); the part must be this person's own (below)
        user = auth.viewer(request)
        if not user:
            raise ApiError(401, "login_required", "Log in with Discord to use the cloud")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cloud.CHUNK_MAX:
        raise ApiError(413, "chunk_too_big", "Upload chunk too big")

    def fail(e: CloudError):
        if first:
            return _fail(request, user, "upload", where, e, total)
        raise ApiError(e.status, e.code, e.message) from None

    try:
        part = cloud.part_path(settings, user["id"], upload, total)
        if first:
            target = await run_in_threadpool(cloud.upload_target, settings, path, name, overwrite, folders)
            await run_in_threadpool(cloud.start_upload, settings, part, target, total, overwrite)
        else:
            have = part.stat().st_size if part.is_file() else -1
            if have < offset:
                raise CloudError(409, "out_of_sync", "This upload was interrupted. Start it again.")
            if have > offset:  # the same chunk sent again after a dropped connection: forget its first try
                with open(part, "r+b") as f:
                    f.truncate(offset)
    except CloudError as e:
        await run_in_threadpool(fail, e)
    received = offset
    block = bytearray()
    with open(part, "ab") as f:
        async for chunk in request.stream():
            received += len(chunk)
            if received > total or received - offset > cloud.CHUNK_MAX:
                f.close()
                part.unlink(missing_ok=True)
                raise ApiError(400, "bad_upload", "More data than the file size given")
            block += chunk
            if len(block) >= WRITE_BLOCK:
                await run_in_threadpool(f.write, block)
                block = bytearray()
        if block:
            await run_in_threadpool(f.write, block)
    if received < total:
        return {"done": False, "received": received}
    try:
        target = await run_in_threadpool(cloud.upload_target, settings, path, name, overwrite)  # still free?
        replacing = target.is_file()
        done = cloud.relative(settings, target)
        if antivirus.scannable(settings, total):  # waits for its virus scan; not downloadable until clean
            await run_in_threadpool(antivirus.hold, settings, part, done, overwrite, user, total)
            cloud._adjust_usage(settings, total)
            request.app.state.antivirus.notify()
        else:
            await run_in_threadpool(cloud.finish_upload, settings, part, target)
            request.app.state.virustotal.enqueue(done, user)  # background fingerprint check (when a key is set)
    except CloudError as e:
        part.unlink(missing_ok=True)
        await run_in_threadpool(_fail, request, user, "upload", where, e, total)
    scanning = antivirus.scannable(settings, total)
    detail = ", ".join(x for x in ("replaced" if replacing else "", "checking for viruses" if scanning else "") if x) or None
    await run_in_threadpool(_audit, request, user, "upload", done, True, detail, total)
    return {"done": True, "received": received, "path": done, "scanning": scanning}


# --- virus scanning: console users (user, 2026-11-10) -------------------------------------------------------------------

@router.get("/quarantine")
def quarantine(request: Request):
    _require_console(request, "quarantine")
    settings = request.app.state.settings
    return {"items": antivirus.quarantine_items(settings), "scanner": antivirus.status(settings),
            "virustotal": request.app.state.virustotal.status(), "waiting": antivirus.pending_count(settings),
            "sweep": {k: v for k, v in request.app.state.antivirus.sweep.items() if k != "by"},
            "scanner_error": request.app.state.antivirus.last_error}


@router.post("/quarantine/delete")
def quarantine_delete(request: Request, body: TrashChoice):
    user = _require_console(request, "quarantine delete", fresh=True)
    try:
        result = antivirus.quarantine_delete(request.app.state.settings, body.id)
    except CloudError as e:
        _fail(request, user, "purge", body.id, e)
    _audit(request, user, "purge", result["path"], detail=f"quarantined file deleted ({result['virus']})", size=result["size"])
    return result


@router.post("/quarantine/release")
def quarantine_release(request: Request, body: TrashChoice):
    """A false alarm: a console user lets the file into the cloud."""
    user = _require_console(request, "quarantine release", fresh=True)
    try:
        result = antivirus.quarantine_release(request.app.state.settings, body.id)
    except CloudError as e:
        _fail(request, user, "release", body.id, e)
    _audit(request, user, "release", result["path"], detail=f"released from the quarantine despite: {result['virus']}",
           size=result["size"])
    return result


@router.post("/scan-all")
def scan_all(request: Request):
    """Every file already in the cloud: ClamAV where it is (and VirusTotal after), one at a time in the background."""
    user = _require_console(request, "scan all", fresh=True)
    settings = request.app.state.settings
    if not (antivirus.enabled(settings) or settings.virustotal_key):
        raise ApiError(409, "scanning_off", "Virus scanning is not set up (ECHOVR_CLAMAV / ECHOVR_VIRUSTOTAL_KEY)")
    queued = request.app.state.antivirus.scan_existing(user)
    if not antivirus.enabled(settings):  # ClamAV off: the sweep thread is not running, VirusTotal only
        for folder in [cloud.root(settings)]:
            for rel in [cloud.relative(settings, f) for f in folder.rglob("*") if f.is_file() and not f.is_symlink()]:
                request.app.state.virustotal.enqueue(rel, user)
        request.app.state.antivirus.sweep["running"] = False
    _audit(request, user, "scan", "(all existing files)", detail=f"started: {queued} files")
    return {"queued": queued}


# --- permissions of one folder or file: its admins (cloud_acl.py; user, 2026-11-16) -------------------------------------

def _admin(request: Request, action: str, path: str | None = None, fresh: bool = False) -> tuple[dict, cloud_acl.Access]:
    """Admin of `path` (Cloud admin, console user, or listed as Admin on it or on a folder above it). path None: admin
    of anything in the cloud. Raises CloudError for a path the cloud refuses."""
    user, acl = _enter(request, action, path or "", fresh)
    if (acl.level(cloud_acl.clean(path)) != "admin") if path is not None else not acl.manages():
        _audit(request, user, "denied", path or "", False, f"{action}: needs Cloud admin")
        raise ApiError(403, "admin_only", "Only an admin of this folder or file can do that" if path is not None
                       else "Only Cloud admins can do that")
    return user, acl


def _names(settings):
    """(type, Discord id) -> the role's or the person's name, "?" when it cannot be found."""
    roles = {r["id"]: r["name"] for r in _server_roles(settings) or []}
    return lambda kind, i: roles.get(i, "?") if kind == "role" else auth.user_name(settings, i)


def _rule_state(request: Request, rel: str) -> dict:
    settings = request.app.state.settings
    target = cloud.resolve(settings, rel)
    if not rel or not target.exists():
        raise CloudError(404, "not_found", "Not found")
    name = _names(settings)

    def named(grants: list[dict]) -> list[dict]:
        return [g | {"name": name(g["type"], g["id"])} for g in grants]

    with request.app.state.sessionmaker() as db:
        rules = cloud_acl.load(db)
        effective = named(cloud_acl.effective(settings, db, rel, rules))
    above = cloud_acl.chain(rules, rel, itself=False)
    own = rules.get(rel.casefold(), {"private": False, "grants": []})
    return {"path": rel, "dir": target.is_dir(), "private": own["private"], "grants": named(own["grants"]),
            "above": [{"path": r["path"], "private": r["private"], "grants": named(r["grants"])} for r in above],
            "effective": effective,  # who ends up with what, all rules and whole-Cloud permissions together
            "server_roles": _server_roles(settings)}


@router.get("/permissions/all")
def all_permissions(request: Request):
    """Every folder / file with permissions of its own that this person is admin of (all of them for a Cloud admin),
    and whether the item is still there. Also the Discord server's roles, for the pickers."""
    _, acl = _admin(request, "permissions")
    settings = request.app.state.settings
    name = _names(settings)
    out = []
    for rule in sorted(acl.rules.values(), key=lambda r: r["path"].casefold()):
        if acl.level(rule["path"]) != "admin":
            continue
        try:
            target = cloud.resolve(settings, rule["path"])
            exists, is_dir = target.exists(), target.is_dir()
        except CloudError:
            exists = is_dir = False
        out.append({"path": rule["path"], "private": rule["private"], "exists": exists, "dir": is_dir,
                    "grants": [g | {"name": name(g["type"], g["id"])} for g in rule["grants"]],
                    "updated_at": rule["updated_at"], "by": rule["by"]})
    return {"rules": out, "server_roles": _server_roles(settings)}


@router.get("/people")
def people(request: Request, q: str = Query("", max_length=60)):
    """Find a person's Discord id by name (cloud admins): players seen in matches, people in the cloud audit log,
    and the Discord server's members when the bot may search them. At most 20."""
    _admin(request, "people search")
    term = q.strip()
    if len(term) < 2:
        return {"people": []}
    from sqlalchemy import or_, select

    from ..models import CloudLog, NakamaAccount
    settings = request.app.state.settings
    found: dict[str, dict] = {}
    like = f"%{term}%"
    try:  # the server's own members first: the name the admin knows from Discord
        if settings.discord_bot_token:
            r = auth._bot_get(settings, f"/guilds/{settings.discord_guild_id}/members/search?query={quote(term)}&limit=10")
            for m in r.json() if r.status_code == 200 else []:
                u = m.get("user") or {}
                if auth.is_discord_id(str(u.get("id") or "")):
                    found[u["id"]] = {"id": u["id"], "name": m.get("nick") or u.get("global_name") or u.get("username") or "?",
                                      "from": "Discord server"}
    except Exception as e:  # Discord down or the bot not allowed: the other two sources still answer
        log.warning("Discord member search failed: %s", e)
    with request.app.state.sessionmaker() as db:
        accounts = db.execute(select(NakamaAccount.discord_id, NakamaAccount.display_name, NakamaAccount.username).where(
            NakamaAccount.discord_id.is_not(None), or_(NakamaAccount.username.ilike(like), NakamaAccount.display_name.ilike(like))
        ).order_by(NakamaAccount.last_seen_at.desc()).limit(20)).all()
        logged = db.execute(select(CloudLog.who_id, CloudLog.who_name).where(CloudLog.who_name.ilike(like))
                            .group_by(CloudLog.who_id).limit(20)).all()
    for i, shown, username in accounts:
        if auth.is_discord_id(i or ""):
            found.setdefault(i, {"id": i, "name": shown or username, "from": "player"})
    for i, shown in logged:
        if auth.is_discord_id(i or ""):
            found.setdefault(i, {"id": i, "name": shown, "from": "used the cloud"})
    return {"people": list(found.values())[:20]}


@router.get("/permissions")
def item_permissions(request: Request, path: str):
    """Who one folder or file is shared with, whether it is private, and the rules of the folders above it."""
    try:
        _admin(request, "permissions", path)
        return _rule_state(request, cloud_acl.clean(path))
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None


class Rule(BaseModel):
    path: str
    private: bool = False
    grants: list[dict] = []  # {"type": "role" | "user", "id": Discord id, "level": "view" | "edit" | "admin"}


@router.post("/permissions")
def set_item_permissions(request: Request, body: Rule):
    """Replaces the permissions of one folder or file (nothing listed and not private: none of its own)."""
    try:
        user, acl = _admin(request, "permissions change", body.path, fresh=True)
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None
    try:
        rel = cloud_acl.clean(body.path)
        grants = cloud_acl.check_grants(body.grants)
        after = cloud_acl.Access(acl.user_id, acl.base, acl.console, acl.rules | (
            {rel.casefold(): {"path": rel, "private": body.private, "grants": grants}} if body.private or grants else {}), acl.roles)
        if not (body.private or grants):
            after.rules = {k: r for k, r in acl.rules.items() if k != rel.casefold()}
        if after.level(rel) != "admin":  # their admin came from this item's own rule: they would lock themselves out
            raise CloudError(400, "locks_you_out", "With this change you would no longer be an admin of this item. "
                             "Keep yourself (or one of your roles) listed as Admin, or ask an admin of the folder above.")
        if not body.private and not grants and rel and not cloud.resolve(request.app.state.settings, rel).exists():
            # clearing what a file left behind that was removed with File Station (Console > Permissions)
            cloud_acl.save(request.app.state.sessionmaker, rel, False, [], user)
            _audit(request, user, "permissions", rel, detail="cleared (the item is gone)")
            return {"path": rel, "gone": True}
        _rule_state(request, rel)  # it must be there
        server = _server_roles(request.app.state.settings)
        if server is not None:  # a person's id is not a role, and the other way round (as on the Permissions page)
            role_ids = {r["id"] for r in server}
            for g in grants:
                if g["type"] == "role" and g["id"] not in role_ids:
                    raise CloudError(400, "not_a_role", f"{g['id']} is not a role in the Discord server. For a person, choose User.")
                if g["type"] == "user" and g["id"] in role_ids:
                    raise CloudError(400, "not_a_user", f"{g['id']} is a role, not a person. Choose Role for it.")
        cloud_acl.save(request.app.state.sessionmaker, rel, body.private, grants, user)
        state = _rule_state(request, rel)
    except CloudError as e:
        _fail(request, user, "permissions", body.path, e)
    _audit(request, user, "permissions", rel, detail=cloud_acl.describe(body.private, grants))
    return state


@router.get("/log")
def audit_log(request: Request, q: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=500),
              before: int | None = Query(None, ge=1)):
    """The cloud audit log, newest first (`before`: the id to continue from). Console users only."""
    if not auth.has_console(request):
        raise ApiError(403, "console_only", "Only console users can read the cloud audit log")
    return cloud.log_rows(request.app.state.sessionmaker, q.strip(), before, limit)
