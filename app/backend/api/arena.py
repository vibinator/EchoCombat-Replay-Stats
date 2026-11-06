"""Mega Prizes tab data (Preview role only; Arena counting is separate from Combat, see arena.py)."""

import time
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from .. import auth
from ..achievements import FULL_GAME_S, MEGA_COMBAT, icon_file
from ..admin_actions import mega_visible, mega_window
from ..duplicates import counted
from ..errors import ApiError
from ..models import (ArenaCounted, ArenaPlayer, Match, MatchPlayer, NakamaAccount, NakamaCombatCounted,
                      NakamaCombatPlayer, Player)

router = APIRouter(prefix="/api/arena", tags=["arena"])
TARGET = 1000  # Mega Prize: Jack Series 11 from Lone Echo 1/2
SEARCH_LIMIT = 10
CLOSEST = 2  # players shown as "closest to the prize"
IMAGES = {name: "image/png" for name in ("d13_front.png", "d13_back.png", "jack_front.png", "jack_back.png")}  # exact names only: nothing from the visitor reaches a path (user, 2026-11-06: front and back of each prize)
IMAGE_DIR = Path(__file__).resolve().parent.parent / "private_assets"


def _require_preview(request: Request) -> None:
    """Who may see the Mega Prizes is set in the Console (\"Visible to\", user, 2026-11-06): Preview role only by default."""
    with request.app.state.sessionmaker() as db:
        allowed = mega_visible(db, auth.has_preview(request))
    if not allowed:
        raise ApiError(403, "no_access", "You do not have access")


@router.get("/visible")
def visible(request: Request):
    """May this visitor see the Mega Prizes? (Console "Visible to".) Its own small answer under /api/arena, which is never shared,
    so /api/challenges stays the same for everyone and can be kept at the edge."""
    with request.app.state.sessionmaker() as db:
        return {"visible": mega_visible(db, auth.has_preview(request))}


@router.get("/image/{name}")
def image(request: Request, name: str):
    """The prize pictures. Not in the public folder: only the Preview role can load them."""
    _require_preview(request)
    if name not in IMAGES:
        raise ApiError(404, "not_found", "Not found")
    return FileResponse(IMAGE_DIR / name, media_type=IMAGES[name])


@router.get("/progress")
def progress(request: Request, limit: int = Query(10, ge=1, le=100)):
    _require_preview(request)
    with request.app.state.sessionmaker() as db:
        rows = db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches >= TARGET)
                         .order_by(ArenaPlayer.matches.desc()).limit(limit)).all()  # only those who reached it (user, 2026-11-04)
        near_arena = db.scalars(select(ArenaPlayer).where(ArenaPlayer.matches < TARGET)
                                .order_by(ArenaPlayer.matches.desc()).limit(CLOSEST)).all()
        combat_target = int(MEGA_COMBAT.levels[-1])
        near_combat = _closest_combat(db, combat_target)
        won_arena = db.scalar(select(func.count()).select_from(ArenaPlayer).where(ArenaPlayer.matches >= TARGET)) or 0
        won_combat = _combat_winners(db, combat_target)
        period = mega_window(db)
        moves = {"top_combat": top_combat(db), "top_arena": top_arena(db)}
    r = MEGA_COMBAT  # kept out of RULES, so no public list or ranking has it
    combat = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r), "estimated": False,
               "new": r.new, "group": r.group, "levels": list(r.levels), "unit": r.unit, "prize": r.prize}]
    today = date.today().isoformat()
    return {"target": TARGET, "min_minutes": 4, "combat": combat,
            # the Mega Prize period (its own dates, or the challenge period): the cards show a live dot while it is running
            "period": {"start": period[0], "end": period[1], "active": bool(period[0]) and period[0] <= today and (not period[1] or today <= period[1])},
            "players": [{"user_id": r.user_id, "name": r.display_name or r.username, "matches": r.matches,
                         "completed": r.matches >= TARGET} for r in rows],
            # the two players nearest to the prize who have not reached it yet (user, 2026-11-04)
            "winners_combat": won_combat, "winners_arena": won_arena,
            **moves,  # the top 10 of each prize with the change over the last day (user, 2026-11-06)
            "closest_combat": near_combat,
            "closest_arena": [{"user_id": a.user_id, "name": a.display_name or a.username, "matches": a.matches} for a in near_arena]}


