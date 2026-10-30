from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from sqlalchemy import func, not_, select

from parser import PARSER_VERSION

from ..achievements import RULES
from ..models import Event, Match, Player, Replay
from ..stats import STATS_VERSION
from ..admin_actions import hidden_failure

router = APIRouter(prefix="/api/import", tags=["import"])

STATUSES = ("queued", "processing", "done", "failed")
RATE_WINDOW_MIN = 10


def _stage(key: str, label: str, done: int, total: int | None, detail: str) -> dict:
    return {"key": key, "label": label, "done": done, "total": total, "detail": detail}


@router.get("")
def import_status(request: Request):
    """Import progress, broken down by what each replay produces."""
    worker, scanner = request.app.state.worker, request.app.state.scanner
    since = (datetime.now(timezone.utc) - timedelta(minutes=RATE_WINDOW_MIN)).isoformat(timespec="seconds")
    with request.app.state.sessionmaker() as db:
        # failed replays hidden in the admin console are left out of every count here
        counts = dict(db.execute(select(Replay.status, func.count()).where(not_(hidden_failure()))
                                 .group_by(Replay.status)).all())
        hidden = db.scalar(select(func.count()).select_from(Replay).where(hidden_failure()))
        # queued rows processed before = being redone after an app update or a changed file
        redo = db.scalar(select(func.count()).select_from(Replay)
                         .where(Replay.status == "queued", Replay.parser_version.is_not(None)))
        recent, earliest = db.execute(
            select(func.count(), func.min(Replay.processed_at)).where(Replay.processed_at >= since)).one()
        matches = db.scalar(select(func.count()).select_from(Match))
        with_tracks = db.scalar(select(func.count()).select_from(Match).where(Match.has_tracks))
        players = db.scalar(select(func.count()).select_from(Player))
        events = db.scalar(select(func.count()).select_from(Event))
        by_map = dict(db.execute(select(Match.map, func.count()).group_by(Match.map)).all())
        hour_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(timespec="seconds")
        minute = func.substr(Replay.processed_at, 1, 16)
        per_minute = dict(db.execute(
            select(minute, func.count()).where(Replay.processed_at >= hour_ago).group_by(minute)).all())
        year = func.strftime("%Y", Replay.source_mtime, "unixepoch")
        by_year: dict[str, dict] = {}
        for y, status, n in db.execute(select(year, Replay.status, func.count()).where(not_(hidden_failure()))
                                       .group_by(year, Replay.status)):
            by_year.setdefault(y, {s: 0 for s in STATUSES})[status] = n

    counts = {s: counts.get(s, 0) for s in STATUSES}
    total = sum(counts.values())
    finished = counts["done"] + counts["failed"]
    waiting = counts["queued"] + counts["processing"]
    # rate over the last 10 min, or since processing started if that is more recent (min 1 min)
    window_min = RATE_WINDOW_MIN
    if earliest:
        window_min = max(1.0, (datetime.now(timezone.utc) - datetime.fromisoformat(earliest)).total_seconds() / 60)
    per_min = recent / window_min
    stages = [
        _stage("files", "Replay files found", scanner.state.files, None,
               "Listed from the replay folder (read-only). Recordings still being written are picked up by a later scan."),
        _stage("replays", "Replays read and checked", finished, total,
               f"Each file is unzipped, read frame by frame and checked (Echo Combat, not damaged). {counts['failed']:,} failed."),
        _stage("matches", "Match results and player stats", matches, total,
               "Score, winner, teams, play time, ping, speed, deaths (est.), loadouts, payload push / block."),
        _stage("players", "Players", players, None, "One profile per player ID, combining all of their matches."),
        _stage("events", "Timeline events", events, None,
               "Joins, deaths (est.), respawns, loadout changes, rounds won, checkpoints, contests."),
        _stage("tracks", "Position tracks", with_tracks, matches,
               "2 positions per second per player, saved per match; used by heatmaps and the timeline chart."),
        _stage("heatmaps", "Heatmaps", with_tracks, matches,
               "Drawn from the position tracks when a match or player page is opened."),
        _stage("leaderboard", "Leaderboard", matches, total,
               f"Ranked live from the saved match stats ({players:,} players)."),
        _stage("achievements", "Achievements", matches, total,
               f"{len(RULES)} achievements per player, calculated from the saved match stats when viewed."),
    ]
    return {
        "source_dir": str(request.app.state.settings.source_dir),
        "workers": worker.slots,
        "busy": worker.busy,
        "counts": counts,
        "hidden_failed": hidden,
        "redo": redo,
        "versions": {"parser": PARSER_VERSION, "stats": STATS_VERSION},
        "rate_per_min": round(per_min, 1),
        "eta_min": round(waiting / per_min) if per_min and waiting else None,
        "matches_by_map": by_map,
        "throughput": _minutes(per_minute),
        "by_year": [{"year": y} | counts for y, counts in sorted(by_year.items())],
        "stages": stages,
        "current": worker.current(),
        "scan": asdict(scanner.state),
    }


def _minutes(per_minute: dict[str, int]) -> list[dict]:
    """Replays finished per minute over the last 60 minutes (UTC), zeros included."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    out = []
    for i in range(59, -1, -1):
        label = (now - timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M")
        out.append({"minute": label, "replays": per_minute.get(label, 0)})
    return out
