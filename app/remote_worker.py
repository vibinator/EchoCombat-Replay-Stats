"""Reads replays for the website on this PC instead of on the NAS (remote.py; start it with remote_worker.bat).

Needs: the same app version as the website (the parser and stats must match), the replay share reachable from this PC,
and "Process replays on another PC" switched on in the Console (otherwise it waits). The PC asks the website for queued
replays, reads each file from the share, parses it here (all cores but two), and sends the finished result back. Nothing
is written to the PC besides temporary files; the website's database is only ever changed by the website itself.

Settings (settings.local.bat or arguments): ECHOVR_REMOTE_SERVER (https://echocombat.com, or the NAS's own address on the
home network, http://<nas>:8000), ECHOVR_REMOTE_WORKER_SECRET (the same value as on the NAS), ECHOVR_REPLAY_SOURCE
(the replay share as this PC sees it)."""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend import remote  # noqa: E402
from backend.config import DEFAULT_SOURCE  # noqa: E402
from backend.stats import STATS_VERSION  # noqa: E402
from backend.worker import _pool_process_start, analyse  # noqa: E402
from parser import PARSER_VERSION  # noqa: E402

USER_AGENT = "EchoVR-RemoteWorker/1"
IDLE_S = 10  # nothing queued: ask again after this
OFF_S = 20  # remote processing is off on the server
ERROR_S = 30  # the server did not answer
MISSING_S = 60  # a replay file is not where the server says: share not connected?


class Fatal(Exception):
    """Stop with this message (wrong secret, other app version)."""


@dataclass
class Job:
    id: int
    path: Path
    folder: Path
    started: float


class Server:
    def __init__(self, base: str, secret: str):
        self.base, self.secret = base.rstrip("/"), secret

    def post(self, path: str, body: bytes, content_type: str = "application/json", timeout: float = 180) -> dict:
        request = urllib.request.Request(self.base + path, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.secret}", "Content-Type": content_type, "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                return json.loads(reply.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read())
            except Exception:  # noqa: BLE001 - not our JSON (a Cloudflare error page)
                detail = {}
            code, message = detail.get("error_code", ""), detail.get("message", f"HTTP {e.code}")
            if e.code in (401, 404) and code in ("bad_worker_secret", "remote_worker_disabled"):
                raise Fatal(message) from e
            if e.code == 409 and code == "version_mismatch":
                raise Fatal(message) from e
            if (e.code == 404 and not code) or (e.code == 405 and code == "read_only"):  # an older website: no such address
                raise Fatal("This website does not offer remote processing (an older version, or ECHOVR_REMOTE_WORKER_SECRET is "
                            "not set on the NAS). Update / set it, then start this again.") from e
            if e.code in (403, 1010) and not code:  # a Cloudflare page, not the website's own answer
                raise Fatal(f"The request was refused before it reached the website (HTTP {e.code}, probably Cloudflare's bot "
                            "protection). Use the NAS's home-network address as ECHOVR_REMOTE_SERVER (http://<nas>:8000).") from e
            raise Rejected(e.code, code, message) from e

    def claim(self, count: int) -> dict:
        return self.post("/api/worker/claim", json.dumps(
            {"count": count, "parser_version": PARSER_VERSION, "stats_version": STATS_VERSION}).encode())

    def release(self, ids: list[int]) -> None:
        if ids:
            self.post("/api/worker/release", json.dumps({"ids": ids}).encode(), timeout=30)

    def result(self, replay_id: int, body: bytes) -> dict:
        return self.post(f"/api/worker/result/{replay_id}", body, "application/octet-stream")


