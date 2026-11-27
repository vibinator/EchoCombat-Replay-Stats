"""Mega Prizes tab data (Preview role only; Arena counting is separate from Combat, see arena.py)."""

import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from .. import aliases, auth
from ..discord_links import main_id
from ..achievements import FULL_GAME_S, MEGA_COMBAT, icon_file
from ..arena import COMBAT_MIN_TEAM
from ..admin_actions import mega_visible, mega_window, window_active
from ..duplicates import counted
from ..errors import ApiError
from ..models import (ArenaCounted, ArenaPlayer, Match, MatchPlayer, NakamaAccount, NakamaCombatCounted,
                      NakamaCombatPlayer, Player)

router = APIRouter(prefix="/api/arena", tags=["arena"])
TARGET = 1000  # Mega Prize: Jack Series 11 from Lone Echo 1/2
# the day Arena counting began (first release with arena.py, 2026.11.04.1): matches counted before 2026-11-25 or so lost
# their dates (pruned after 2 days) and only count for a period that starts on or before this day (arena_totals)
ARENA_FIRST_DAY = "2026-11-04"
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


# The Mega Prize counts are remembered for 10 minutes (user, 2026-11-27: "not super important to be real-time", fewer
# live requests to the NAS the better): counting every player's Combat matches re-reads the replay history and took
# seconds on the NAS. Kept per app (app.state) and keyed on the Mega Prize period, so a period changed in the Console
# shows at once. The role check runs before the cache on every request, so who may see the prizes is never cached.
MEGA_CACHE_S = 600
_MEGA_LOCK = threading.RLock()  # re-entrant: the progress answer asks for the cached totals while counting


def _remember(request: Request, key: tuple, compute):
    """compute() once per MEGA_CACHE_S for this key; one request counts while the others wait for its answer."""
    state = request.app.state
    with _MEGA_LOCK:
        memo = getattr(state, "mega_memo", None)
        if memo is None:
            memo = {}
            state.mega_memo = memo
        hit = memo.get(key)
        if hit is not None and time.monotonic() - hit[0] < MEGA_CACHE_S:
            return hit[1]
        value = compute()
        now = time.monotonic()
        for k in [k for k, (at, _) in memo.items() if now - at >= MEGA_CACHE_S]:
            del memo[k]  # old periods and expired answers: the store stays a few entries
        memo[key] = (now, value)
        return value


def _cached_totals(request: Request, db, start: str | None, end: str | None) -> list[dict]:
    """combat_totals for the period, from the 10-minute cache (shared by the progress, player and search answers)."""
    return _remember(request, ("combat", start, end), lambda: combat_totals(db, start, end))


def _cached_arena(request: Request, db, start: str | None, end: str | None) -> list[dict]:
    """arena_totals for the period, from the same 10-minute cache (keyed on the period, so new dates count at once)."""
    return _remember(request, ("arena", start, end), lambda: arena_totals(db, start, end))


def _bounds(start: str, end: str | None, as_of: float | None) -> tuple[float, float | None]:
    """The Mega Prize period as epoch seconds: from its start (day 00:00, or its start time) to the end of its end day (server time)."""
    lo = datetime.fromisoformat(start).timestamp()
    hi = datetime.fromisoformat(end).timestamp() + 86400 if end else None
    if as_of is not None:
        hi = as_of if hi is None else min(hi, as_of)
    return lo, hi


def arena_totals(db, start: str | None, end: str | None, as_of: float | None = None) -> list[dict]:
    """Public Arena matches per player inside the Mega Prize period, most matches first (user, 2026-11-27: "the number should
    reflect FROM the data picked from the mega prize period"). Counted from the kept (match, player) rows by the time each
    was counted, so changing the period recounts. Arena matches counted before 2026-11-27 had their rows pruned after 2 days,
    so only their per-player total (ArenaPlayer.matches) is left: those undated matches (the total minus the dated rows,
    played from ARENA_FIRST_DAY until the first kept row) are added only when the period covers all of that stretch, i.e. it
    starts on or before ARENA_FIRST_DAY and does not end before the first kept row (user, 2026-11-27).
    `as_of` (epoch s) = only what was known by then (the change over the last day)."""
    if not start:
        return []
    lo, hi = _bounds(start, end, as_of)
    q = select(ArenaCounted.user_id, func.count()).where(ArenaCounted.counted_at >= lo).group_by(ArenaCounted.user_id)
    if hi:
        q = q.where(ArenaCounted.counted_at < hi)
    counts: dict[str, int] = dict(db.execute(q).all())
    first_kept = db.scalar(select(func.min(ArenaCounted.counted_at)))
    if start <= ARENA_FIRST_DAY + "T00:00" and (hi is None or first_kept is None or hi >= first_kept):
        dated = select(ArenaCounted.user_id, func.count().label("n")).group_by(ArenaCounted.user_id).subquery()
        old = db.execute(select(ArenaPlayer.user_id, ArenaPlayer.matches - func.coalesce(dated.c.n, 0))
                         .outerjoin(dated, dated.c.user_id == ArenaPlayer.user_id)
                         .where(ArenaPlayer.matches > func.coalesce(dated.c.n, 0)))
        for user_id, n in old:
            counts[user_id] = counts.get(user_id, 0) + n
    if not counts:
        return []
    info = {u: (display, username, discord_id) for u, display, username, discord_id in db.execute(
        select(ArenaPlayer.user_id, ArenaPlayer.display_name, ArenaPlayer.username, ArenaPlayer.discord_id)
        .where(ArenaPlayer.user_id.in_(list(counts))))}
    rows = [{"name": info[u][0] or info[u][1], "username": info[u][1], "user_id": u, "discord_id": info[u][2], "count": n}
            for u, n in counts.items() if u in info]
    return sorted(rows, key=lambda w: -w["count"])


