"""Open Cloud endpoints (cloud.py): Discord login + the Cloud view / Cloud edit permission (Permissions page).
Changes are POSTs with the X-EchoVR header (middleware.py WRITES); the download link is opened by the browser itself
and is exempt from that header (guard.py), the session cookie (SameSite=Lax) still decides who may have the file."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import auth, cloud
from ..cloud import CloudError
from ..errors import ApiError

router = APIRouter(prefix="/api/cloud", tags=["cloud"])
log = logging.getLogger("uvicorn.error")


def _require(request: Request, edit: bool = False, fresh: bool = False) -> dict:
    user = auth.viewer(request)
    if not user:
        raise ApiError(401, "login_required", "Log in with Discord to use the cloud")
    access = auth.cloud_access(request, fresh=fresh)
    if access is None or (edit and access != "edit"):
        raise ApiError(403, "cloud_only", "You do not have permission to change cloud files" if access
                       else "You do not have access to the cloud")
    return user | {"access": access}


def _fail(e: CloudError):
    raise ApiError(e.status, e.code, e.message) from None


@router.get("/list")
def listing(request: Request, path: str = ""):
    user = _require(request)
    try:
        return cloud.listing(request.app.state.settings, path) | {"can_edit": user["access"] == "edit"}
    except CloudError as e:
        _fail(e)


@router.get("/download")
def download(request: Request, path: str):
    user = _require(request)
    try:
        file = cloud.file_for_download(request.app.state.settings, path)
    except CloudError as e:
        _fail(e)
    log.info("Cloud: %s (%s) downloaded %s", user["name"], user["id"], path)
    # always a download, never shown as a page: an uploaded .html or .svg cannot run on this site (sandbox, octet-stream)
    return FileResponse(file, filename=file.name, media_type="application/octet-stream",
                        content_disposition_type="attachment",
                        headers={"Content-Security-Policy": "sandbox", "Content-Encoding": "identity"})  # identity: no gzip of big files


class Target(BaseModel):
    path: str = ""
    name: str = ""


@router.post("/folder")
def make_folder(request: Request, body: Target):
    user = _require(request, edit=True, fresh=True)
    try:
        result = cloud.make_folder(request.app.state.settings, body.path, body.name)
    except CloudError as e:
        _fail(e)
    log.warning("Cloud: %s (%s) made folder %s", user["name"], user["id"], result["path"])
    return result


@router.post("/rename")
def rename(request: Request, body: Target):
    user = _require(request, edit=True, fresh=True)
    try:
        result = cloud.rename(request.app.state.settings, body.path, body.name)
    except CloudError as e:
        _fail(e)
    log.warning("Cloud: %s (%s) renamed %s to %s", user["name"], user["id"], body.path, result["path"])
    return result


@router.post("/delete")
def delete(request: Request, body: Target):
    user = _require(request, edit=True, fresh=True)
    try:
        cloud.delete(request.app.state.settings, body.path)
    except CloudError as e:
        _fail(e)
    log.warning("Cloud: %s (%s) deleted %s", user["name"], user["id"], body.path)
    return {"ok": True}


@router.post("/upload")
async def upload(request: Request, name: str, upload: str, offset: int, total: int, path: str = "",
                 overwrite: bool = False):
    """One chunk of a file (the body, at most cloud.CHUNK_MAX bytes) at `offset` of `total`. The page sends the chunks
    in order with the same random `upload` id; the last one moves the file into the folder."""
    settings = request.app.state.settings
    user = await run_in_threadpool(_require, request, True, offset == 0)  # Discord asked again when a file starts
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cloud.CHUNK_MAX:
        raise ApiError(413, "chunk_too_big", "Upload chunk too big")
    try:
        part = cloud.part_path(settings, user["id"], upload)
        target = await run_in_threadpool(cloud.upload_target, settings, path, name, overwrite)
        if offset == 0:
            await run_in_threadpool(cloud.start_upload, settings, part, target, total, overwrite)
        else:
            have = part.stat().st_size if part.is_file() else -1
            if have < offset:
                raise CloudError(409, "out_of_sync", "This upload was interrupted. Start it again.")
            if have > offset:  # the same chunk sent again after a dropped connection: forget its first try
                with open(part, "r+b") as f:
                    f.truncate(offset)
    except CloudError as e:
        _fail(e)
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
        _fail(e)
    log.warning("Cloud: %s (%s) uploaded %s (%d bytes)", user["name"], user["id"], cloud.relative(settings, target), total)
    return {"done": True, "received": received, "path": cloud.relative(settings, target)}
