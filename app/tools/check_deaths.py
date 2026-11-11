"""Check the deaths the app counts against each other: the game's kill records (last_kill, recordings from
2026-11-04 on) and the estimate from positions (a player leaving the map), on the same replays. Read-only.

    .venv\\Scripts\\python app\\tools\\check_deaths.py [--per-map 25] [--folder <replays folder>]

For every map: the newest replays of its folder that carry kill records, the deaths by either method, and the matches
where the two are furthest apart. The two should stay within a few percent of each other in total (2026-11-11: +1 to
+6 %); a map or a day where they do not is worth a look (a game update, a changed recorder, wrong bounds).
Default folder: the local copy of recent replays (app/sync_recent_replays.py) when it exists, else the replay source."""

import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]

from backend import stats  # noqa: E402
from backend.config import Settings  # noqa: E402
from parser import open_replay  # noqa: E402

LOCAL = Path(__file__).resolve().parents[3] / "ECRanked" / "Replays"


def deaths_of(path: Path, use_kills: bool) -> tuple[int, int, bool] | None:
    """(deaths counted, of them repeat kills taken from the estimate, the recording has kill records)."""
    replay = open_replay(path)
    seen = []
    real = stats._deaths_from_kills
    stats._deaths_from_kills = lambda events, kills, players: (seen.append(len(kills)), real(events, kills, players))[1]
    try:
        result = stats.compute(replay.meta, replay.frames(), use_kills=use_kills)
    finally:
        stats._deaths_from_kills = real
    deaths = [e for e in result.events if e.type == "death_est"]
    return len(deaths), sum(bool((e.data or {}).get("repeat")) for e in deaths), bool(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--per-map", type=int, default=25, help="replays with kill records to look at per map")
    parser.add_argument("--folder", type=Path, help="folder with one sub-folder of replays per map")
    args = parser.parse_args()
    folder = args.folder or (LOCAL if LOCAL.is_dir() else Settings.from_env().source_dir / "Replays")
    print(f"Replays from {folder}\n")
    print(f"{'map':11s} {'matches':>7s} {'by kills':>9s} {'(repeats)':>9s} {'estimate':>9s} {'estimate vs kills':>18s}   furthest apart (kills / estimate)")
    for map_dir in sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("_")):
        rows = []
        for path in sorted(map_dir.glob("*replay"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(rows) >= args.per_map:
                break
            try:
                by_kills = deaths_of(path, True)
                if not by_kills[2]:
                    continue  # recorded before 2026-11-04: no kill records, nothing to compare
                rows.append((path.name, by_kills[0], by_kills[1], deaths_of(path, False)[0]))
            except Exception as error:  # noqa: BLE001 - an unreadable replay must not stop the check
                print(f"  skipped {path.name}: {type(error).__name__}")
        if not rows:
            print(f"{map_dir.name:11s} no replays with kill records")
            continue
        kills, repeats, estimate = (sum(r[i] for r in rows) for i in (1, 2, 3))
        worst = sorted(rows, key=lambda r: -abs(r[3] - r[1]))[:3]
        apart = ", ".join(f"{k} / {e}" for _, k, _, e in worst)
        print(f"{map_dir.name:11s} {len(rows):7d} {kills:9d} {repeats:9d} {estimate:9d} {(estimate / kills - 1) if kills else 0:+17.1%}   {apart}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
