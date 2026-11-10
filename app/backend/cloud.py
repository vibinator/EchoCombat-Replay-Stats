"""Open Cloud (user, 2026-11-10): file storage on the website for Discord members with the Cloud permission. Two
levels (Permissions page): Cloud view = list and download, Cloud edit = also upload, new folder, rename, delete.
Console users have both.

Files live in <data>/cloud on the NAS (kept across app updates like the database), never in the replay share.
Uploads arrive in chunks (Cloudflare refuses request bodies over 100 MB on its free plan): each chunk is appended
to <data>/cloud-uploads/<user>-<upload id>.part, and the finished file is moved into place in one step, so a
half-uploaded file never shows in the list. A part reserves its file's full size (quota and disk) while the upload
runs; parts nobody touched for 2 hours are deleted.

Every path from a visitor goes through resolve(): parts are checked one by one (no "..", no separators, no control
characters) and the result must stay inside the cloud folder, symlinks included."""

import os
import re
import shutil
import threading
import time
from pathlib import Path

from .config import Settings

CHUNK_MAX = 90 * 1024 * 1024  # one upload request at most: under Cloudflare's 100 MB body limit
RESERVE_BYTES = 5 * 1024**3  # an upload never leaves less than this free on the disk (the database needs room)
STALE_PART_S = 2 * 3600  # an upload untouched this long is given up (every chunk touches it; a 16 MB chunk takes ~20 min even at 0.1 Mbps)
USAGE_S = 60  # the "used" total is recounted at most this often (walking the folder is slow on the NAS)
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
BAD_CHARS = re.compile(r'[\x00-\x1f\x7f/\\<>:"|?*]')  # also the characters Windows refuses (tests, a copy to a PC)
WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}

_usage: dict[str, tuple[float, int]] = {}  # cloud folder -> (counted at, bytes)
_usage_lock = threading.Lock()
_start_lock = threading.Lock()  # checking room and reserving it is one step: parallel uploads cannot both take the last GB


class CloudError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def root(settings: Settings) -> Path:
    path = settings.data_dir / "cloud"
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads(settings: Settings) -> Path:
    path = settings.data_dir / "cloud-uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_name(name: str) -> str:
    """One file or folder name as typed or uploaded; raises CloudError when it cannot be stored safely."""
    name = (name or "").strip()
    if not name or name in (".", ".."):
        raise CloudError(400, "bad_name", "Enter a name")
    if len(name.encode()) > 255:
        raise CloudError(400, "bad_name", "Name too long (255 bytes at most)")
    if BAD_CHARS.search(name):
        raise CloudError(400, "bad_name", 'Names cannot contain / \\ < > : " | ? * or control characters')
    if name.endswith((".", " ")) or name.split(".")[0].lower() in WINDOWS_NAMES:
        raise CloudError(400, "bad_name", f"'{name}' cannot be used as a name")
    return name


def resolve(settings: Settings, rel: str | None) -> Path:
    """'' or None = the cloud folder itself; 'a/b.txt' = a file below it."""
    base = root(settings)
    parts = [p for p in (rel or "").replace("\\", "/").split("/") if p]
    path = base.joinpath(*(check_name(p) for p in parts))
    real = path.resolve()
    if real != base.resolve() and base.resolve() not in real.parents:
        raise CloudError(400, "bad_path", "That path is outside the cloud folder")
    return path


def relative_join(folder: str | None, name: str | None) -> str:
    """For the audit log only (not checked): what a person asked for, 'folder/name'."""
    return "/".join(p for p in ((folder or "").strip("/"), (name or "").strip()) if p)[:1000]


def size_of(settings: Settings, rel: str) -> int | None:
    """Bytes of a file, or of everything in a folder (the audit log of a delete)."""
    path = resolve(settings, rel)
    if not rel or not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())


def relative(settings: Settings, path: Path) -> str:
    return path.relative_to(root(settings)).as_posix() if path != root(settings) else ""


def _forget_usage() -> None:
    with _usage_lock:
        _usage.clear()


def used_bytes(settings: Settings) -> int:
    now, key = time.monotonic(), str(root(settings))
    with _usage_lock:
        hit = _usage.get(key)
        if hit and now - hit[0] < USAGE_S:
            return hit[1]
    total, todo = 0, [key]
    while todo:
        try:
            with os.scandir(todo.pop()) as items:
                for item in items:
                    try:
                        if item.is_dir(follow_symlinks=False):
                            todo.append(item.path)
                        elif item.is_file(follow_symlinks=False):
                            total += item.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    with _usage_lock:
        _usage[key] = (now, total)
    return total


def quota_bytes(settings: Settings) -> int:
    return int(settings.cloud_quota_gb * 1024**3)


def listing(settings: Settings, rel: str | None) -> dict:
    folder = resolve(settings, rel)
    if not folder.is_dir():
        raise CloudError(404, "not_found", "Folder not found")
    entries = []
    with os.scandir(folder) as items:  # scandir: the type (and on Windows the size) come with the listing, one stat at most
        for item in items:
            try:
                is_dir = item.is_dir()
                st = item.stat()
            except OSError:
                continue
            entries.append({"name": item.name, "dir": is_dir, "size": None if is_dir else st.st_size,
                            "modified": int(st.st_mtime)})
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return {"path": relative(settings, folder), "entries": entries, "used_bytes": used_bytes(settings),
            "quota_bytes": quota_bytes(settings)}


def file_for_download(settings: Settings, rel: str) -> Path:
    path = resolve(settings, rel)
    if not rel or not path.is_file():
        raise CloudError(404, "not_found", "File not found")
    return path


