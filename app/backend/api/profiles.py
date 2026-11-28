"""Player profiles linked to Discord (user, 2026-11-02).

- The Discord bot links a Discord account to an EchoVR player: POST /api/bot/link with its shared secret
  (ECHOVR_BOT_LINK_SECRET, `Authorization: Bearer <secret>`). The site trusts the bot: any checking of who owns a
  player is done there. One player per Discord account and one Discord account per player; linking again moves it.
  A pair an admin unlinked on the Console stays apart: the bot gets 409 link_blocked (discord_links.py).
- The linked person, logged in with the site's Discord login, may change only two things on their player page: the
  bio and whether their Discord avatar is shown as the profile picture (POST /api/profiles/{user_id}, X-EchoVR;
  a fourth exception to the read-only website, D38). Nothing else about a player can be changed this way.
"""

import hmac
import threading
import time
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from .. import aliases, auth, discord_links, discord_names, guard, regions
from ..discord_links import main_id as _main_id
from ..errors import ApiError
from ..models import ArenaPlayer, DiscordProfile, NakamaAccount, NakamaCombatPlayer, Player, PlayerProfile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
bot_router = APIRouter(prefix="/api/bot", tags=["bot"])

BIO_MAX = 500
BIO_MAX_LINES = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_bio(text: str | None) -> str | None:
    """Plain text: control and invisible format characters removed (newlines kept), blank lines squeezed, cut to
    BIO_MAX characters and BIO_MAX_LINES lines. Empty -> None. Shown as text, never as HTML."""
    if text is None:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c == "\n" or unicodedata.category(c)[0] != "C")
    lines = [line.rstrip() for line in text.split("\n")]
    squeezed: list[str] = []
    for line in lines:
        if line or (squeezed and squeezed[-1]):
            squeezed.append(line)
    text = "\n".join(squeezed[:BIO_MAX_LINES]).strip()
    return text[:BIO_MAX] or None


def _name_match_avatar(request: Request, db, user_id: str) -> str | None:
    """Avatar of the one Discord member with this player's name, when no other player has it (discord_names.py)."""
    name = db.scalar(select(Player.name).where(Player.user_id == user_id))
    if not name:
        return None
    hit = discord_names.match(request.app.state.settings, name)
    if hit is None:
        return None
    discord_id, url = hit
    return url if discord_links.name_match_ok(db, user_id, name, discord_id) else None


def _seen_avatar(request: Request, db, user_id: str) -> str | None:
    """Same picture as the list pages (api/avatars.py): the Discord account seen with this player on the match list,
    respecting that account's own show_avatar choice. Fresh from Discord (budgeted, cached), else the member list."""
    seen = discord_links.seen_discord(db, user_id)
    if seen is None:
        return None
    row = db.get(DiscordProfile, seen)
    if row is not None and not row.show_avatar:
        return None
    settings = request.app.state.settings
    return discord_names.avatar_for_id(settings, seen, 256, ask=True) or auth.avatar_url(settings, seen)


def _id_avatar(request: Request, db, user_id: str) -> str | None:
    """A player whose id IS a Discord id (recent replays): that account's picture, as on the list pages (api/avatars.py),
    respecting its own show_avatar choice; no default picture. The profile page is where it is fetched (user, 2026-11-10:
    pictures only when a profile is opened), so the lists can show it afterwards."""
    if not auth.is_discord_id(user_id) or not discord_links.allowed(db, user_id, user_id):
        return None
    row = db.get(DiscordProfile, user_id)
    if row is not None and not row.show_avatar:
        return None
    url = auth.avatar_url(request.app.state.settings, user_id)
    return url if url and "/embed/avatars/" not in url else None


def _account(db, user_id: str) -> dict | None:
    """The Echo (Nakama) account linked to this replay player, collected from the match list (arena.py): its name and when it
    was last seen playing. No Discord id: it is not shown to visitors."""
    own = aliases.ids_of(db, _main_id(db, user_id))  # every merged id: the account may be linked to one of them (2026-11-27)
    accounts = db.scalars(select(NakamaAccount).where(NakamaAccount.replay_user_id.in_(own)).order_by(NakamaAccount.last_seen_at.desc()))
    acc = next((a for a in accounts.all() if a.discord_id is None or discord_links.allowed(db, user_id, a.discord_id)), None)
    return None if acc is None else {"name": acc.display_name or acc.username, "last_seen": acc.last_seen_at}


