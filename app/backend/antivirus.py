"""Virus / malware scanning of Open Cloud uploads (user, 2026-11-10: ClamAV on upload, files held until scanned).

ClamAV runs in its own container (docker-compose.yml, service clamav) and keeps its virus list up to date by itself. The
app talks to its daemon (clamd) over TCP: ECHOVR_CLAMAV = "clamav:3310"; empty = scanning off (dev PC, tests).

- A finished upload of at most ECHOVR_CLAMAV_MAX_MB is not moved into the cloud: it waits in <data>/cloud-pending/<id>/
  (item + info.json: where it goes, who sent it) and shows on the Cloud page as "Checking for viruses", not downloadable.
  An older file it replaces stays available until the new one is clean.
- One file at a time is scanned (the NAS keeps its CPU for the site): clamd is asked "SCAN <path>" for the file on the
  shared data folder (mounted read-only into the clamav container at the same path), so the bytes are never sent over the
  network. Clean: moved into place. Virus: moved to <data>/cloud-quarantine/<id>/, which only console users see; they
  delete it or, for a false alarm, release it.
- Scanner down: the files wait and are tried again every RETRY_S; waiting files survive restarts (read again at start).
- Bigger files: clamd would silently stop at its own size limit and answer "OK", so the site never sends them and never
  calls them clean: the Cloud page labels them "Not scanned".
- "Scan all existing files" (Console): every file already in the cloud is scanned where it is; a virus moves it to the
  quarantine the same way.

VirusTotal (ECHOVR_VIRUSTOTAL_KEY, user 2026-11-10): after a file is in the cloud, its SHA-256 fingerprint (worked out on
the NAS; the file itself never leaves) is looked up in the background: results of about 70 engines for files someone has
submitted before. ECHOVR_VIRUSTOTAL_MIN_ENGINES or more calling it malicious: quarantined like a ClamAV find. Not a hold
(the free key allows 4 lookups a minute): paced VT_SPACING_S apart, VT_PER_DAY a UTC day at most; files over VT_MAX_BYTES
are skipped (VirusTotal cannot know them: its own upload limit), which also spares the NAS fingerprinting them.
"""

import hashlib
import json
import logging
import os
import queue
import shutil
import socket
import threading
import time
from pathlib import Path

import httpx

from . import cloud
from .config import Settings

log = logging.getLogger("uvicorn.error")
RETRY_S = 60  # the scanner could not be asked: waiting files are tried again after this
TIMEOUT_S = 15 * 60  # one file's scan at most (a big archive on a slow NAS)
PENDING_ID = cloud.TRASH_ID  # same shape: <UTC time>-<random>


VT_URL = "https://www.virustotal.com/api/v3/files/"
VT_MAX_BYTES = 650 * 1024 * 1024  # VirusTotal's own upload limit: it cannot know bigger files
VT_SPACING_S = 15.0  # free key: 4 lookups a minute
VT_PER_DAY = 480  # free key: 500 a day; a little below


class ScannerDown(Exception):
    pass


def vt_client() -> httpx.Client:
    """Replaced in tests."""
    return httpx.Client(timeout=httpx.Timeout(20, connect=5))


def enabled(settings: Settings) -> bool:
    return bool(settings.clamav_address)


def max_bytes(settings: Settings) -> int:
    return settings.clamav_max_mb * 1024 * 1024


def scannable(settings: Settings, size: int) -> bool:
    return enabled(settings) and size <= max_bytes(settings)


def pending_root(settings: Settings) -> Path:
    path = settings.data_dir / "cloud-pending"
    path.mkdir(parents=True, exist_ok=True)
    return path


def quarantine_root(settings: Settings) -> Path:
    path = settings.data_dir / "cloud-quarantine"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- clamd ------------------------------------------------------------------------------------------

def _ask(settings: Settings, command: str, timeout: float = 10.0) -> str:
    """One clamd command (null-terminated "z" form), its answer without the trailing NUL."""
    host, _, port = settings.clamav_address.rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(port or 3310)), timeout=timeout) as s:
            s.sendall(f"z{command}\0".encode())
            data = b""
            while not data.endswith(b"\0"):
                part = s.recv(4096)
                if not part:
                    break
                data += part
    except (OSError, ValueError) as e:
        raise ScannerDown(f"ClamAV at {settings.clamav_address} cannot be reached: {e}") from None
    return data.rstrip(b"\0").decode("utf-8", "replace").strip()


def scan_file(settings: Settings, path: Path) -> str | None:
    """None = clean; else the virus name. Raises ScannerDown when ClamAV cannot be asked or answers an error."""
    answer = _ask(settings, f"SCAN {path}", timeout=TIMEOUT_S)
    if answer.endswith(" OK"):
        return None
    if answer.endswith(" FOUND"):
        return answer.rsplit(": ", 1)[-1][: -len(" FOUND")].strip() or "unknown"
    raise ScannerDown(f"ClamAV could not scan {path.name}: {answer[:200]}")