@router.get("/progress")
def progress(request: Request, limit: int = Query(10, ge=1, le=100)):
    _require_preview(request)
    with request.app.state.sessionmaker() as db:
        period = mega_window(db)
        return _remember(request, ("progress", limit, *period), lambda: _progress(request, db, limit, period))


def _progress(request: Request, db, limit: int, period: tuple) -> dict:
    """The body of /progress, counted at most every MEGA_CACHE_S."""
    arena = _cached_arena(request, db, *period)  # inside the Mega Prize period only (user, 2026-11-27)
    rows = [w for w in arena if w["count"] >= TARGET][:limit]  # only those who reached it (user, 2026-11-04)
    near_arena = [w for w in arena if w["count"] < TARGET][:CLOSEST]
    combat_target = int(MEGA_COMBAT.levels[-1])
    # the Combat totals once, shared by the top 10, the closest and the winners (user, 2026-11-27: Mega Prizes slow to
    # load; this was counted 4 times per request, each time re-reading the replay history)
    totals = _cached_totals(request, db, *period)
    near_combat = _closest_combat(totals, combat_target)
    won_arena = sum(1 for w in arena if w["count"] >= TARGET)
    won_combat = _combat_winners(totals, combat_target)
    moves = {"top_combat": top_combat(db, totals), "top_arena": top_arena(db, arena)}
    r = MEGA_COMBAT  # kept out of RULES, so no public list or ranking has it
    combat = [{"id": r.id, "name": r.name, "description": r.description, "period": r.period, "icon": icon_file(r), "estimated": False,
               "new": r.new, "group": r.group, "levels": list(r.levels), "unit": r.unit, "prize": r.prize}]
    return {"target": TARGET, "min_minutes": 4, "combat": combat,
            # the Mega Prize period (its own dates, or the challenge period): the cards show a live dot while it is running
            "period": {"start": period[0], "end": period[1], "active": window_active(period)},
            "players": [{"user_id": w["user_id"], "name": w["name"], "matches": w["count"], "completed": True} for w in rows],
            # the two players nearest to the prize who have not reached it yet (user, 2026-11-04)
            "winners_combat": won_combat, "winners_arena": won_arena,
            **moves,  # the top 10 of each prize with the change over the last day (user, 2026-11-06)
            "closest_combat": near_combat,
            "closest_arena": [{"user_id": w["user_id"], "name": w["name"], "matches": w["count"]} for w in near_arena]}


def _replay_history(db, start: str, end: str | None, accounts: dict[str, object]) -> dict[str, int]:
    """Echo Combat matches from the replay files, per linked replay player (user, 2026-11-06: the Mega Prize now includes the
    replay history, linked by Discord id). Only matches that started BEFORE the Nakama match list began counting (the first
    NakamaCombatCounted row), so a match both sources saw is never counted twice. Same rules as the live count: 4+ minutes
    played, public, 2+ players per team for at least half of the match (user, 2026-11-27: was 3+), inside the Mega Prize period, duplicate recordings left out."""
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
    big: set[int] = set()  # matches with COMBAT_MIN_TEAM+ players per team for at least half of the match
    for i in range(0, len(match_ids), 500):
        chunk = match_ids[i:i + 500]
        sizes = db.execute(select(MatchPlayer.match_id, MatchPlayer.team, func.count()).join(Match, Match.id == MatchPlayer.match_id)
                           .where(MatchPlayer.match_id.in_(chunk), MatchPlayer.play_time_s >= 0.5 * Match.duration_s)
                           .group_by(MatchPlayer.match_id, MatchPlayer.team)).all()
        per: dict[int, dict[str, int]] = {}
        for m, team, n in sizes:
            per.setdefault(m, {})[team] = n
        big |= {m for m, t in per.items() if t.get("blue", 0) >= COMBAT_MIN_TEAM and t.get("orange", 0) >= COMBAT_MIN_TEAM}
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
    lo, hi = _bounds(start, end, as_of)
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


