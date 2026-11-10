"""Open Cloud (user, 2026-11-10): file storage on the website for Discord members with the Cloud permission. Two
levels (Permissions page): Cloud view = list and download, Cloud edit = also upload, new folder, rename, delete.
Console users have both.

Files live in <data>/cloud on the NAS (kept across app updates like the database), never in the replay share.
Uploads arrive in chunks (Cloudflare refuses request bodies over 100 MB on its free plan): each chunk is appended
to <data>/cloud-uploads/<user>-<upload id>.part, and the finished file is moved into place in one step, so a
half-uploaded file never shows in the list. A part reserves its file's full size (quota and disk) while the upload
runs; an interrupted upload continues where it stopped (same upload id: the page derives it from the file), and parts
nobody touched for a day are deleted.

Delete moves the file or folder into the recycle bin, <data>/cloud-trash/<id>/item with info.json beside it (where it
was, who deleted it, when): one rename on the same disk, instant and no CPU even for a big folder. Console users
restore or remove it for good; after ECHOVR_CLOUD_TRASH_DAYS it goes by itself. The recycle bin counts toward the quota.

Space used (cloud + recycle bin) is counted once, then kept as a running total (an upload adds its size, removing for
good subtracts); a full recount every USAGE_RECOUNT_S picks up changes made outside the site (File Station).

Every path from a visitor goes through resolve(): parts are checked one by one (no "..", no separators, no control
characters) and the result must stay inside the cloud folder, symlinks included."""

import json
import os
import re
import secrets
import shutil
import threading
import time
from pathlib import Path

from .config import Settings

CHUNK_MAX = 90 * 1024 * 1024  # one upload request at most: under Cloudflare's 100 MB body limit
RESERVE_BYTES = 5 * 1024**3  # an upload never leaves less than this free on the disk (the database needs room)
STALE_PART_S = 24 * 3600  # an upload untouched this long is given up; until then it can be resumed (the page asks /upload/status)
USAGE_RECOUNT_S = 600  # full recount of the space used at most this often; in between a running total (no folder walk)
TRASH_ID = re.compile(r"^\d{14}-[0-9a-f]{8}$")
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
BAD_CHARS = re.compile(r'[\x00-\x1f\x7f/\\<>:"|?*]')  # also the characters Windows refuses (tests, a copy to a PC)
MAX_DEPTH = 32  # folders inside folders, at most (a dropped folder tree keeps its shape)
WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}

_usage: dict[str, list] = {}  # data folder -> [bytes in the cloud + recycle bin, counted at (monotonic)]
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


def trash_root(settings: Settings) -> Path:
    path = settings.data_dir / "cloud-trash"
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
    if len(parts) > MAX_DEPTH:
        raise CloudError(400, "bad_path", f"Folders can be at most {MAX_DEPTH} deep")
    # Every name is checked (no "..", no separators), so the path cannot leave the cloud folder by itself; only a link
    # planted on the NAS could. Each existing part is looked at once (lstat) and a link is refused. Before: resolve() of the
    # whole path, which on Windows could return another spelling while parallel uploads created its folders (a false refusal)
    path = base
    for part in parts:
        path = path / check_name(part)
        if path.is_symlink():
            raise CloudError(400, "bad_path", "That path is outside the cloud folder (links are not followed)")
    return path


def relative_join(folder: str | None, name: str | None) -> str:
    """For the audit log only (not checked): what a person asked for, 'folder/name'."""
    return "/".join(p for p in ((folder or "").strip("/"), (name or "").strip()) if p)[:1000]


def make_box(parent: Path, item: Path, info: dict) -> str:
    """A recycle bin / waiting / quarantine box: built under a hidden name (".tmp-..."), the item moved in and its note
    written, then renamed to its real name in one step. Whoever lists the boxes (the scanner thread above all) never sees
    one without its note: a box seen half-built once sent a file next to the cloud folder instead of into it."""
    box_id = f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{secrets.token_hex(4)}"
    building = parent / f".tmp-{box_id}"
    building.mkdir()
    try:
        os.replace(item, building / "item")
    except OSError:
        building.rmdir()
        raise
    (building / "info.json").write_text(json.dumps(info), encoding="utf-8")
    os.replace(building, parent / box_id)
    return box_id