def status(settings: Settings) -> dict:
    """For the Console: on / reachable, ClamAV and virus list version."""
    if not enabled(settings):
        return {"enabled": False}
    try:
        version = _ask(settings, "VERSION")
        return {"enabled": True, "reachable": True, "version": version, "max_mb": settings.clamav_max_mb}
    except ScannerDown as e:
        return {"enabled": True, "reachable": False, "error": str(e), "max_mb": settings.clamav_max_mb}


# --- waiting files -------------------------------------------------------------------------------

def _info(box: Path) -> dict:
    try:
        info = json.loads((box / "info.json").read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else {}
    except (OSError, ValueError):
        return {}


def hold(settings: Settings, part: Path, target_rel: str, overwrite: bool, user: dict, size: int) -> str:
    """A finished upload waits for its scan instead of going into the cloud. Returns its id."""
    return cloud.make_box(pending_root(settings), part, {  # appears complete, or not at all (the scanner lists these)
        "path": target_rel, "overwrite": overwrite, "size": size, "uploaded_at": int(time.time()),
        "by_id": user["id"], "by_name": user["name"]})


def pending_in(settings: Settings, folder_rel: str) -> list[dict]:
    """Files waiting for their scan that will go into this cloud folder (the Cloud page lists them as checking)."""
    out = []
    for box in sorted(pending_root(settings).iterdir()):
        info = _info(box)
        path = str(info.get("path") or "")
        if PENDING_ID.match(box.name) and path.rpartition("/")[0] == folder_rel:
            out.append({"name": path.rpartition("/")[2], "size": int(info.get("size") or 0),
                        "modified": int(info.get("uploaded_at") or 0)})
    return out


def pending_count(settings: Settings) -> int:
    return sum(1 for b in pending_root(settings).iterdir() if PENDING_ID.match(b.name))


# --- quarantine (console users) -------------------------------------------------------------------

def quarantine_items(settings: Settings) -> list[dict]:
    items = []
    for box in quarantine_root(settings).iterdir():
        if not PENDING_ID.match(box.name) or not (box / "item").exists():
            continue
        info = _info(box)
        items.append({"id": box.name, "path": str(info.get("path") or "?"), "size": int(info.get("size") or 0),
                      "virus": str(info.get("virus") or "?"), "found_at": int(info.get("found_at") or 0),
                      "by_id": str(info.get("by_id") or ""), "by_name": str(info.get("by_name") or "?")})
    items.sort(key=lambda i: i["id"], reverse=True)
    return items


def _quarantine_box(settings: Settings, qid: str) -> Path:
    if not PENDING_ID.match(qid or ""):
        raise cloud.CloudError(400, "bad_id", "Unknown quarantine item")
    box = quarantine_root(settings) / qid
    if not (box / "item").exists():
        raise cloud.CloudError(404, "not_found", "Not in the quarantine (deleted or released already)")
    return box


def quarantine_delete(settings: Settings, qid: str) -> dict:
    box = _quarantine_box(settings, qid)
    info = _info(box)
    shutil.rmtree(box)
    size = int(info.get("size") or 0)
    cloud._adjust_usage(settings, -size)
    return {"path": str(info.get("path") or "?"), "size": size, "virus": str(info.get("virus") or "?")}


def quarantine_release(settings: Settings, qid: str) -> dict:
    """A false alarm: into the cloud where it was meant to go (a new name if that is taken). A console user's decision."""
    box = _quarantine_box(settings, qid)
    info = _info(box)
    target = cloud.resolve(settings, str(info.get("path") or ""))
    if target == cloud.root(settings):
        raise cloud.CloudError(409, "bad_info", "The quarantine note of this item is damaged")
    cloud._make_parents(target.parent)
    target = cloud._free_name(target)
    os.replace(box / "item", target)
    shutil.rmtree(box, ignore_errors=True)
    return {"path": cloud.relative(settings, target), "size": int(info.get("size") or 0), "virus": str(info.get("virus") or "?")}


def _to_quarantine(settings: Settings, item: Path, info: dict, virus: str) -> str:
    return cloud.make_box(quarantine_root(settings), item, info | {"virus": virus, "found_at": int(time.time())})


# --- the scanning thread ---------------------------------------------------------------------------

class Scanner:
    """One background thread: waiting uploads first, then "scan all existing files" jobs. audit(user, action, path, ok,
    detail, size) writes the cloud audit log (api/cloud.py)."""

    def __init__(self, settings: Settings, audit, after_clean=None):
        self.settings, self.audit = settings, audit
        self.after_clean = after_clean or (lambda rel, user: None)  # VirusTotal's turn (background)
        self.wake = threading.Event()
        self.stop_flag = False
        self.existing: queue.SimpleQueue[str] = queue.SimpleQueue()  # cloud paths to scan where they are
        self.sweep = {"running": False, "done": 0, "total": 0, "found": 0, "by": None}
        self.last_error: str | None = None
        self.thread = threading.Thread(target=self._run, name="antivirus", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_flag = True
        self.wake.set()

    def notify(self):
        self.wake.set()

    def scan_existing(self, user: dict) -> int:
        """Queue every file already in the cloud (scanned where it is, after the waiting uploads)."""
        if self.sweep["running"]:
            return 0
        paths = []
        for folder, _dirs, files in os.walk(cloud.root(self.settings)):
            for name in files:
                full = Path(folder) / name
                if not full.is_symlink():
                    paths.append(cloud.relative(self.settings, full))
        self.sweep = {"running": True, "done": 0, "total": len(paths), "found": 0, "by": user}
        for p in paths:
            self.existing.put(p)
        self.wake.set()
        return len(paths)

    def _run(self):
        while not self.stop_flag:
            try:
                worked = self._one_pending() or self._one_existing()
                self.last_error = None
            except ScannerDown as e:
                if self.last_error != str(e):
                    log.warning("Cloud virus scan waiting: %s", e)
                self.last_error = str(e)
                worked = False
                self.wake.wait(RETRY_S)
                self.wake.clear()
                continue
            except Exception:  # never let the thread die: the files stay where they are
                log.exception("Cloud virus scan failed")
                worked = False
            if not worked:
                self.wake.wait(RETRY_S)
                self.wake.clear()

    def _one_pending(self) -> bool:
        boxes = sorted(b for b in pending_root(self.settings).iterdir() if PENDING_ID.match(b.name))
        if not boxes:
            return False
        box = boxes[0]
        info = _info(box)
        user = {"id": str(info.get("by_id") or ""), "name": str(info.get("by_name") or "?")}
        item = box / "item"
        if not item.exists():
            shutil.rmtree(box, ignore_errors=True)
            return True
        rel = str(info.get("path") or "")
        if not rel.strip("/"):  # no destination (a damaged note): never placed; a console user looks at it
            self._quarantine(box, item, info, "(damaged upload note: not placed)", user, "?")
            return True
        virus = scan_file(self.settings, item)  # ScannerDown: stays waiting
        if virus:
            self._quarantine(box, item, info, virus, user, rel)
            return True
        try:
            target = cloud.resolve(self.settings, rel)
            cloud._make_parents(target.parent)
            if target.is_dir() or (target.exists() and not info.get("overwrite")):
                target = cloud._free_name(target)  # something new took the name while it was checked
            replaced = target.stat().st_size if target.is_file() else 0
            os.replace(item, target)
            cloud._adjust_usage(self.settings, -replaced)  # the waiting file was counted already; the old one is gone
            shutil.rmtree(box, ignore_errors=True)
            placed = cloud.relative(self.settings, target)
            self.audit(user, "scan", placed, True, "no virus found", int(info.get("size") or 0))
            self.after_clean(placed, user)
        except cloud.CloudError as e:  # its folder became a file meanwhile: it waits in the quarantine for a console user
            self._quarantine(box, item, info, f"(not placed: {e.message})", user, rel)
        return True

    def _quarantine(self, box: Path, item: Path, info: dict, virus: str, user: dict, rel: str) -> None:
        _to_quarantine(self.settings, item, info, virus)
        shutil.rmtree(box, ignore_errors=True)
        log.warning("Cloud: virus %s found in %s (uploaded by %s, %s): quarantined", virus, rel, user["name"], user["id"])
        self.audit(user, "virus", rel, False, virus, int(info.get("size") or 0))

    def _one_existing(self) -> bool:
        try:
            rel = self.existing.get_nowait()
        except queue.Empty:
            if self.sweep["running"]:
                self.sweep["running"] = False
                by = self.sweep["by"] or {"id": "", "name": "?"}
                self.audit(by, "scan", "(all existing files)", True,
                           f"{self.sweep['done']} files checked, {self.sweep['found']} with a virus", None)
            return False
        try:
            path = cloud.resolve(self.settings, rel)
        except cloud.CloudError:
            path = None
        if path is not None and path.is_file() and path.stat().st_size <= max_bytes(self.settings) and enabled(self.settings):
            try:
                virus = scan_file(self.settings, path)
            except ScannerDown:
                self.existing.put(rel)  # tried again when the scanner is back
                raise
            if virus:
                info = {"path": rel, "size": path.stat().st_size, "by_id": "", "by_name": "(already in the cloud)"}
                _to_quarantine(self.settings, path, info, virus)
                self.sweep["found"] += 1
                by = self.sweep["by"] or {"id": "", "name": "?"}
                log.warning("Cloud: virus %s found in existing file %s: quarantined", virus, rel)
                self.audit(by, "virus", rel, False, f"{virus} (existing file)", info["size"])
            else:
                self.after_clean(rel, self.sweep["by"] or {"id": "", "name": "?"})
        elif path is not None and path.is_file():
            self.after_clean(rel, self.sweep["by"] or {"id": "", "name": "?"})  # too big for ClamAV / ClamAV off
        self.sweep["done"] += 1
        return True


class VirusTotal:
    """Background fingerprint lookups, paced to the free key's limits. audit as for Scanner."""

    def __init__(self, settings: Settings, audit):
        self.settings, self.audit = settings, audit
        self.jobs: queue.SimpleQueue[tuple[str, dict]] = queue.SimpleQueue()
        self.stop_flag = False
        self.last_call = 0.0
        self.day, self.today = "", 0
        self.checked = self.found = self.unknown = 0
        self.last_error: str | None = None
        self.bad_key = False
        self.thread = threading.Thread(target=self._run, name="virustotal", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_flag = True
        self.jobs.put(("", {}))

    def enqueue(self, rel: str, user: dict) -> None:
        if self.settings.virustotal_key and not self.bad_key:
            self.jobs.put((rel, user))

    def status(self) -> dict:
        if not self.settings.virustotal_key:
            return {"enabled": False}
        return {"enabled": True, "working": not self.bad_key, "queued": self.jobs.qsize(), "today": self.today,
                "per_day": VT_PER_DAY, "checked": self.checked, "found": self.found, "unknown": self.unknown,
                "min_engines": self.settings.virustotal_min_engines, "error": self.last_error}

    def _wait_turn(self) -> None:
        """Spacing between lookups, and the daily cap (waits for the next UTC day)."""
        while not self.stop_flag:
            day = time.strftime("%Y-%m-%d", time.gmtime())
            if day != self.day:
                self.day, self.today = day, 0
            if self.today >= VT_PER_DAY:
                time.sleep(60)
                continue
            gap = self.last_call + VT_SPACING_S - time.monotonic()
            if gap <= 0:
                return
            time.sleep(min(gap, 5))

    def _run(self):
        while not self.stop_flag:
            rel, user = self.jobs.get()
            if self.stop_flag or not rel:
                continue
            try:
                self._check(rel, user)
                if not self.bad_key:  # a refused key stays visible in the Console
                    self.last_error = None
            except Exception as e:  # never let the thread die
                self.last_error = str(e)[:200]
                log.warning("VirusTotal lookup of %s failed: %s", rel, e)

    def _check(self, rel: str, user: dict) -> None:
        try:
            path = cloud.resolve(self.settings, rel)
            st = path.stat()
        except (cloud.CloudError, OSError):
            return  # renamed, deleted or quarantined meanwhile
        if not path.is_file() or st.st_size > VT_MAX_BYTES:
            return
        with open(path, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        for _attempt in range(5):
            self._wait_turn()
            if self.stop_flag:
                return
            self.last_call = time.monotonic()
            self.today += 1
            with vt_client() as client:
                r = client.get(VT_URL + digest, headers={"x-apikey": self.settings.virustotal_key})
            if r.status_code == 429:  # over the key's limit: wait a minute, the same lookup again
                time.sleep(60)
                continue
            if r.status_code in (401, 403):
                self.bad_key = True
                self.last_error = "VirusTotal refused the API key (ECHOVR_VIRUSTOTAL_KEY): lookups stopped"
                log.error(self.last_error)
                return
            break
        else:
            return
        self.checked += 1
        if r.status_code == 404:  # nobody submitted this file to VirusTotal: nothing known about it
            self.unknown += 1
            return
        r.raise_for_status()
        attrs = (r.json().get("data") or {}).get("attributes") or {}
        stats = attrs.get("last_analysis_stats") or {}
        malicious = int(stats.get("malicious") or 0)
        if malicious < self.settings.virustotal_min_engines:
            return
        engines = sum(int(v or 0) for v in stats.values())
        names = sorted({str(v.get("result")) for v in (attrs.get("last_analysis_results") or {}).values()
                        if isinstance(v, dict) and v.get("category") == "malicious" and v.get("result")})
        verdict = f"VirusTotal: {malicious} of {engines} engines" + (f" ({', '.join(names[:3])})" if names else "")
        try:
            now = path.stat()
        except OSError:
            return
        if (now.st_size, now.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
            return  # replaced while it was looked up: the new file gets its own check
        info = {"path": rel, "size": st.st_size, "by_id": user.get("id", ""), "by_name": user.get("name", "?")}
        _to_quarantine(self.settings, path, info, verdict)
        self.found += 1
        log.warning("Cloud: %s flagged by %s: quarantined", rel, verdict)
        self.audit(user, "virus", rel, False, verdict, st.st_size)