def top_combat(db, now: list[dict] | None = None) -> list[dict]:
    """`now` = combat_totals for the current period when the caller already has it."""
    start, end = mega_window(db)
    if now is None:
        now = combat_totals(db, start, end)
    day_ago = combat_totals(db, start, end, as_of=time.time() - 86400)
    return _moves(now, {w["user_id"]: w["count"] for w in day_ago})


def top_arena(db, now: list[dict] | None = None) -> list[dict]:
    """`now` = arena_totals for the current period when the caller already has it; a day ago is counted the same way."""
    start, end = mega_window(db)
    if now is None:
        now = arena_totals(db, start, end)
    day_ago = arena_totals(db, start, end, as_of=time.time() - 86400)
    return _moves(now, {w["user_id"]: w["count"] for w in day_ago})


def _closest_combat(totals: list[dict], target: int) -> list[dict]:
    """The CLOSEST players below the Combat target (`totals` = combat_totals, most matches first)."""
    below = [w for w in totals if w["count"] < target][:CLOSEST]
    return [{"user_id": w["user_id"], "name": w["name"], "matches": w["count"]} for w in below]


def _combat_winners(totals: list[dict], target: int) -> int:
    """How many players reached the Combat target inside the challenge period (`totals` = combat_totals)."""
    return sum(1 for w in totals if w["count"] >= target)


def _period(db) -> dict:
    start, end = mega_window(db)
    return {"start": start, "end": end, "active": window_active((start, end))}


@router.get("/player/{user_id}")
def player(request: Request, user_id: str):
    """One player's own progress toward each Mega Prize, for their profile (user, 2026-11-26: personal progress only, no ranking
    or other players). `user_id` = the replay player. Combat: every Nakama account linked to them (NakamaAccount.replay_user_id;
    combat_totals already adds their replay-file history to one of those). Arena: those accounts, plus Arena rows carrying their
    Discord id (a recent replay player's id IS the Discord id). No Discord id or Nakama id is sent back."""
    _require_preview(request)
    if len(user_id) > 64:
        raise ApiError(404, "not_found", "Not found")
    with request.app.state.sessionmaker() as db:
        start, end = mega_window(db)
        # every id merged into the player (user, 2026-11-27: echofox's page, 341, showed 0: their account on the match list
        # is linked to the Discord-id player merged into it, not to 341 itself)
        own = aliases.ids_of(db, main_id(db, user_id))
        accounts = db.scalars(select(NakamaAccount).where(NakamaAccount.replay_user_id.in_(own))).all()
        ids = {a.user_id for a in accounts}
        discords = {a.discord_id for a in accounts if a.discord_id} | own
        combat = sum(w["count"] for w in _cached_totals(request, db, start, end) if w["user_id"] in ids) if ids else 0
        arena_ids = set(db.scalars(select(ArenaPlayer.user_id).where(ArenaPlayer.user_id.in_(ids) | ArenaPlayer.discord_id.in_(discords))))
        arena = sum(w["count"] for w in _cached_arena(request, db, start, end) if w["user_id"] in arena_ids) if arena_ids else 0
        period = _period(db)
    combat_target = int(MEGA_COMBAT.levels[-1])
    return {"period": period, "linked": bool(ids or arena_ids),
            "combat": {"matches": combat, "target": combat_target, "prize": MEGA_COMBAT.prize},
            "arena": {"matches": arena, "target": TARGET, "prize": "Jack Series 11 from Lone Echo 1/2"}}


@router.get("/search")
def search(request: Request, q: str = Query("", max_length=60)):
    """Players by name with their progress toward a prize, from the set challenge period on (no start date set = 0).
    Combat and Arena: public matches of 4+ minutes from the live match list, inside the Mega Prize period."""
    _require_preview(request)
    term = q.strip().lower().replace("%", "").replace("_", "")
    if len(term) < 2:
        return {"target": TARGET, "results": []}
    with request.app.state.sessionmaker() as db:
        start, end = mega_window(db)
        combat = [w for w in _cached_totals(request, db, start, end) if term in (w["name"] or "").lower()][:SEARCH_LIMIT]
        arena = [w for w in _cached_arena(request, db, start, end)
                 if term in (w["name"] or "").lower() or term in (w["username"] or "").lower()][:SEARCH_LIMIT]
    results = [{"kind": "combat", "name": w["name"], "user_id": w["user_id"], "matches": w["count"]} for w in combat]
    results += [{"kind": "arena", "name": w["name"], "user_id": w["user_id"], "matches": w["count"]} for w in arena]
    return {"target": TARGET, "results": results}
