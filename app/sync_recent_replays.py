"""Keeps a local copy of the most recent replays of each map, so analysis does not read them over the network.

    python app/sync_recent_replays.py [--dry-run]

The source is only ever read. A file is removed only when this script copied it (see MANIFEST) and it has aged out of the
most recent KEEP; anything else in the folder is left alone. If the source is offline or a map lists fewer than KEEP
replays, that map is left as it is. Recency comes from the "[YYYY-MM-DD HH-MM-SS]" in the file name, or else the file's date.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# The share's network address stays out of the repository: a scheduled task that cannot see the mapped drive sets
# ECHOVR_RECENT_REPLAYS_SOURCE to \\<server>\<share>\Replays.
SOURCES = tuple(Path(p) for p in (os.environ.get("ECHOVR_RECENT_REPLAYS_SOURCE"), r"E:\ECRanked\Replays") if p)
LOCAL = Path(__file__).resolve().parents[2] / "ECRanked" / "Replays"
MANIFEST = LOCAL.parent / "recent_replays_manifest.json"  # relative paths this script copied
LOG = LOCAL.parent / "recent_replays_sync.log"  # the last run only
KEEP = 400
SUFFIX = ".echoreplay"
STAMP = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2})\]")


def most_recent(map_dir: Path) -> dict[str, int]:
    """File name -> size of the KEEP most recent replays; every replay when there are fewer."""
    found = []
    with os.scandir(map_dir) as entries:
        for entry in entries:
            if entry.name.endswith(SUFFIX) and entry.is_file():
                stat = entry.stat()
                stamp = STAMP.match(entry.name)
                when = datetime.strptime(stamp.group(1), "%Y-%m-%d %H-%M-%S") if stamp else datetime.fromtimestamp(stat.st_mtime)
                found.append((when, entry.name, stat.st_size))
    found.sort(reverse=True)
    return {name: size for _, name, size in found[:KEEP]}


def sync(dry_run: bool, say) -> int:
    source = next((s for s in SOURCES if s.is_dir()), None)
    if source is None:
        say("source offline: nothing changed")
        return 1
    managed = set(json.loads(MANIFEST.read_text(encoding="utf-8"))) if MANIFEST.exists() else set()
    for map_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        wanted = most_recent(map_dir)
        if len(wanted) < KEEP:
            say(f"{map_dir.name}: only {len(wanted)} replays listed: left as it is")
            continue
        folder = LOCAL / map_dir.name
        added = updated = removed = 0
        for name, size in wanted.items():
            target = folder / name
            key = f"{map_dir.name}/{name}"
            if target.exists():
                if key not in managed or target.stat().st_size == size:
                    continue
                updated += 1  # copied while still being recorded
            else:
                added += 1
                managed.add(key)
            if not dry_run:
                folder.mkdir(parents=True, exist_ok=True)
                part = target.with_name(name + ".part")
                shutil.copy2(map_dir / name, part)
                part.replace(target)
        for key in sorted(k for k in managed if k.startswith(f"{map_dir.name}/") and k.split("/", 1)[1] not in wanted):
            removed += 1
            managed.discard(key)
            if not dry_run:
                (LOCAL / key).unlink(missing_ok=True)
        if not dry_run:  # after each map: a stopped run still knows what it copied
            MANIFEST.write_text(json.dumps(sorted(managed), indent=0), encoding="utf-8")
        say(f"{map_dir.name}: +{added} new, {updated} updated, -{removed} aged out")
    return 0


def main() -> int:
    lines = [f"{datetime.now():%Y-%m-%d %H:%M:%S} sync"]

    def say(text: str) -> None:
        lines.append(text)
        if sys.stdout:  # pythonw has none
            print(text, flush=True)

    dry_run = "--dry-run" in sys.argv
    try:
        code = sync(dry_run, say)
    except OSError as e:  # share gone mid-run: the next run carries on
        say(f"stopped: {e}")
        code = 1
    if not dry_run:
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