def _public(request: Request, profile: PlayerProfile | None, viewer: dict | None, name_avatar: str | None = None) -> dict:
    settings = request.app.state.settings
    if profile is None:
        return {"linked": False, "bio": None, "avatar_url": name_avatar, "show_avatar": name_avatar is not None,
                "editable": False, "country": None, "region": None}
    return {
        "linked": True,
        "bio": profile.bio,
        "country": profile.country,
        "region": profile.region,
        "place_detected": profile.place_set_by == PLACE_BY_IP,
        "place_auto": profile.place_set_by != PLACE_BY_PLAYER,
        "show_avatar": profile.show_avatar,
        "avatar_url": auth.avatar_url(settings, profile.discord_id) if profile.show_avatar else None,
        "editable": bool(viewer and viewer["id"] == profile.discord_id),
    }


# --- website --------------------------------------------------------------------------------

@router.get("/me")
def my_profile(request: Request):
    """The logged-in visitor's own profile (from the Discord login only; nothing about anyone else is asked for)."""
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to see your profile")
    with request.app.state.sessionmaker() as db:
        if not _known_discord(db, viewer["id"]):  # never seen on the match list: nothing to show yet
            return {"linked": False, "bio": None, "show_avatar": True, "avatar_url": None, "editable": False, "user_id": None,
                    "name": viewer["name"], "known": False, "country": None, "region": None}
        return _discord_public(request, db, viewer["id"], viewer) | {"name": viewer["name"], "known": True}


@router.post("/me")
def edit_my_profile(request: Request, edit: "ProfileEdit"):
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to edit your profile")
    return edit_discord_profile(request, viewer["id"], edit) | {"name": viewer["name"], "known": True}


@router.get("/{user_id}")
def get_profile(request: Request, user_id: str):
    """Bio and picture of a player, and whether the visitor may edit them (their own linked player)."""
    return profile_answer(request, user_id, auth.viewer(request))  # per visitor: never kept in a shared cache


def profile_answer(request: Request, user_id: str, viewer: dict | None) -> dict:
    """The profile as `viewer` sees it; viewer None = what everybody who is not logged in sees, the same for all of them, so
    Cloudflare may keep it (/api/players/{user_id}/bio, 2026-11-27 review: every anonymous player page view reached the NAS)."""
    with request.app.state.sessionmaker() as db:
        main = _main_id(db, user_id)
        profile = discord_links.profile_of(db, main)
        account = _account(db, main)
        if profile is None and discord_links.is_own_id(db, main):
            # recent replays carry the Discord id as the player id: the Discord-keyed profile is this player's profile
            if db.get(DiscordProfile, main) is not None or (viewer and viewer["id"] == main) or account is not None:
                return _discord_public(request, db, main, viewer) | {"account": account}
        if profile is None:  # the Discord account seen with this player on the Echo match list: its bio (My profile)
            seen = discord_links.seen_discord(db, main)
            if seen:
                if db.get(DiscordProfile, seen) is not None or (viewer and hmac.compare_digest(viewer["id"], seen)):
                    return _discord_public(request, db, seen, viewer) | {"account": account, "user_id": main}
        name_avatar = None
        if profile is None:
            name_avatar = _seen_avatar(request, db, main) or _id_avatar(request, db, main) or _name_match_avatar(request, db, main)
        return _public(request, profile, viewer, name_avatar) | {"account": account}


# --- by Discord id (people who play but are not linked to a replay player, user 2026-11-05) --------------

def _known_discord(db, discord_id: str) -> bool:
    """Only Discord ids this site has seen (Nakama match list, bot link, a saved profile): it is not a lookup for any account."""
    return any(db.scalar(select(col).where(col == discord_id).limit(1)) is not None
               for col in (NakamaAccount.discord_id, ArenaPlayer.discord_id, NakamaCombatPlayer.discord_id, PlayerProfile.discord_id, DiscordProfile.discord_id, Player.user_id))