def _replay_history(db, start: str, end: str | None, accounts: dict[str, object]) -> dict[str, int]:
    """Echo Combat matches from the replay files, per linked replay player (user, 2026-11-06: the Mega Prize now includes the
    replay history, linked by Discord id). Only matches that started BEFORE the Nakama match list began counting (the first
    NakamaCombatCounted row), so a match both sources saw is never counted twice. Same rules as the live count: 4+ minutes
    played, public, 3+ players per team for at least half of the match, inside the Mega Prize period, duplicate recordings left out."""
    if not accounts:
        return {}
    first = db.scalar(select(func.min(NakamaCombatCounted.counted_at)))
    q = (select(Player.user_id, MatchPlayer.match_id).join(MatchPlayer, MatchPlayer.player_id == Player.id)
         .join(Match, Match.id == MatchPlayer.match_id)
         .where(Player.user_id.in_(list(accounts)), counted(MatchPlayer.match_id), MatchPlayer.play_time_s >= FULL_GAME_S,
                Match.private_match.is_(False), Match.started_at >= start))
    if end:
        q = q.where(Match.started_at < (date.fromisoformat(end) + timedelta(days=1)).isoformat())
    if first is not None:
        q = q.where(Match.started_at < datetime.fromtimestamp(first).isoformat(timespec="seconds"))
    rows = [(u, m) for u, m in db.execute(q)]
    match_ids = sorted({m for _, m in rows})
    big: set[int] = set()  # matches with 3+ players per team for at least half of the match
    for i in range(0, len(match_ids), 500):
        chunk = match_ids[i:i + 500]
        sizes = db.execute(select(MatchPlayer.match_id, MatchPlayer.team, func.count()).join(Match, Match.id == MatchPlayer.match_id)
                           .where(MatchPlayer.match_id.in_(chunk), MatchPlayer.play_time_s >= 0.5 * Match.duration_s)
                           .group_by(MatchPlayer.match_id, MatchPlayer.team)).all()
        per: dict[int, dict[str, int]] = {}
        for m, team, n in sizes:
            per.setdefault(m, {})[team] = n
        big |= {m for m, t in per.items() if t.get("blue", 0) >= 3 and t.get("orange", 0) >= 3}
    out: dict[str, int] = {}
    for u, m in rows:
        if m in big:
            out[u] = out.get(u, 0) + 1
    return out


def combat_totals(db, start: str | None, end: str | None, as_of: float | None = None) -> list[dict]:
    """Echo Combat matches per player for the Mega Prize, inside the Mega Prize period, most matches first: the live Nakama
    match list plus (user, 2026-11-06) the replay-file history of the replay player linked to the same account by Discord id
    (see _replay_history; the two never overlap in time). `as_of` (epoch s) counts only what was known by then (for the
    rank change over the last day)."""
    if not start:
        return []
    lo = datetime.fromisoformat(start).timestamp()
    hi = datetime.fromisoformat(end).timestamp() + 86400 if end else None
    if as_of is not None:
        hi = as_of if hi is None else min(hi, as_of)
    n = func.count().label("n")
    q = (select(NakamaCombatCounted.user_id, NakamaCombatPlayer.display_name, NakamaCombatPlayer.username,
                NakamaCombatPlayer.discord_id, n)
         .join(NakamaCombatPlayer, NakamaCombatPlayer.user_id == NakamaCombatCounted.user_id)
         .where(NakamaCombatCounted.counted_at >= lo).group_by(NakamaCombatCounted.user_id))
    if hi:
        q = q.where(NakamaCombatCounted.counted_at < hi)
    totals = {user_id: {"name": display or username, "user_id": user_id, "discord_id": discord_id, "count": count}
              for user_id, display, username, discord_id, count in db.execute(q)}
    # the Nakama account of each linked replay player (the most recently seen one when a player has several)
    accounts: dict[str, object] = {}
    for acc in db.scalars(select(NakamaAccount).where(NakamaAccount.replay_user_id.is_not(None)).order_by(NakamaAccount.last_seen_at)):
        accounts[acc.replay_user_id] = acc
    for replay_user_id, count in _replay_history(db, start, end, accounts).items():
        acc = accounts[replay_user_id]
        entry = totals.setdefault(acc.user_id, {"name": acc.display_name or acc.username, "user_id": acc.user_id,
                                                "discord_id": acc.discord_id, "count": 0})
        entry["count"] += count
    return sorted(totals.values(), key=lambda w: -w["count"])


