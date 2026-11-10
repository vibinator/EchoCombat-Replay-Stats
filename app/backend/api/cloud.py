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

from .. import auth, cloud, guard
from ..cloud import CloudError
from ..errors import ApiError

router = APIRouter(prefix="/api/cloud", tags=["cloud"])
log = logging.getLogger("uvicorn.error")


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
    try:
        file = cloud.file_for_download(request.app.state.settings, path)
    except CloudError as e:
        _fail(request, user, "download", path, e)
    # a resumed download or a video player asks for parts: logged once, for the request from the start
    span = request.headers.get("range", "")
    if not span or span.replace(" ", "").startswith("bytes=0-"):
        _audit(request, user, "download", path, size=file.stat().st_size)
    # always a download, never shown as a page: an uploaded .html or .svg cannot run on this site (sandbox, octet-stream)
    return FileResponse(file, filename=file.name, media_type="application/octet-stream",
                        content_disposition_type="attachment",
                        headers={"Content-Security-Policy": "sandbox", "Content-Encoding": "identity"})  # identity: no gzip of big files


class Target(BaseModel):
    path: str = ""
    name: str = ""


@router.post("/folder")
def make_folder(request: Request, body: Target):
    where = cloud.relative_join(body.path, body.name)
    user = _require(request, "folder", where, edit=True, fresh=True)
    try:
        result = cloud.make_folder(request.app.state.settings, body.path, body.name)
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
    settings = request.app.state.settings
    try:
        size = cloud.size_of(settings, body.path)
        cloud.delete(settings, body.path)
    except CloudError as e:
        _fail(request, user, "delete", body.path, e)
    _audit(request, user, "delete", body.path, size=size)
    return {"ok": True}


@router.post("/upload")
async def upload(request: Request, name: str, upload: str, offset: int, total: int, path: str = "",
                 overwrite: bool = False):
    """One chunk of a file (the body, at most cloud.CHUNK_MAX bytes) at `offset` of `total`. The page sends the chunks
    in order with the same random `upload` id; the last one moves the file into the folder. Logged when the file is
    complete, or refused (a refusal only once: at the first chunk)."""
    settings = request.app.state.settings
    where = cloud.relative_join(path, name)
    first = offset == 0
    user = await run_in_threadpool(_require, request, "upload", where, True, first)  # Discord asked again when a file starts
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cloud.CHUNK_MAX:
        raise ApiError(413, "chunk_too_big", "Upload chunk too big")

    def fail(e: CloudError):
        if first:
            return _fail(request, user, "upload", where, e, total)
        raise ApiError(e.status, e.code, e.message) from None

    try:
        part = cloud.part_path(settings, user["id"], upload, total)
        target = await run_in_threadpool(cloud.upload_target, settings, path, name, overwrite)
        replacing = target.is_file()
        if first:
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
    with open(part, "ab") as f:
        async for chunk in request.stream():
            received += len(chunk)
            if received > total or received - offset > cloud.CHUNK_MAX:
                f.close()
                part.unlink(missing_ok=True)
                raise ApiError(400, "bad_upload", "More data than the file size given")
            await run_in_threadpool(f.write, chunk)
    if received < total:
        return {"done": False, "received": received}
    try:
        target = await run_in_threadpool(cloud.upload_target, settings, path, name, overwrite)  # still free?
        await run_in_threadpool(cloud.finish_upload, settings, part, target)
    except CloudError as e:
        part.unlink(missing_ok=True)
        await run_in_threadpool(_fail, request, user, "upload", where, e, total)
    done = cloud.relative(settings, target)
    await run_in_threadpool(_audit, request, user, "upload", done, True, "replaced" if replacing else None, total)
    return {"done": True, "received": received, "path": done}


@router.get("/log")
def audit_log(request: Request, q: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=500),
              before: int | None = Query(None, ge=1)):
    """The cloud audit log, newest first (`before`: the id to continue from). Console users only."""
    if not auth.has_console(request):
        raise ApiError(403, "console_only", "Only console users can read the cloud audit log")
    return cloud.log_rows(request.app.state.sessionmaker, q.strip(), before, limit)
