"""Open Cloud endpoints (cloud.py): Discord login + the Cloud view / Cloud edit permission (Permissions page).
Changes are POSTs with the X-EchoVR header (middleware.py WRITES); the download link is opened by the browser itself
and is exempt from that header (guard.py), the session cookie (SameSite=Lax) still decides who may have the file.

Audit log (user, 2026-11-10): every upload, download, new folder, rename and delete goes into cloud_log with who did
it, and so does every refusal of a logged-in person (no permission, no space, a bad name). Anonymous refusals are not
logged: there is nobody to name. Console users read it at /api/cloud/log (Console > Audit log > Cloud audit log)."""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import antivirus, auth, cloud, guard
from ..cloud import CloudError
from ..errors import ApiError

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


def _require(request: Request, action: str, path: str, edit: bool = False, fresh: bool = False) -> dict:
    user = auth.viewer(request)
    if not user:
        raise ApiError(401, "login_required", "Log in with Discord to use the cloud")
    access = auth.cloud_access(request, fresh=fresh)
    if access is None or (edit and access != "edit"):
        _audit(request, user, "denied", path, False, f"{action}: {'needs Cloud edit' if access else 'no Cloud access'}")
        raise ApiError(403, "cloud_only", "You do not have permission to change cloud files" if access
                       else "You do not have access to the cloud")
    return user | {"access": access}


def _fail(request: Request, user: dict, action: str, path: str, e: CloudError, size: int | None = None):
    _audit(request, user, action, path, False, e.message, size)
    raise ApiError(e.status, e.code, e.message) from None


@router.get("/list")
def listing(request: Request, path: str = ""):
    user = _require(request, "list", path)
    try:
        return cloud.listing(request.app.state.settings, path) | {"can_edit": user["access"] == "edit"}
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None  # browsing is not logged, only refusals of access


@router.get("/download")
def download(request: Request, path: str):
    user = _require(request, "download", path)
    settings = request.app.state.settings
    try:
        file = cloud.file_for_download(settings, path)
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


@router.post("/folder")
def make_folder(request: Request, body: Target):
    where = cloud.relative_join(body.path, body.name)
    user = _require(request, "folder", where, edit=True, fresh=True)
    try:
        result = cloud.make_folder(request.app.state.settings, body.path, body.name, body.parents)
    except CloudError as e:
        _fail(request, user, "folder", where, e)
    _audit(request, user, "folder", result["path"])
    return result


@router.post("/rename")
def rename(request: Request, body: Target):
    user = _require(request, "rename", body.path, edit=True, fresh=True)
    try:
        result = cloud.rename(request.app.state.settings, body.path, body.name)
    except CloudError as e:
        _fail(request, user, "rename", body.path, e)
    _audit(request, user, "rename", body.path, detail=result["path"])
    return result


@router.post("/delete")
def delete(request: Request, body: Target):
    user = _require(request, "delete", body.path, edit=True, fresh=True)
    try:
        gone = cloud.delete(request.app.state.settings, body.path, user)
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
    try:
        result = cloud.restore(request.app.state.settings, body.id)
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
    user = _require(request, "upload", "", edit=True)
    try:
        part = cloud.part_path(request.app.state.settings, user["id"], upload, total)
    except CloudError as e:
        raise ApiError(e.status, e.code, e.message) from None
    return {"received": part.stat().st_size if part.is_file() else 0}


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
        user = await run_in_threadpool(_require, request, "upload", where, True, False)
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


@router.get("/log")
def audit_log(request: Request, q: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=500),
              before: int | None = Query(None, ge=1)):
    """The cloud audit log, newest first (`before`: the id to continue from). Console users only."""
    if not auth.has_console(request):
        raise ApiError(403, "console_only", "Only console users can read the cloud audit log")
    return cloud.log_rows(request.app.state.sessionmaker, q.strip(), before, limit)