class Rejected(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def say(text: str) -> None:
    print(time.strftime("%H:%M:%S"), text, flush=True)


def read_files(job: Job) -> tuple[bytes, bytes]:
    out = []
    for name in ("tracks.bin", "tracks3d.bin"):
        file = job.folder / name
        out.append(file.read_bytes() if file.is_file() else b"")
    return out[0], out[1]


def send(server: Server, job: Job, outcome: tuple) -> str:
    """Uploads one result (three tries); returns what to show."""
    tracks, tracks3d = read_files(job) if outcome[0] == "ok" else (b"", b"")
    body = remote.pack(outcome, tracks, tracks3d)
    for attempt in range(3):
        try:
            server.result(job.id, body)
            return "saved"
        except Rejected as e:
            if e.code == "not_claimed":
                return "dropped (the server has it queued again)"
            if e.code in ("bad_result", "too_big"):
                # the server will not take this one: say so there, so it is marked failed instead of coming back forever
                body = remote.pack(("failed", "internal", f"The remote PC's result was refused: {e}"), b"", b"")
                continue
            if attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))
    raise OSError("upload failed")


def run(server: Server, source: Path, workers: int, uploaders: int) -> None:
    """Parsing (process pool), claiming (main loop) and uploading (threads) overlap, so the cores never wait for the network.
    Up to 2 x workers replays are claimed ahead, and claimed again as soon as the cores are about to run dry."""
    tmp = Path(tempfile.mkdtemp(prefix="echovr-remote-"))
    pool = ProcessPoolExecutor(workers, initializer=_pool_process_start)
    senders = ThreadPoolExecutor(uploaders, thread_name_prefix="upload")
    jobs: dict[Future, Job] = {}  # being read in the pool
    uploads: dict[Future, tuple[Job, tuple]] = {}  # read, being sent
    done_n = failed_n = 0
    started = time.monotonic()
    next_claim, last_note = 0.0, ""
    spent = {"parse": 0.0, "send": 0.0, "claim": 0.0}
    window = workers * 2

    def note(text: str) -> None:
        nonlocal last_note
        if text != last_note:
            say(text)
            last_note = text

    def give_back(ids: list[int]) -> None:
        try:
            server.release(ids)
        except Exception as e:  # noqa: BLE001 - the server takes them back after 30 minutes anyway
            say(f"Could not give {len(ids)} replay(s) back ({e}); the server queues them again by itself.")

    def upload(job: Job, outcome: tuple) -> str:
        t = time.monotonic()
        try:
            return send(server, job, outcome)
        finally:
            spent["send"] += time.monotonic() - t
            shutil.rmtree(job.folder, ignore_errors=True)

    try:
        while True:
            if len(jobs) <= workers and time.monotonic() >= next_claim:
                t = time.monotonic()
                try:
                    reply = server.claim(min(32, window - len(jobs)))  # 32 = the server's MAX_CLAIM per request
                except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, Rejected) as e:
                    note(f"The server did not answer ({e}); trying again in {ERROR_S} s")
                    next_claim = time.monotonic() + ERROR_S
                    reply = None
                spent["claim"] += time.monotonic() - t
                if reply is not None:
                    if not reply["enabled"]:
                        note("Remote processing is OFF on the server (Console: Process replays on another PC). Waiting...")
                        next_claim = time.monotonic() + OFF_S
                    elif not reply["jobs"]:
                        note("Nothing queued. Waiting for new replays...")
                        next_claim = time.monotonic() + IDLE_S
                    else:
                        last_note = ""
                        missing = []
                        for item in reply["jobs"]:
                            path = source / item["path"]
                            if not path.is_file():
                                missing.append(item["id"])
                                continue
                            folder = tmp / str(item["id"])
                            folder.mkdir(parents=True, exist_ok=True)
                            future = pool.submit(analyse, str(path), str(folder / "tracks.bin"), item["repair"])
                            jobs[future] = Job(item["id"], path, folder, time.monotonic())
                        if missing:
                            give_back(missing)
                            say(f"{len(missing)} replay(s) are not at {source}: is the replay share connected on this PC? "
                                f"(e.g. {reply['jobs'][0]['path']}). Given back; trying again in {MISSING_S} s.")
                            next_claim = time.monotonic() + MISSING_S
            if not jobs and not uploads:
                time.sleep(1)
                continue
            finished, _ = wait(list(jobs) + list(uploads), timeout=1, return_when=FIRST_COMPLETED)
            for future in finished:
                if future in jobs:
                    job = jobs.pop(future)
                    spent["parse"] += time.monotonic() - job.started
                    try:
                        outcome = future.result()
                    except BrokenProcessPool:
                        # a replay killed a process: start a new pool; everything being read goes back to the server
                        give_back([job.id] + [j.id for j in jobs.values()])
                        say("A reader process died (a damaged or huge replay?). Starting again with a new pool.")
                        jobs.clear()
                        pool.shutdown(wait=False, cancel_futures=True)
                        pool = ProcessPoolExecutor(workers, initializer=_pool_process_start)
                        break
                    uploads[senders.submit(upload, job, outcome)] = (job, outcome)
                    continue
                job, outcome = uploads.pop(future)
                try:
                    what = future.result()
                except Fatal:
                    raise
                except Exception as e:  # noqa: BLE001
                    give_back([job.id])
                    say(f"Could not send replay {job.id} ({e}); given back.")
                    continue
                if outcome[0] == "ok":
                    done_n += 1
                else:
                    failed_n += 1
                total = done_n + failed_n
                if what != "saved" or total % 10 == 0 or outcome[0] != "ok":
                    minutes = max((time.monotonic() - started) / 60, 1e-9)
                    say(f"Replay {job.id} {job.path.name}: {outcome[0] if outcome[0] != 'ok' else 'read'}, {what}"
                        + (f" ({outcome[1]})" if outcome[0] != "ok" else "")
                        + f"  |  {done_n} read, {failed_n} failed, {total / minutes:.1f}/min"
                        + f"  |  avg s/replay: read {spent['parse'] / total:.1f}, send {spent['send'] / total:.1f}, "
                          f"claim {spent['claim'] / total:.2f}  |  reading {len(jobs)}, sending {len(uploads)}")
    except (KeyboardInterrupt, Fatal):
        raise
    finally:
        ids = [j.id for j in jobs.values()] + [j.id for j, _ in uploads.values()]
        for process in list(getattr(pool, "_processes", {}).values()):
            process.terminate()  # they were told to ignore Ctrl+C; whatever they were reading goes back to the queue
        pool.shutdown(wait=False, cancel_futures=True)
        senders.shutdown(wait=False, cancel_futures=True)
        if ids:
            give_back(ids)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    env = os.environ.get
    parser = argparse.ArgumentParser(description="Read replays for the website on this PC (see docs/Setup.MD, Remote processing).")
    parser.add_argument("--server", default=env("ECHOVR_REMOTE_SERVER", "https://echocombat.com"), help="the website's address")
    parser.add_argument("--secret", default=env("ECHOVR_REMOTE_WORKER_SECRET", ""), help="same as ECHOVR_REMOTE_WORKER_SECRET on the NAS")
    parser.add_argument("--source", default=env("ECHOVR_REPLAY_SOURCE", DEFAULT_SOURCE), help="the replay share as this PC sees it")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2), help="parallel readers (default: all cores but two)")
    parser.add_argument("--uploads", type=int, default=6, help="results sent at the same time (default: 6)")
    args = parser.parse_args(argv)
    if not args.secret or args.secret.startswith("YOUR_"):
        print("No secret: set ECHOVR_REMOTE_WORKER_SECRET in settings.local.bat (the same value as on the NAS).", file=sys.stderr)
        return 2
    source = Path(args.source)
    if not source.is_dir():
        print(f"The replay folder {source} is not reachable from this PC. Connect the share, or set ECHOVR_REPLAY_SOURCE.", file=sys.stderr)
        return 2
    say(f"Reading replays for {args.server} from {source} with {args.workers} process(es). Ctrl+C stops (unfinished replays go back).")
    try:
        run(Server(args.server, args.secret), source, args.workers, max(1, args.uploads))
    except KeyboardInterrupt:
        say("Stopped.")
    except Fatal as e:
        print(f"! {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
