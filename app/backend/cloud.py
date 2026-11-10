"""Open Cloud (user, 2026-11-10): file storage on the website for Discord members with the Cloud permission. Two
levels (Permissions page): Cloud view = list and download, Cloud edit = also upload, new folder, rename, delete.
Console users have both.

Files live in <data>/cloud on the NAS (kept across app updates like the database), never in the replay share.
Uploads arrive in chunks (Cloudflare refuses request bodies over 100 MB on its free plan): each chunk is appended
to <data>/cloud-uploads/<user>-<upload id>.part, and the finished file is moved into place in one step, so a
half-uploaded file never shows in the list. Parts nobody finished are deleted after a day.

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
STALE_PART_S = 24 * 3600
USAGE_S = 60  # the "used" total is recounted at most this often (walking the folder is slow on the NAS)
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")
BAD_CHARS = re.compile(r'[\x00-\x1f\x7f/\\<>:"|?*]')  # also the characters Windows refuses (tests, a copy to a PC)
WINDOWS_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}

_usage: dict[str, tuple[float, int]] = {}  # cloud folder -> (counted at, bytes)
_usage_lock = threading.Lock()


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
    total = 0
    for folder, _dirs, files in os.walk(key):
        for f in files:
            try:
                total += os.stat(os.path.join(folder, f)).st_size
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
    for item in folder.iterdir():
        try:
            st = item.stat()
        except OSError:
            continue
        is_dir = item.is_dir()
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


def part_path(settings: Settings, user_id: str, upload_id: str) -> Path:
    """The parts are per person: nobody can append to someone else's upload."""
    if not UPLOAD_ID.match(upload_id or "") or not user_id.isdigit():
        raise CloudError(400, "bad_upload", "Bad upload id")
    return uploads(settings) / f"{user_id}-{upload_id}.part"


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
    """First chunk: room for the whole file (quota and free disk), then an empty part file."""
    _clean_stale_parts(settings)
    if total < 0:
        raise CloudError(400, "bad_upload", "Bad file size")
    replaced = target.stat().st_size if overwrite and target.is_file() else 0
    quota = quota_bytes(settings)
    if quota and used_bytes(settings) - replaced + total > quota:
        free = max(quota - used_bytes(settings) + replaced, 0)
        raise CloudError(413, "quota", f"Not enough cloud space: {free / 1024**3:.1f} GB left of {quota / 1024**3:.0f} GB")
    if shutil.disk_usage(uploads(settings)).free - total < RESERVE_BYTES:
        raise CloudError(507, "disk_full", "The server's disk is almost full")
    part.write_bytes(b"")


def finish_upload(settings: Settings, part: Path, target: Path) -> None:
    os.replace(part, target)  # same disk (both in the data folder): one step, never half a file
    _forget_usage()
