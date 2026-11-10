"""Discord avatars for players not linked by the bot (user, 2026-11-02): when a player's name matches exactly one
member of the Discord server and no other player has that name, that member's avatar is the player's picture.

- Names compared: the member's server nickname, display name and username, ignoring case. A name used by two members,
  or by two players (merged ids count as one player, D34), gives no picture: only 1:1 matches.
- A member linked by the bot to some player is only ever shown for that player, and a linked player's own choice
  (show_avatar) always wins (api/profiles.py).
- The picture is Discord's CDN URL, loaded by the visitor's browser straight from Discord: no image traffic on this
  server. Members without their own avatar give no picture (Discord's default one says nothing).
- The member list is read with the bot (needs the Server Members intent in the Discord developer portal), in the
  background, at most every REFRESH_S. Until it is loaded, or when Discord cannot be asked, there are no matches.
- Read only when a player's profile page needs a name match (user, 2026-11-10: pictures only when a profile is opened),
  at most every REFRESH_S; never at startup, never for list pages (they use what was read).
- Discord refusing the list (403: the bot's Server Members intent is off) is logged once and not asked again until the
  next start; other failures are retried after RETRY_S. ECHOVR_DISCORD_NAME_PICTURES=0 never asks (user, 2026-11-10).
"""

import logging
import threading
import time
import unicodedata

import httpx

from . import auth
from .config import Settings

log = logging.getLogger(__name__)

REFRESH_S = 6 * 3600  # new members / changed avatars show within 6 hours
RETRY_S = 600  # after a failed read
PAGE = 1000  # Discord's maximum per request

_lock = threading.Lock()
_by_name: dict[str, tuple[str, str]] = {}  # normalised name -> (discord id, avatar hash) for 1:1 names only
_by_id: dict[str, str] = {}  # discord id -> avatar hash, every member with their own picture (list pages: no request per row)
_next_refresh = 0.0
_loading = False
_refused = [False]  # Discord said 403 (no Server Members intent): nothing will come until the next start


def normalise(name: str | None) -> str:
    return unicodedata.normalize("NFKC", name or "").casefold().strip()


def _read_members(settings: Settings) -> list[dict]:
    members, after = [], "0"
    while True:
        r = auth._bot_get(settings, f"/guilds/{settings.discord_guild_id}/members?limit={PAGE}&after={after}")
        r.raise_for_status()
        page = r.json()
        members += page
        if len(page) < PAGE:
            return members
        after = page[-1]["user"]["id"]


def names_of(members: list[dict]) -> dict[str, tuple[str, str]]:
    """normalised name -> (discord id, avatar hash), only names that belong to exactly one member with an avatar."""
    owners: dict[str, set[str]] = {}
    avatars: dict[str, str | None] = {}
    for m in members:
        user = m.get("user") or {}
        uid = str(user.get("id") or "")
        if not auth.is_discord_id(uid) or user.get("bot"):
            continue
        avatars[uid] = user.get("avatar")
        for name in {normalise(m.get("nick")), normalise(user.get("global_name")), normalise(user.get("username"))}:
            if name:
                owners.setdefault(name, set()).add(uid)
    result = {}
    for name, ids in owners.items():
        if len(ids) == 1:
            uid = next(iter(ids))
            avatar = avatars[uid]
            if avatar and avatar.replace("a_", "", 1).isalnum():
                result[name] = (uid, avatar)
    return result


def _refresh(settings: Settings) -> None:
    global _by_name, _by_id, _next_refresh, _loading
    try:
        members = _read_members(settings)
        by_name = names_of(members)
        by_id = {str((m.get("user") or {}).get("id")): (m.get("user") or {}).get("avatar") for m in members
                 if auth.is_discord_id(str((m.get("user") or {}).get("id") or "")) and not (m.get("user") or {}).get("bot")}
        by_id = {uid: a for uid, a in by_id.items() if a and a.replace("a_", "", 1).isalnum()}
        with _lock:
            _by_name, _by_id, _next_refresh = by_name, by_id, time.monotonic() + REFRESH_S
        log.info("Discord members read: %d names usable for player pictures", len(by_name))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:  # the Server Members intent is off: asking again cannot help
            log.warning("Discord member list refused (403): turn on the bot's Server Members intent or set "
                        "ECHOVR_DISCORD_NAME_PICTURES=0. Player pictures by name stay off until the next start.")
            with _lock:
                _next_refresh, _refused[0] = float("inf"), True
        else:
            log.warning("Discord member list not read (player pictures by name): %s", e)
            with _lock:
                _next_refresh = time.monotonic() + RETRY_S
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
        log.warning("Discord member list not read (player pictures by name): %s", e)
        with _lock:
            _next_refresh = time.monotonic() + RETRY_S
    finally:
        with _lock:
            _loading = False


def refresh_soon(settings: Settings) -> None:
    """Read the member list in the background if it is due (never blocks a request)."""
    global _loading
    if not (settings.discord_name_pictures and settings.discord_bot_token and settings.discord_guild_id):
        return
    with _lock:
        if _loading or time.monotonic() < _next_refresh:
            return
        _loading = True
    threading.Thread(target=_refresh, args=(settings,), name="discord-members", daemon=True).start()


def match(settings: Settings, name: str) -> tuple[str, str] | None:
    """(discord id, avatar URL on Discord's CDN) of the one member with this name, or None."""
    refresh_soon(settings)
    with _lock:
        hit = _by_name.get(normalise(name))
    if hit is None:
        return None
    uid, avatar = hit
    return uid, f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png?size=256"


def by_name(settings: Settings, names: list[str]) -> dict[str, tuple[str, str]]:
    """normalised name -> (discord id, avatar hash) for those of the names that belong to exactly one member (lists: one
    lock). Lists never start a read of the member list: only what a profile page already caused."""
    with _lock:
        return {n: _by_name[n] for n in (normalise(x) for x in names) if n in _by_name}


def loaded() -> bool:
    with _lock:
        return _next_refresh > 0 and bool(_by_id or _by_name)


def avatar_for_id(settings: Settings, discord_id: str, size: int = 64, ask: bool = False) -> str | None:
    """Discord CDN URL of this member's own picture, from the member list (None: not a member, no picture, or not read yet).
    ask: a profile page, which may start a read of the member list when it is due."""
    if ask:
        refresh_soon(settings)
    with _lock:
        avatar = _by_id.get(discord_id)
    return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar}.png?size={size}" if avatar else None


def clear() -> None:
    """Tests: forget the member list."""
    global _by_name, _by_id, _next_refresh, _loading
    with _lock:
        _by_name, _by_id, _next_refresh, _loading = {}, {}, 0.0, False
        _refused[0] = False