def _own_account(db, discord_id: str) -> dict | None:
    acc = db.scalar(select(NakamaAccount).where(NakamaAccount.discord_id == discord_id).order_by(NakamaAccount.last_seen_at.desc()))
    return None if acc is None else {"name": acc.display_name or acc.username, "last_seen": acc.last_seen_at}


def _discord_public(request: Request, db, discord_id: str, viewer: dict | None) -> dict:
    linked = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == discord_id))
    row = linked or db.get(DiscordProfile, discord_id)  # a bot-linked player's profile is the one profile of that account
    show = row.show_avatar if row is not None else True
    return {"linked": True, "bio": row.bio if row is not None else None, "show_avatar": show,
            "country": row.country if row is not None else None, "region": row.region if row is not None else None,
            "place_detected": row is not None and row.place_set_by == PLACE_BY_IP,
            "place_auto": row is None or row.place_set_by != PLACE_BY_PLAYER,
            "avatar_url": auth.avatar_url(request.app.state.settings, discord_id) if show else None,
            "editable": bool(viewer and hmac.compare_digest(viewer["id"], discord_id)),
            # the replay player page, when there is one: bot-linked, a replay player whose id IS the Discord id, or the
            # player its Echo account was seen with on the match list
            "user_id": discord_links.player_of(db, discord_id),
            "account": _own_account(db, discord_id)}


@router.get("/discord/{discord_id}")
def get_discord_profile(request: Request, discord_id: str):
    viewer = auth.viewer(request)
    if not auth.is_discord_id(discord_id):
        raise ApiError(400, "bad_discord_id", "Not a Discord user id")
    with request.app.state.sessionmaker() as db:
        if not _known_discord(db, discord_id):
            raise ApiError(404, "unknown_profile", "No profile")
        return _discord_public(request, db, discord_id, viewer)


@router.post("/discord/{discord_id}")
def edit_discord_profile(request: Request, discord_id: str, edit: "ProfileEdit"):
    """Only the bio and the avatar choice, only by that Discord account itself (logged in with Discord)."""
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to edit your profile")
    if not auth.is_discord_id(discord_id) or not hmac.compare_digest(viewer["id"], discord_id):
        raise ApiError(403, "not_your_profile", "You can only edit your own profile")
    if edit.bio is not None and len(edit.bio) > BIO_MAX * 4:
        raise ApiError(400, "bio_too_long", f"The bio can be at most {BIO_MAX} characters")
    _check_place(edit)
    with request.app.state.sessionmaker() as db:
        if not _known_discord(db, discord_id):
            raise ApiError(404, "unknown_profile", "Play a match first: your Discord account is not known here yet")
        row = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == discord_id)) or db.get(DiscordProfile, discord_id)
        if row is None:
            row = DiscordProfile(discord_id=discord_id, bio=None, show_avatar=True, updated_at=_now())
            db.add(row)
        row.bio = clean_bio(edit.bio)
        row.show_avatar = edit.show_avatar
        _apply_place(row, edit)
        row.updated_at = _now()
        db.commit()
        _detect_now(request, db, discord_id, edit)
        if row.show_avatar:
            auth.avatar_url(request.app.state.settings, discord_id, fresh=True)
        return _discord_public(request, db, discord_id, viewer)


class ProfileEdit(BaseModel):
    bio: str | None = None
    show_avatar: bool = True
    # flag and game region (user, 2026-11-28; regions.py): only changed when sent, so a page opened before they existed
    # does not clear them; null or "" = none
    country: str | None = None
    region: str | None = None
    place_auto: bool = False  # true: taken from the player's connection again (country / region ignored)


def _check_place(edit: ProfileEdit) -> None:
    """A country or region that is not on the lists is refused before anything is saved."""
    try:
        regions.clean_country(edit.country)
        regions.clean_region(edit.region)
    except ValueError:
        raise ApiError(400, "bad_region", "Pick a country and region from the lists")


def _apply_place(row, edit: ProfileEdit) -> None:
    """The player's own choice is never overwritten by detection; choosing "automatic" hands it back to detection."""
    if edit.place_auto:
        row.country = row.region = row.place_set_by = None  # detected again at once (_detect_now)
        return
    if "country" in edit.model_fields_set or "region" in edit.model_fields_set:
        if "country" in edit.model_fields_set:
            row.country = regions.clean_country(edit.country)
        if "region" in edit.model_fields_set:
            row.region = regions.clean_region(edit.region)
        # the region follows the country (user, 2026-11-28): the country's own one; the US and Canada pick one of theirs
        row.region = regions.matching_region(row.country, row.region)
        row.place_set_by = PLACE_BY_PLAYER


