"""Small Discord pictures for the name lists (user, 2026-11-06): Players, Leaderboard, Achievements.

GET /api/avatars?ids=<player id>,<player id>... (at most MAX_IDS) -> {player id: picture URL}, only for players who have one.
- It is its own request, never part of the cached list answers, so a player who switches their picture off in their profile
  disappears at once (Cache-Control: private, short).
- No Discord request per row: the pictures come from the server member list the site already reads in the background
  (discord_names.py). A player's Discord account is found the same ways as on their page: the bot link, an Echo account
  seen on the match list, or a player id that IS the Discord id. Their own show_avatar choice always wins; the same
  name-matching as on a profile page is not used here (it needs a lookup per player).
- The picture is Discord's CDN URL, loaded by the visitor's browser: no image traffic on this server.
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .. import auth, discord_names
from ..models import DiscordProfile, NakamaAccount, PlayerAlias, PlayerProfile

router = APIRouter(prefix="/api/avatars", tags=["avatars"])
MAX_IDS = 100


def pictures(settings, db, user_ids: list[str]) -> dict[str, str]:
    """player id -> picture URL for the players that have a visible one (see the module text)."""
    ids = list(dict.fromkeys(u for u in user_ids if u))[:MAX_IDS]
    if not ids:
        return {}
    main = {a.alias_user_id: a.main_user_id for a in db.scalars(select(PlayerAlias).where(PlayerAlias.alias_user_id.in_(ids)))}
    wanted = {u: main.get(u, u) for u in ids}  # a merged id shows its main player's picture
    mains = set(wanted.values())
    linked = {p.user_id: p for p in db.scalars(select(PlayerProfile).where(PlayerProfile.user_id.in_(mains)))}
    seen: dict[str, str] = {}  # replay player id -> discord id, from the match list (newest first wins)
    for acc in db.scalars(select(NakamaAccount).where(NakamaAccount.replay_user_id.in_(mains), NakamaAccount.discord_id.is_not(None))
                          .order_by(NakamaAccount.last_seen_at)):
        seen[acc.replay_user_id] = acc.discord_id
    discord_of: dict[str, str] = {}
    for u in mains:
        if u in linked:
            discord_of[u] = linked[u].discord_id
        elif u in seen:
            discord_of[u] = seen[u]
        elif auth.is_discord_id(u):
            discord_of[u] = u
    only_discord = {d for u, d in discord_of.items() if u not in linked}
    choice = {r.discord_id: r.show_avatar for r in db.scalars(select(DiscordProfile).where(DiscordProfile.discord_id.in_(only_discord)))}
    out: dict[str, str] = {}
    for original, u in wanted.items():
        d = discord_of.get(u)
        if d is None:
            continue
        show = linked[u].show_avatar if u in linked else choice.get(d, True)
        url = discord_names.avatar_for_id(settings, d) if show else None
        if url:
            out[original] = url
    return out


@router.get("")
def get_avatars(request: Request, ids: str = Query("", max_length=4000)):
    wanted = [i.strip() for i in ids.split(",") if i.strip()][:MAX_IDS]
    with request.app.state.sessionmaker() as db:
        data = pictures(request.app.state.settings, db, wanted)
    return JSONResponse(data, headers={"Cache-Control": "private, max-age=300"})
