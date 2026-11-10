"""Build the 3D tracks (tracks3d.bin) of every processed replay that lacks them, so player / Compare 3D heatmaps cover
the whole archive. Reads each replay once (slow: ~3 h for 29k replays on a many-core PC), writes only tracks3d.bin next to
the existing tracks.bin. Safe to stop (Ctrl+C) and run again: it skips what exists, newest matches first.

    backfill_tracks3d.bat [--workers 4] [--limit N] [--dry-run] [--upgrade]
    backfill_tracks3d.bat --heights      only write the small heights.bin files (what 3D player heatmaps read) of
                                         matches that have 3D tracks but lack one: minutes, no replay is read

Run it where the data folder and the replay share are both reachable (the website's PC / NAS, or a copy of data/processed
that you copy back). Never writes the replay share or the database."""

import argparse
import os
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]

from backend import heatmaps3d, tracks, tracks3d  # noqa: E402
from backend.config import Settings  # noqa: E402


def _low_priority() -> None:
    try:
        if os.name == "nt":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # below normal
        else:
            os.nice(10)
    except Exception:
        pass


def _build(replay_path: str, out_path: str) -> bool:
    return tracks3d.build(replay_path, out_path)


def _heights(tracks_file: str, tracks3d_file: str) -> bool:
    return heatmaps3d.save_heights(Path(tracks_file), Path(tracks3d_file))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) // 2))
    ap.add_argument("--limit", type=int, default=0, help="stop after this many replays (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="only count what is missing")
    ap.add_argument("--upgrade", action="store_true", help="also rebuild files of an older format (before head roll: version 3)")
    ap.add_argument("--heights", action="store_true", help="write the missing heights.bin files instead (fast: reads the track files only)")
    args = ap.parse_args()

    settings = Settings.from_env()
    db = sqlite3.connect(f"file:{settings.db_path.as_posix()}?mode=ro", uri=True)
    rows = db.execute("select id, source_path from replays where status = 'done' order by source_mtime desc").fetchall()
    db.close()
    todo = []
    for rid, source in rows:
        out = tracks3d.tracks3d_path(settings.processed_dir, rid)
        if not out.parent.exists():
            continue  # not processed (no tracks.bin folder)
        if args.heights:
            if out.exists() and not heatmaps3d.heights_path(out).exists():
                todo.append((str(tracks.tracks_path(settings.processed_dir, rid)), str(out)))
        elif not out.exists() or (args.upgrade and (tracks3d.file_version(out) or 0) < tracks3d.FORMAT_VERSION):
            todo.append((str(settings.source_dir / source), str(out)))
    if args.limit:
        todo = todo[: args.limit]
    what = "heights.bin missing" if args.heights else f"missing{' or older format' if args.upgrade else ''}"
    print(f"{len(rows):,} processed replays, {len(todo):,} to build ({what}).")
    if args.dry_run or not todo:
        return 0
    done = failed = 0
    started = time.time()
    with ProcessPoolExecutor(args.workers, initializer=_low_priority) as pool:
        futures = {pool.submit(_heights if args.heights else _build, src, out): src for src, out in todo}
        try:
            for f in as_completed(futures):
                if f.exception() is None and f.result():
                    done += 1
                else:
                    failed += 1
                n = done + failed
                if n % 50 == 0 or n == len(todo):
                    rate = n / (time.time() - started)
                    print(f"{n:,}/{len(todo):,}  ({failed} failed)  {rate:.1f}/s  ~{(len(todo) - n) / rate / 60:.0f} min left", flush=True)
        except KeyboardInterrupt:
            print("Stopping; run again to continue.")
            for f in futures:
                f.cancel()
    print(f"Built {done:,}, failed {failed:,}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