TOP = 10  # players listed on each Mega Prize card


def _moves(now: list[dict], before: dict[str, int]) -> list[dict]:
    """The top TOP of `now` with the change over the last day: rank_change (+ = climbed, - = dropped, None = new on the list) and
    gained (matches in the last day). `before` = user_id -> matches a day ago."""
    ranked_before = sorted(before.values(), reverse=True)
    out = []
    for i, w in enumerate(now[:TOP], 1):
        was = before.get(w["user_id"], 0)
        rank_before = 1 + sum(1 for c in ranked_before if c > was) if was > 0 else None
        out.append({"user_id": w["user_id"], "name": w["name"], "matches": w["count"], "rank": i,
                    "rank_change": None if rank_before is None else rank_before - i, "gained": w["count"] - was})
    return out


def top_combat(db) -> list[dict]:
    start, end = mega_window(db)
    now = combat_totals(db, start, end)
    day_ago = combat_totals(db, start, end, as_of=time.time() - 86400)
    return _moves(now, {w["user_id"]: w["count"] for w in day_ago})


def top_arena(db) -> list[dict]:
    """Arena only keeps totals, so a day ago = the total minus the matches counted in the last day (ArenaCounted keeps 2 days)."""
    players = db.execute(select(ArenaPlayer.user_id, ArenaPlayer.display_name, ArenaPlayer.username, ArenaPlayer.matches)
                         .order_by(ArenaPlayer.matches.desc())).all()
    recent = dict(db.execute(select(ArenaCounted.user_id, func.count()).where(ArenaCounted.counted_at >= time.time() - 86400)
                             .group_by(ArenaCounted.user_id)).all())
    now = [{"user_id": u, "name": d or un, "count": m} for u, d, un, m in players]
    return _moves(now, {u: m - recent.get(u, 0) for u, _, _, m in players})


def _closest_combat(db, target: int) -> list[dict]:
    """The CLOSEST players below the Combat target."""
    start, end = mega_window(db)
    below = [w for w in combat_totals(db, start, end) if w["count"] < target][:CLOSEST]
    return [{"user_id": w["user_id"], "name": w["name"], "matches": w["count"]} for w in below]


def _combat_winners(db, target: int) -> int:
    """How many players reached the Combat target inside the challenge period."""
    start, end = mega_window(db)
    return sum(1 for w in combat_totals(db, start, end) if w["count"] >= target)


@router.get("/search")
def search(request: Request, q: str = Query("", max_length=60)):
    """Players by name with their progress toward a prize, from the set challenge period on (no start date set = 0).
    Combat and Arena: public matches of 4+ minutes from the live match list. Arena: public matches of 4+ minutes from the live match list."""
    _require_preview(request)
    term = q.strip().lower().replace("%", "").replace("_", "")
    if len(term) < 2:
        return {"target": TARGET, "results": []}
    like = f"%{term}%"
    with request.app.state.sessionmaker() as db:
        start, end = mega_window(db)
        combat = [w for w in combat_totals(db, start, end) if term in (w["name"] or "").lower()][:SEARCH_LIMIT]
        arena = db.scalars(select(ArenaPlayer).where(func.lower(ArenaPlayer.username).like(like)
                                                     | func.lower(func.coalesce(ArenaPlayer.display_name, "")).like(like))
                           .order_by(ArenaPlayer.matches.desc()).limit(SEARCH_LIMIT)).all()
    results = [{"kind": "combat", "name": w["name"], "user_id": w["user_id"], "matches": w["count"]} for w in combat]
    results += [{"kind": "arena", "name": a.display_name or a.username, "user_id": a.user_id, "matches": a.matches} for a in arena]
    return {"target": TARGET, "results": results}