# --- country and game region from the connection (user, 2026-11-28: "auto gather the region via their IP address too,
# unless it's manually set"; shown at once, marked as detected, the player can change it). Only for the logged-in
# visitor's own Discord account; from Cloudflare's CF-IPCountry header, believed only through the tunnel (guard.py).
# No IP address is kept or sent anywhere. A VPN shows the VPN's country.
PLACE_BY_IP, PLACE_BY_PLAYER = "ip", "player"
DETECT_EVERY_S = 3600  # per account: page loads ask /api/auth/me every time, the database is asked at most hourly
_detected: dict[str, tuple[float, str]] = {}  # Discord id -> (when, country seen)
_detected_lock = threading.Lock()


def _seen_place(request: Request) -> tuple[str, str | None] | None:
    """(country, game region) of the visitor's connection, or None when not known (not through Cloudflare, Tor, unknown)."""
    if not guard._from_inside(request.client.host if request.client else None):
        return None
    try:
        country = regions.clean_country(request.headers.get("cf-ipcountry"))
    except ValueError:
        return None  # XX (unknown), T1 (Tor)
    return (country, regions.region_for(country, request.headers.get("cf-region-code"))) if country else None


def _store_place(db, discord_id: str, place: tuple[str, str | None]) -> bool:
    """Saves a detected place on the account's profile row unless the player chose one; True when it changed. The bio's
    date (updated_at) is not touched: it dates the Edit your Bio challenge."""
    row = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == discord_id)) or db.get(DiscordProfile, discord_id)
    if row is None:
        if not _known_discord(db, discord_id):
            return False
        row = DiscordProfile(discord_id=discord_id, bio=None, show_avatar=True, updated_at=_now())
        db.add(row)
    if row.place_set_by == PLACE_BY_PLAYER or (row.country, row.region, row.place_set_by) == (*place, PLACE_BY_IP):
        return False
    row.country, row.region, row.place_set_by = place[0], place[1], PLACE_BY_IP
    db.commit()
    return True


def detect_place(request: Request, discord_id: str) -> None:
    """Called on the logged-in visitor's page loads (/api/auth/me): at most once an hour per account, or when the
    country seen changes. Never fails the request it rides on."""
    place = _seen_place(request)
    if place is None:
        return
    now = time.monotonic()
    with _detected_lock:
        last = _detected.get(discord_id)
        if last is not None and last[1] == place[0] and now - last[0] < DETECT_EVERY_S:
            return
        _detected[discord_id] = (now, place[0])
    try:
        with request.app.state.sessionmaker() as db:
            _store_place(db, discord_id, place)
    except Exception:  # a locked database must not break the login check
        with _detected_lock:
            _detected.pop(discord_id, None)


def _detect_now(request: Request, db, discord_id: str, edit: ProfileEdit) -> None:
    """After "automatic" was chosen: detected in the same request, so the page shows it at once."""
    if edit.place_auto and (place := _seen_place(request)) is not None:
        _store_place(db, discord_id, place)


@router.post("/{user_id}")
def edit_profile(request: Request, user_id: str, edit: ProfileEdit):
    """Only the bio and the avatar choice; only by the Discord account linked to this player."""
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to edit your profile")
    if edit.bio is not None and len(edit.bio) > BIO_MAX * 4:
        raise ApiError(400, "bio_too_long", f"The bio can be at most {BIO_MAX} characters")
    _check_place(edit)
    with request.app.state.sessionmaker() as db:
        main = _main_id(db, user_id)
        profile = discord_links.profile_of(db, main)
        if profile is None and auth.is_discord_id(main) and hmac.compare_digest(main, viewer["id"]) and discord_links.allowed(db, main, main):
            return edit_discord_profile(request, main, edit)  # the replay id is the viewer's own Discord id
        if profile is None:
            seen = discord_links.seen_discord(db, main)  # the viewer's Echo account was seen with this player on the match list
            if seen and hmac.compare_digest(seen, viewer["id"]):
                return edit_discord_profile(request, seen, edit) | {"user_id": main}
        if profile is None or not hmac.compare_digest(profile.discord_id, viewer["id"]):
            raise ApiError(403, "not_your_profile", "Only the Discord account linked to this player can edit it")
        profile.bio = clean_bio(edit.bio)
        profile.show_avatar = edit.show_avatar
        _apply_place(profile, edit)
        profile.updated_at = _now()
        db.commit()
        _detect_now(request, db, profile.discord_id, edit)
        if profile.show_avatar:
            auth.avatar_url(request.app.state.settings, profile.discord_id, fresh=True)  # a new avatar shows at once
        return _public(request, profile, viewer) | {"account": _account(db, main)}


