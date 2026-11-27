"""Public player-stats API, v1 (user, 2026-11-27): for people and bots an admin gave a key (Console > API keys,
or admin.bat api-key-add). Profile stats only: the numbers on a player's page, no heatmaps, bios, Discord ids, pings
or match-by-match data; stats hidden from players stay hidden. Docs: docs/API.MD.

The key goes in `Authorization: Bearer <key>`, `X-API-Key: <key>` or `?key=<key>` (a URL that works on its own; it ends
up in browser histories and logs, so the header is better for scripts). Each key may ask 30 times a minute (bursts up
to 60) and 1,000 times an hour, on top of the site's own limit per address (guard.py). The answers are never kept by
Cloudflare or browsers (middleware.py PER_VISITOR), so a revoked key stops working at once."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from .. import api_keys, visibility
from ..cache import cached
from .derived import MAP_PATTERN, PERIODS, TEXT_MAX
from .players import _get_player, _search_players

router = APIRouter(prefix="/api/v1", tags=["public"])

# what a player's stats share (players._profile); hidden win-loss stats are already left out by _get_player
STATS = ("games", "counted_games", "decided_games", "wins", "losses", "games_by_map", "games_by_mode", "hours_played",
         "deaths_est", "deaths_per_game_est", "avg_speed", "top_speed", "pct_stopped", "pct_upside_down", "pct_near_mate",
         "pct_near_enemy", "pct_left_early", "dominant_arm", "pct_left_arm", "payload_push_s", "payload_block_s", "emote_count")
PLAYER = ("user_id", "name", "level", "first_seen_at", "last_seen_at", "period", "map")
LISTED = ("user_id", "name", "games", "hours_played", "last_seen_at")


def _refuse(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error_code": code, "message": message}, status_code=status, headers=headers)


def _presented(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or request.query_params.get("key") or "").strip()


def _check(request: Request) -> JSONResponse | None:
    """None = a live key with requests left; otherwise the refusal."""
    presented = _presented(request)
    if not presented:
        return _refuse(401, "api_key_missing", "This API needs a key: Authorization: Bearer <key>, X-API-Key or ?key=. "
                                               "Ask an admin of the site for one.")
    key = api_keys.find(request.app.state.sessionmaker, presented)
    if key is None:
        return _refuse(401, "bad_api_key", "Unknown or revoked API key")
    if wait := api_keys.wait_for(key["id"]):
        return _refuse(429, "rate_limited", f"Too many requests for this key ({api_keys.PER_MIN} a minute, "
                                            f"{api_keys.PER_HOUR} an hour). Wait a moment and try again.",
                       {"Retry-After": str(max(1, round(wait)))})
    api_keys.touch(request.app.state.sessionmaker, key["id"])
    return None


@router.get("/players")
def find_players(request: Request, q: str = Query("", max_length=TEXT_MAX), limit: int = Query(20, ge=1, le=50),
                 offset: int = Query(0, ge=0)):
    """Players whose name contains `q` (all players without it), most recently seen first."""
    if refusal := _check(request):
        return refusal
    q = q.strip()
    found = cached(request, "api_v1_players", (q, limit, offset), lambda: _search_players(request, q, limit, offset))
    return {"items": [{k: p.get(k) for k in LISTED} for p in found["items"]], "total": found["total"], "limit": limit, "offset": offset}


@router.get("/players/{user_id}")
def player_stats(request: Request, user_id: str, period: str = Query("all", pattern="^(" + "|".join(PERIODS) + ")$"),
                 map: str | None = Query(None, pattern=MAP_PATTERN)):
    """One player's profile stats for a period and map. A merged id answers with its main player (see `user_id`)."""
    if refusal := _check(request):
        return refusal
    v = visibility.public(request.app.state.sessionmaker)  # always the public view: hidden stats stay hidden
    p = cached(request, "api_v1_player", (user_id, period, map, v), lambda: _get_player(request, user_id, period, map, v))
    return {**{k: p.get(k) for k in PLAYER}, "stats": {k: p["stats"][k] for k in STATS if k in p["stats"]}}


_schema: dict = {}


@router.get("/openapi.json", include_in_schema=False)
def openapi(request: Request):
    """The API listed as JSON (OpenAPI 3; user, 2026-11-27): only these endpoints, never the site's own. No key needed."""
    if not _schema:
        from fastapi.openapi.utils import get_openapi
        schema = get_openapi(title="Echo Combat Stats: player stats API", version="1",
                             description="Profile stats of Echo Combat players. Every call needs an API key from an admin "
                                         f"of the site: Authorization: Bearer <key> (or X-API-Key, or ?key=). "
                                         f"{api_keys.PER_MIN} requests a minute and {api_keys.PER_HOUR} an hour per key.",
                             routes=[r for r in router.routes if getattr(r, "include_in_schema", True)],
                             servers=[{"url": request.app.state.settings.public_url.rstrip("/")}])
        schema.setdefault("components", {})["securitySchemes"] = {
            "bearer": {"type": "http", "scheme": "bearer"},
            "header": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "query": {"type": "apiKey", "in": "query", "name": "key"},
        }
        schema["security"] = [{"bearer": []}, {"header": []}, {"query": []}]
        _schema.update(schema)
    return _schema
