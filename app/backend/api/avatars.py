"""Small Discord pictures for the name lists (user, 2026-11-06): Players, Leaderboard, Achievements.

GET /api/avatars?ids=<player id>,<player id>... (at most MAX_IDS) -> {player id: picture URL}, only for players who have one.
- It is its own request, never part of the cached list answers, so a player who switches their picture off in their profile
  disappears at once (Cache-Control: private, short).
- No Discord request per row: the pictures come from the server member list the site already reads in the background
  (discord_names.py). A player's Discord account is found the same ways as on their page: the bot link, an Echo account
  seen on the match list, a player id that IS the Discord id, or the one member with the player's exact name (as on a
  profile page, done for the whole list at once). Their own show_avatar choice always wins. A member missing from the
  member list is asked from Discord one by one, within auth.py's request budget (the rest fill in on the next visits).
- The picture is Discord's CDN URL, loaded by the visitor's browser: no image traffic on this server.
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .. import auth, discord_names
from ..models import DiscordProfile, NakamaAccount, Player, PlayerAlias, PlayerProfile

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
    # players with no Discord account known: the one member with their exact name, when no other player has that name
    # (the same rule as the player page, api/profiles.py, done for the whole list at once)
    rest = [u for u in mains if u not in discord_of]
    name_hit: dict[str, tuple[str, str]] = {}
    if rest:
        names = {u: n for u, n in db.execute(select(Player.user_id, Player.name).where(Player.user_id.in_(rest))) if n}
        found = discord_names.by_name(settings, list(names.values()))
        if found:
            taken = set(db.scalars(select(PlayerProfile.discord_id).where(PlayerProfile.discord_id.in_([v[0] for v in found.values()]))))
            lowered = {n.lower() for n, v in zip(names.values(), map(discord_names.normalise, names.values())) if v in found}
            owners: dict[str, set[str]] = {}
            for uid, name in db.execute(select(Player.user_id, Player.name).where(func.lower(Player.name).in_(lowered))):
                owners.setdefault(name.lower(), set()).add(db.get(PlayerAlias, uid).main_user_id if db.get(PlayerAlias, uid) else uid)
            for u, n in names.items():
                hit = found.get(discord_names.normalise(n))
                if hit and hit[0] not in taken and owners.get(n.lower(), {u}) <= {u}:
                    name_hit[u] = hit
                    discord_of[u] = hit[0]
    only_discord = {d for u, d in discord_of.items() if u not in linked}
    choice = {r.discord_id: r.show_avatar for r in db.scalars(select(DiscordProfile).where(DiscordProfile.discord_id.in_(only_discord)))}
    out: dict[str, str] = {}
    for original, u in wanted.items():
        d = discord_of.get(u)
        if d is None:
            continue
        show = linked[u].show_avatar if u in linked else choice.get(d, True)
        url = discord_names.avatar_for_id(settings, d) if show else None
        if show and not url:  # not in the member list (yet): ask Discord, budgeted + cached (auth.avatar_url); no default pictures
            fresh = auth.avatar_url(settings, d)
            url = fresh if fresh and "/embed/avatars/" not in fresh else None
        if url:
            out[original] = url
    return out


@router.get("")
def get_avatars(request: Request, ids: str = Query("", max_length=4000)):
    wanted = [i.strip() for i in ids.split(",") if i.strip()][:MAX_IDS]
    with request.app.state.sessionmaker() as db:
        data = pictures(request.app.state.settings, db, wanted)
    # member list not read yet / lookups still filling in: ask again soon instead of keeping a thin answer for 5 minutes
    ttl = 300 if discord_names.loaded() else 20
    return JSONResponse(data, headers={"Cache-Control": f"private, max-age={ttl}"})