# --- Discord bot ----------------------------------------------------------------------------

def _require_bot(request: Request) -> None:
    secret = request.app.state.settings.bot_link_secret
    if not secret:
        raise ApiError(404, "bot_link_disabled", "Discord bot linking is not set up (ECHOVR_BOT_LINK_SECRET)")
    given = request.headers.get("authorization", "")
    if not hmac.compare_digest(given.encode(), f"Bearer {secret}".encode()):
        raise ApiError(401, "bad_bot_secret", "Wrong or missing bot secret")


def _discord_id(value: str) -> str:
    value = value.strip()
    if not auth.is_discord_id(value):
        raise ApiError(400, "bad_discord_id", "discord_id must be a Discord user id (17-20 digits)")
    return value


def _link_info(db, profile: PlayerProfile | None) -> dict:
    if profile is None:
        return {"linked": False}
    name = db.scalar(select(Player.name).where(Player.user_id == profile.user_id))
    return {"linked": True, "discord_id": profile.discord_id, "user_id": profile.user_id, "name": name,
            "linked_at": profile.linked_at}


class Link(BaseModel):
    discord_id: str
    user_id: str  # EchoVR user id (a merged id is linked to its main player)


@bot_router.post("/link")
def bot_link(request: Request, link: Link):
    """Link a Discord account to a player. Relinking moves the link; the bio and picture choice go with the Discord account."""
    _require_bot(request)
    discord_id = _discord_id(link.discord_id)
    with request.app.state.sessionmaker() as db:
        user_id = _main_id(db, link.user_id.strip())
        if db.scalar(select(Player.id).where(Player.user_id == user_id)) is None:
            raise ApiError(404, "unknown_player", f"No player with user id {link.user_id[:64]}")
        if discord_links.blocked(db, user_id, discord_id):  # an admin's correction is not undone by the bot
            raise ApiError(409, "link_blocked", "An admin unlinked this Discord account from this player; only an admin can link them again")
        profile, changed = discord_links.link(db, user_id, discord_id)
        db.commit()
        return _link_info(db, profile) | {"changed": changed}


class Unlink(BaseModel):
    discord_id: str | None = None
    user_id: str | None = None


@bot_router.post("/unlink")
def bot_unlink(request: Request, unlink: Unlink):
    """Remove a link (by Discord account or by player); the bio goes with the Discord account."""
    _require_bot(request)
    if not unlink.discord_id and not unlink.user_id:
        raise ApiError(400, "missing_id", "Give discord_id or user_id")
    with request.app.state.sessionmaker() as db:
        if unlink.discord_id:
            profile = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == _discord_id(unlink.discord_id)))
        else:
            profile = discord_links.profile_of(db, _main_id(db, unlink.user_id.strip()))
        removed = profile is not None and discord_links.unlink(db, profile.user_id, profile.discord_id, block=False)
        db.commit()
    return {"removed": removed}


@bot_router.post("/lookup")
def bot_lookup(request: Request, unlink: Unlink):
    """Which player a Discord account is linked to (or which account a player is linked to). POST so the secret
    travels in the same way as for the other bot calls."""
    _require_bot(request)
    with request.app.state.sessionmaker() as db:
        if unlink.discord_id:
            profile = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == _discord_id(unlink.discord_id)))
        elif unlink.user_id:
            profile = discord_links.profile_of(db, _main_id(db, unlink.user_id.strip()))
        else:
            raise ApiError(400, "missing_id", "Give discord_id or user_id")
        return _link_info(db, profile)