def _walk_size(path: Path) -> int:
    """Bytes of a file, or of every file below a folder (scandir: one listing per folder, symlinks not followed)."""
    try:
        if not path.is_dir() or path.is_symlink():
            return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0
    total, todo = 0, [str(path)]
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
    return total


def relative(settings: Settings, path: Path) -> str:
    return path.relative_to(root(settings)).as_posix() if path != root(settings) else ""


def _forget_usage() -> None:
    """Tests: count again from the disk."""
    with _usage_lock:
        _usage.clear()


def used_bytes(settings: Settings) -> int:
    """Cloud + recycle bin. Walks the folders only on the first ask and every USAGE_RECOUNT_S; otherwise the running
    total (upload: +size, removal for good: -size). Before, every upload start walked every file (34 ms CPU a file)."""
    now, key = time.monotonic(), str(settings.data_dir)
    with _usage_lock:
        hit = _usage.get(key)
        if hit and now - hit[1] < USAGE_RECOUNT_S:
            return hit[0]
    total = sum(_walk_size(settings.data_dir / d) for d in ("cloud", "cloud-trash", "cloud-pending", "cloud-quarantine"))
    with _usage_lock:
        _usage[key] = [total, now]
    return total


def _adjust_usage(settings: Settings, delta: int) -> None:
    with _usage_lock:
        hit = _usage.get(str(settings.data_dir))
        if hit:
            hit[0] = max(hit[0] + delta, 0)


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
    from . import antivirus  # here: antivirus imports this module
    if antivirus.enabled(settings):
        limit = antivirus.max_bytes(settings)
        for e in entries:  # bigger than ClamAV scans: never called clean
            if not e["dir"] and e["size"] > limit:
                e["state"] = "unscanned"
        entries += [p | {"dir": False, "state": "scanning"} for p in antivirus.pending_in(settings, relative(settings, folder))]
    entries.sort(key=lambda e: (not e["dir"], e["name"].lower(), e.get("state") == "scanning"))
    return {"path": relative(settings, folder), "entries": entries, "used_bytes": used_bytes(settings),
            "quota_bytes": quota_bytes(settings), "trash_bytes": sum(i["size"] for i in trash_items(settings))}


def file_for_download(settings: Settings, rel: str) -> Path:
    path = resolve(settings, rel)
    if not rel or not path.is_file():
        raise CloudError(404, "not_found", "File not found")
    return path