def make_folder(settings: Settings, rel: str | None, name: str) -> dict:
    parent = resolve(settings, rel)
    if not parent.is_dir():
        raise CloudError(404, "not_found", "Folder not found")
    target = parent / check_name(name)
    if target.exists():
        raise CloudError(409, "exists", f"'{target.name}' already exists here")
    target.mkdir()
    return {"path": relative(settings, target)}


def rename(settings: Settings, rel: str, name: str) -> dict:
    """A new name in the same folder (file or folder)."""
    source = resolve(settings, rel)
    if not rel or not source.exists():
        raise CloudError(404, "not_found", "Not found")
    target = source.parent / check_name(name)
    if target == source:
        return {"path": relative(settings, source)}
    if target.exists() and target.name.lower() != source.name.lower():  # a change of case only is fine
        raise CloudError(409, "exists", f"'{target.name}' already exists here")
    source.rename(target)
    return {"path": relative(settings, target)}


def delete(settings: Settings, rel: str) -> None:
    """A file, or a folder with everything in it."""
    path = resolve(settings, rel)
    if not rel or not path.exists():
        raise CloudError(404, "not_found", "Not found")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    _forget_usage()


# --- uploads -------------------------------------------------------------------------------------

def _clean_stale_parts(settings: Settings) -> None:
    cutoff = time.time() - STALE_PART_S
    for part in uploads(settings).glob("*.part"):
        try:
            if part.stat().st_mtime < cutoff:
                part.unlink()
        except OSError:
            pass


def part_path(settings: Settings, user_id: str, upload_id: str, total: int) -> Path:
    """The parts are per person: nobody can append to someone else's upload. The name holds the file's full size,
    which stays reserved (quota and disk) until the upload finishes or is cleaned up."""
    if not UPLOAD_ID.match(upload_id or "") or not user_id.isdigit() or total < 0:
        raise CloudError(400, "bad_upload", "Bad upload id or file size")
    return uploads(settings) / f"{user_id}-{upload_id}-{total}.part"


def _reserved(settings: Settings) -> tuple[int, int]:
    """(full sizes of the uploads in progress, bytes of them still to come)."""
    full = still = 0
    for part in uploads(settings).glob("*.part"):
        try:
            size = int(part.stem.rsplit("-", 1)[1])
            full, still = full + size, still + max(size - part.stat().st_size, 0)
        except (OSError, ValueError, IndexError):
            pass
    return full, still


def upload_target(settings: Settings, rel: str | None, name: str, overwrite: bool) -> Path:
    folder = resolve(settings, rel)
    if not folder.is_dir():
        raise CloudError(404, "not_found", "Folder not found")
    target = folder / check_name(name)
    if target.is_dir():
        raise CloudError(409, "exists", f"'{target.name}' is a folder here")
    if target.exists() and not overwrite:
        raise CloudError(409, "exists", f"'{target.name}' already exists here")
    return target


def start_upload(settings: Settings, part: Path, target: Path, total: int, overwrite: bool) -> None:
    """First chunk: room for the whole file (quota and free disk, counting the uploads still in progress), then an
    empty part file that reserves it."""
    _clean_stale_parts(settings)
    replaced = target.stat().st_size if overwrite and target.is_file() else 0
    quota = quota_bytes(settings)
    with _start_lock:
        part.unlink(missing_ok=True)  # the same upload started again: its old reservation does not count
        reserved, still = _reserved(settings)
        if quota and used_bytes(settings) + reserved - replaced + total > quota:
            free = max(quota - used_bytes(settings) - reserved + replaced, 0)
            raise CloudError(413, "quota", f"Not enough cloud space: {free / 1024**3:.1f} GB left of {quota / 1024**3:.0f} GB"
                             + (" (uploads in progress count)" if reserved else ""))
        if shutil.disk_usage(uploads(settings)).free - still - total < RESERVE_BYTES:
            raise CloudError(507, "disk_full", "The server's disk is almost full")
        part.write_bytes(b"")


def finish_upload(settings: Settings, part: Path, target: Path) -> None:
    os.replace(part, target)  # same disk (both in the data folder): one step, never half a file
    _forget_usage()


# --- audit log -----------------------------------------------------------------------------------

def log(sessions, user: dict, action: str, path: str, ok: bool = True, detail: str | None = None,
        size: int | None = None, ip: str | None = None) -> None:
    """One line in the cloud audit log. Never stops the action it records: a failed write is only logged."""
    from .db import utcnow
    from .models import CloudLog
    try:
        with sessions() as db:
            db.add(CloudLog(at=utcnow(), who_id=user["id"], who_name=user["name"], action=action, path=path or "/",
                            detail=detail, size=size, ok=ok, ip=ip))
            db.commit()
    except Exception as e:  # e.g. the database busy for longer than its timeout
        import logging
        logging.getLogger("uvicorn.error").warning("Cloud audit log not written (%s %s by %s): %s", action, path, user["id"], e)


def log_rows(sessions, term: str = "", before: int | None = None, limit: int = 100) -> list[dict]:
    """Newest first; `term` matches the person (name or id), the action or the file."""
    from sqlalchemy import or_, select

    from .models import CloudLog
    query = select(CloudLog).order_by(CloudLog.id.desc()).limit(limit)
    if term:
        like = f"%{term}%"
        query = query.where(or_(CloudLog.who_name.ilike(like), CloudLog.who_id.ilike(like), CloudLog.action.ilike(like),
                                CloudLog.path.ilike(like), CloudLog.detail.ilike(like)))
    if before is not None:
        query = query.where(CloudLog.id < before)
    with sessions() as db:
        return [{"id": r.id, "at": r.at, "who": r.who_name, "who_id": r.who_id, "action": r.action, "path": r.path,
                 "detail": r.detail, "size": r.size, "ok": r.ok, "ip": r.ip} for r in db.scalars(query)]

