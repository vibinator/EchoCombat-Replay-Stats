"""Home dashboard, archive activity and global search."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import case, func, select

from ..cache import cached
from ..gear import ORDNANCES, TACMODS, WEAPONS
from ..models import Match, MatchPlayer, MatchPlayerLoadout, Player, PlayerAlias, Replay
from .derived import gear, match_summary, period_start, ratio
from .players import games_of

router = APIRouter(tags=["overview"])


@router.get("/api/overview")
def overview(request: Request):
    """Archive totals, today / this week, most-played map, top players this week, latest matches."""
    return cached(request, "overview", (), lambda: _overview(request))


def _overview(request: Request) -> dict:
    today, week = period_start("day"), period_start("week")
    with request.app.state.sessionmaker() as db:
        matches, hours = db.execute(select(func.count(), func.sum(Match.duration_s))).one()
        players = db.scalar(select(func.count()).select_from(Player))
        play_hours = db.scalar(select(func.sum(MatchPlayer.play_time_s)))
        today_n = db.scalar(select(func.count()).select_from(Match).where(Match.started_at >= today))
        week_n = db.scalar(select(func.count()).select_from(Match).where(Match.started_at >= week))
        by_map = dict(db.execute(select(Match.map, func.count()).group_by(Match.map)).all())
        first, last = db.execute(select(func.min(Match.started_at), func.max(Match.started_at))).one()
        won = case((Match.winner == MatchPlayer.team, 1), else_=0)
        top_week = db.execute(
            select(Player.user_id, Player.name, func.count().label("games"), func.sum(won).label("wins"))
            .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id).join(Player)
            .where(Match.started_at >= week).group_by(Player.id)
            .order_by(func.count().desc(), func.sum(won).desc()).limit(5)
        ).all()
        latest = db.scalars(select(Match).order_by(Match.started_at.desc()).limit(8)).all()
        globals_ = _global_stats(db)
    return {
        "global": globals_,
        "matches": matches or 0,
        "players": players or 0,
        "match_hours": round((hours or 0) / 3600, 1),
        "player_hours": round((play_hours or 0) / 3600, 1),
        "today": today_n,
        "this_week": week_n,
        "by_map": by_map,
        "most_played_map": max(by_map, key=by_map.get) if by_map else None,
        "first_match_at": first,
        "last_match_at": last,
        "top_this_week": [{"user_id": u, "name": n, "games": g, "wins": w or 0} for u, n, g, w in top_week],
        "latest": [match_summary(m) for m in latest],
    }


@router.get("/api/overview/processing")
def processing(request: Request):
    """Replays still waiting to be read, for the "processing" spinner in the top bar. Not cached: it is the live queue."""
    with request.app.state.sessionmaker() as db:
        pending = db.scalar(select(func.count()).select_from(Replay).where(Replay.status.in_(("queued", "processing"))))
    return {"pending": pending or 0}


@router.get("/api/overview/activity")
def activity(request: Request, bucket: str = Query("month", pattern="^(day|week|month|year)$")):
    """Matches per period over the whole archive (recorder-local dates), split by map for the stacked chart."""
    return cached(request, "activity", (bucket,), lambda: _activity(request, bucket))


def _activity(request: Request, bucket: str) -> dict:
    expr = {
        "day": func.substr(Match.started_at, 1, 10),
        "week": func.strftime("%Y-%W", Match.started_at),
        "month": func.substr(Match.started_at, 1, 7),
        "year": func.substr(Match.started_at, 1, 4),
    }[bucket]
    with request.app.state.sessionmaker() as db:
        rows = db.execute(
            select(expr.label("period"), Match.map, func.count(), func.sum(Match.duration_s))
            .group_by("period", Match.map).order_by("period")
        ).all()
    items: dict[str, dict] = {}
    for period, map_, n, s in rows:
        item = items.setdefault(period, {"period": period, "matches": 0, "hours": 0.0, "maps": {}})
        item["matches"] += n
        item["hours"] += (s or 0) / 3600
        item["maps"][map_] = n
    for item in items.values():
        item["hours"] = round(item["hours"], 1)
    return {"bucket": bucket, "items": list(items.values())}


@router.get("/api/search")
def search(request: Request, q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=25)):
    """Players by name, plus a match when q is a match id."""
    q = q.strip()
    with request.app.state.sessionmaker() as db:
        games = games_of(Player.id)
        players = db.execute(
            select(Player.user_id, Player.name, games)
            .where(Player.name.ilike(f"%{q}%"), Player.user_id.not_in(select(PlayerAlias.alias_user_id)))  # merged ids (D34)
            .order_by(games.desc()).limit(limit)
        ).all()
        match = db.get(Match, int(q.lstrip("#"))) if q.lstrip("#").isdigit() else None
    return {
        "players": [{"user_id": u, "name": n, "games": g} for u, n, g in players],
        "matches": [match_summary(match)] if match else [],
    }



def _top_gear(db, limit: int = 3) -> dict[str, list[dict]]:
    """Most-used weapons / ordnances / tac mods by time in use (frames / frame rate), empty code excluded.
    One pass over the loadout table, split per slot here."""
    rows = db.execute(
        select(MatchPlayerLoadout.weapon, MatchPlayerLoadout.ordnance, MatchPlayerLoadout.tacmod,
               func.sum(MatchPlayerLoadout.frames / Match.frame_rate_hz))
        .join(Match, Match.id == MatchPlayerLoadout.match_id)
        .group_by(MatchPlayerLoadout.weapon, MatchPlayerLoadout.ordnance, MatchPlayerLoadout.tacmod)
    ).all()
    out = {}
    for i, (key, table) in enumerate((("top_weapons", WEAPONS), ("top_ordnances", ORDNANCES), ("top_tacmods", TACMODS))):
        seconds: dict[str, float] = {}
        for row in rows:
            if row[i] != "":
                seconds[row[i]] = seconds.get(row[i], 0) + (row[3] or 0)
        total = sum(seconds.values())
        ranked = sorted(seconds.items(), key=lambda kv: -kv[1])[:limit]
        out[key] = [gear(code, table) | {"hours": round(s / 3600, 1), "share": ratio(s, total)} for code, s in ranked]
    return out


def _global_stats(db) -> dict:
    """Archive-wide facts for the home page."""
    avg_len, longest_id, longest_s = None, None, None
    n, total_s = db.execute(select(func.count(), func.sum(Match.duration_s))).one()
    if n:
        avg_len = total_s / n
        longest_id, longest_s = db.execute(select(Match.id, Match.duration_s).order_by(Match.duration_s.desc()).limit(1)).one()
    slots = db.scalar(select(func.count()).select_from(MatchPlayer))
    deaths = db.scalar(select(func.sum(MatchPlayer.deaths_est)))
    fastest = db.execute(
        select(Player.user_id, Player.name, MatchPlayer.top_speed, MatchPlayer.match_id).join(Player)
        .order_by(MatchPlayer.top_speed.desc()).limit(1)
    ).first()
    most_active = db.execute(
        select(Player.user_id, Player.name, func.count()).select_from(MatchPlayer).join(Player)
        .group_by(Player.id).order_by(func.count().desc()).limit(1)
    ).first()
    busiest = db.execute(
        select(func.substr(Match.started_at, 1, 10).label("day"), func.count()).group_by("day")
        .order_by(func.count().desc()).limit(1)
    ).first()
    payload = db.execute(
        select(func.count(), func.sum(case((Match.winner == Match.attacking_team, 1), else_=0)))
        .where(Match.mode == "payload", Match.winner.is_not(None), Match.attacking_team.is_not(None))
    ).one()
    capture = dict(db.execute(
        select(Match.winner, func.count()).where(Match.mode == "capture_point", Match.winner.is_not(None))
        .group_by(Match.winner)
    ).all())
    return {
        "recorded_hours": round((total_s or 0) / 3600, 1),
        "avg_match_s": round(avg_len, 1) if avg_len else None,
        "longest_match": {"id": longest_id, "duration_s": longest_s} if longest_id else None,
        "avg_players_per_match": round(slots / n, 1) if n else None,
        "deaths_est": deaths or 0,
        **_top_gear(db),
        "fastest": {"user_id": fastest[0], "name": fastest[1], "top_speed": round(fastest[2], 2), "match_id": fastest[3]}
        if fastest else None,
        "most_active": {"user_id": most_active[0], "name": most_active[1], "games": most_active[2]} if most_active else None,
        "busiest_day": {"day": busiest[0], "matches": busiest[1]} if busiest else None,
        "payload_attack_win_rate": ratio(payload[1], payload[0]),
        "payload_decided": payload[0],
        "capture_wins": {"blue": capture.get("blue", 0), "orange": capture.get("orange", 0)},
    }


RANGES = {"24h": (timedelta(hours=24), "hour"), "7d": (timedelta(days=7), "day"), "30d": (timedelta(days=30), "day")}


@router.get("/api/overview/players-seen")
def players_seen(request: Request, range: str = Query("7d", pattern="^(24h|7d|30d)$"),
                 anchor: str = Query("now", pattern="^(now|latest)$")):
    """Distinct players seen in Combat per hour (24 h) or per day (7 / 30 days), plus the distinct total.
    `anchor=latest` ends the range at the newest recorded match instead of now (the archive may stop earlier)."""
    span, unit = RANGES[range]
    with request.app.state.sessionmaker() as db:
        end = datetime.now()
        if anchor == "latest":
            newest = db.scalar(select(func.max(Match.started_at)))
            if newest:
                end = datetime.fromisoformat(newest)
        start = end - span
        key = func.substr(Match.started_at, 1, 13 if unit == "hour" else 10)
        rows = dict(db.execute(
            select(key.label("bucket"), func.count(func.distinct(MatchPlayer.player_id)))
            .select_from(MatchPlayer).join(Match, Match.id == MatchPlayer.match_id)
            .where(Match.started_at >= start.isoformat(), Match.started_at <= end.isoformat())
            .group_by("bucket")
        ).all())
        unique = db.scalar(
            select(func.count(func.distinct(MatchPlayer.player_id))).select_from(MatchPlayer)
            .join(Match, Match.id == MatchPlayer.match_id)
            .where(Match.started_at >= start.isoformat(), Match.started_at <= end.isoformat())
        )
        matches = db.scalar(select(func.count()).select_from(Match)
                            .where(Match.started_at >= start.isoformat(), Match.started_at <= end.isoformat()))
    # every bucket in the range, zeros included
    step = timedelta(hours=1) if unit == "hour" else timedelta(days=1)
    cursor = start.replace(minute=0, second=0, microsecond=0)
    if unit == "day":
        cursor = cursor.replace(hour=0)
    items = []
    while cursor <= end:
        label = cursor.strftime("%Y-%m-%dT%H") if unit == "hour" else cursor.strftime("%Y-%m-%d")
        items.append({"bucket": label, "players": rows.get(label, 0)})
        cursor += step
    return {"range": range, "unit": unit, "anchor": anchor, "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"), "unique_players": unique, "matches": matches, "items": items}