def _make_parents(folder: Path) -> None:
    """Missing folders of an already checked path (resolve()): a file in the way is refused."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        raise CloudError(409, "exists", "A file has the name of a folder in this path") from None


def make_folder(settings: Settings, rel: str | None, name: str, parents: bool = False) -> dict:
    """parents: also make the missing folders above it (empty folders of an uploaded folder tree)."""
    parent = resolve(settings, rel)
    if parents and not parent.exists():
        _make_parents(parent)
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


def delete(settings: Settings, rel: str, user: dict) -> dict:
    """A file, or a folder with everything in it, into the recycle bin (one rename: instant, nothing is copied or erased)."""
    path = resolve(settings, rel)
    if not rel or not path.exists():
        raise CloudError(404, "not_found", "Not found")
    purge_expired(settings)
    size, is_dir = _walk_size(path), path.is_dir()
    box_id = make_box(trash_root(settings), path, {  # same disk: the space stays counted (the bin is part of the quota)
        "path": relative(settings, path), "dir": is_dir, "size": size, "deleted_at": int(time.time()),
        "by_id": user["id"], "by_name": user["name"]})
    return {"trash_id": box_id, "size": size}


# --- recycle bin (console users) -----------------------------------------------------------------

def _box(settings: Settings, trash_id: str) -> Path:
    if not TRASH_ID.match(trash_id or ""):
        raise CloudError(400, "bad_id", "Unknown recycle bin item")
    box = trash_root(settings) / trash_id
    if not (box / "item").exists() and not (box / "item").is_symlink():
        raise CloudError(404, "not_found", "Not in the recycle bin (restored or removed already)")
    return box


def _info(box: Path) -> dict:
    try:
        info = json.loads((box / "info.json").read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else {}
    except (OSError, ValueError):
        return {}


def trash_items(settings: Settings) -> list[dict]:
    """Newest first: id, where it was, file or folder, size, when and by whom it was deleted, when it goes for good."""
    days = settings.cloud_trash_days
    items = []
    with os.scandir(trash_root(settings)) as boxes:
        for box in boxes:
            if not TRASH_ID.match(box.name) or not os.path.lexists(os.path.join(box.path, "item")):
                continue
            info = _info(Path(box.path))
            deleted = int(info.get("deleted_at") or 0)
            items.append({"id": box.name, "path": str(info.get("path") or "?"), "dir": bool(info.get("dir")),
                          "size": int(info.get("size") or 0), "deleted_at": deleted, "by_id": str(info.get("by_id") or ""),
                          "by_name": str(info.get("by_name") or "?"), "expires_at": deleted + days * 86400 if days else None})
    items.sort(key=lambda i: i["id"], reverse=True)
    return items


def _free_name(target: Path) -> Path:
    """Where a restored item goes when something new has its name: 'report (restored 2026-11-10 1430).pdf'."""
    if not any(p.name == "cloud" for p in target.parents):  # never beside the cloud folder (or anywhere else)
        raise CloudError(409, "bad_info", "No place inside the cloud for this item")
    if not target.exists():
        return target
    stamp = time.strftime("%Y-%m-%d %H%M")
    stem, suffix = (target.stem, target.suffix) if target.suffix and len(target.suffix) <= 10 else (target.name, "")
    for n in range(1, 1000):
        extra = f" (restored {stamp})" if n == 1 else f" (restored {stamp} {n})"
        candidate = target.with_name(f"{stem}{extra}{suffix}")
        if not candidate.exists():
            return candidate
    raise CloudError(409, "exists", "Too many restored copies with this name")


def restore(settings: Settings, trash_id: str) -> dict:
    """Back where it was (its folders made again if they were deleted too); a new item with its name is kept."""
    box = _box(settings, trash_id)
    info = _info(box)
    target = resolve(settings, str(info.get("path") or "")) if info.get("path") else None
    if target is None or target == root(settings):
        raise CloudError(409, "bad_info", "The recycle bin note of this item is damaged: restore it with File Station")
    _make_parents(target.parent)
    target = _free_name(target)
    os.replace(box / "item", target)
    shutil.rmtree(box, ignore_errors=True)
    return {"path": relative(settings, target), "size": int(info.get("size") or 0)}


def purge(settings: Settings, trash_id: str) -> dict:
    """Removed for good."""
    box = _box(settings, trash_id)
    info = _info(box)
    shutil.rmtree(box)
    size = int(info.get("size") or 0)
    _adjust_usage(settings, -size)
    return {"path": str(info.get("path") or "?"), "size": size}


def purge_all(settings: Settings) -> dict:
    count = size = 0
    for item in trash_items(settings):
        try:
            size += purge(settings, item["id"])["size"]
            count += 1
        except (CloudError, OSError):
            pass
    return {"count": count, "size": size}


def purge_expired(settings: Settings) -> list[dict]:
    """Items older than ECHOVR_CLOUD_TRASH_DAYS go for good (checked on every delete and every look at the bin)."""
    if not settings.cloud_trash_days:
        return []
    now, gone = time.time(), []
    for item in trash_items(settings):
        if item["expires_at"] and item["expires_at"] < now:
            try:
                gone.append(purge(settings, item["id"]))
            except (CloudError, OSError):
                pass
    return gone


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


def upload_target(settings: Settings, rel: str | None, name: str, overwrite: bool, folders: bool = False) -> Path:
    """folders: make the missing folders of `rel` first (a file inside an uploaded folder tree)."""
    folder = resolve(settings, rel)
    if folders and not folder.exists():
        _make_parents(folder)
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
    replaced = target.stat().st_size if target.is_file() else 0
    added = part.stat().st_size
    os.replace(part, target)  # same disk (both in the data folder): one step, never half a file
    _adjust_usage(settings, added - replaced)


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

