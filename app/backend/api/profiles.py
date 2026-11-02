"""Player profiles linked to Discord (user, 2026-11-02).

- The Discord bot links a Discord account to an EchoVR player: POST /api/bot/link with its shared secret
  (ECHOVR_BOT_LINK_SECRET, `Authorization: Bearer <secret>`). The site trusts the bot: any checking of who owns a
  player is done there. One player per Discord account and one Discord account per player; linking again moves it.
- The linked person, logged in with the site's Discord login, may change only two things on their player page: the
  bio and whether their Discord avatar is shown as the profile picture (POST /api/profiles/{user_id}, X-EchoVR;
  a fourth exception to the read-only website, D38). Nothing else about a player can be changed this way.
"""

import hmac
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import delete, select

from .. import auth
from ..errors import ApiError
from ..models import Player, PlayerAlias, PlayerProfile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
bot_router = APIRouter(prefix="/api/bot", tags=["bot"])

BIO_MAX = 500
BIO_MAX_LINES = 8


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _main_id(db, user_id: str) -> str:
    """A merged id (D34) means its main player."""
    alias = db.get(PlayerAlias, user_id)
    return alias.main_user_id if alias is not None else user_id


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


def _public(request: Request, profile: PlayerProfile | None, viewer: dict | None) -> dict:
    settings = request.app.state.settings
    if profile is None:
        return {"linked": False, "bio": None, "avatar_url": None, "show_avatar": False, "editable": False}
    return {
        "linked": True,
        "bio": profile.bio,
        "show_avatar": profile.show_avatar,
        "avatar_url": auth.avatar_url(settings, profile.discord_id) if profile.show_avatar else None,
        "editable": bool(viewer and viewer["id"] == profile.discord_id),
    }


# --- website --------------------------------------------------------------------------------

@router.get("/{user_id}")
def get_profile(request: Request, user_id: str):
    """Bio and picture of a player, and whether the visitor may edit them (their own linked player)."""
    viewer = auth.viewer(request)  # per visitor: never kept in a shared cache
    with request.app.state.sessionmaker() as db:
        profile = db.get(PlayerProfile, _main_id(db, user_id))
        return _public(request, profile, viewer)


class ProfileEdit(BaseModel):
    bio: str | None = None
    show_avatar: bool = True


@router.post("/{user_id}")
def edit_profile(request: Request, user_id: str, edit: ProfileEdit):
    """Only the bio and the avatar choice; only by the Discord account linked to this player."""
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to edit your profile")
    if edit.bio is not None and len(edit.bio) > BIO_MAX * 4:
        raise ApiError(400, "bio_too_long", f"The bio can be at most {BIO_MAX} characters")
    with request.app.state.sessionmaker() as db:
        profile = db.get(PlayerProfile, _main_id(db, user_id))
        if profile is None or not hmac.compare_digest(profile.discord_id, viewer["id"]):
            raise ApiError(403, "not_your_profile", "Only the Discord account linked to this player can edit it")
        profile.bio = clean_bio(edit.bio)
        profile.show_avatar = edit.show_avatar
        profile.updated_at = _now()
        db.commit()
        if profile.show_avatar:
            auth.avatar_url(request.app.state.settings, profile.discord_id, fresh=True)  # a new avatar shows at once
        return _public(request, profile, viewer)


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
    """Link a Discord account to a player. Relinking moves the link; the bio stays with the player only when the
    same Discord account is linked to it again."""
    _require_bot(request)
    discord_id = _discord_id(link.discord_id)
    with request.app.state.sessionmaker() as db:
        user_id = _main_id(db, link.user_id.strip())
        if db.scalar(select(Player.id).where(Player.user_id == user_id)) is None:
            raise ApiError(404, "unknown_player", f"No player with user id {link.user_id[:64]}")
        existing = db.get(PlayerProfile, user_id)
        if existing is not None and existing.discord_id == discord_id:
            return _link_info(db, existing) | {"changed": False}
        # this Discord account's old player, and this player's old Discord account, are unlinked
        db.execute(delete(PlayerProfile).where(PlayerProfile.discord_id == discord_id))
        if existing is not None:
            db.delete(existing)
        db.flush()
        now = _now()
        profile = PlayerProfile(user_id=user_id, discord_id=discord_id, bio=None, show_avatar=True, linked_at=now,
                                updated_at=now)
        db.add(profile)
        db.commit()
        return _link_info(db, profile) | {"changed": True}


class Unlink(BaseModel):
    discord_id: str | None = None
    user_id: str | None = None


@bot_router.post("/unlink")
def bot_unlink(request: Request, unlink: Unlink):
    """Remove a link (by Discord account or by player); the bio goes with it."""
    _require_bot(request)
    if not unlink.discord_id and not unlink.user_id:
        raise ApiError(400, "missing_id", "Give discord_id or user_id")
    with request.app.state.sessionmaker() as db:
        if unlink.discord_id:
            where = PlayerProfile.discord_id == _discord_id(unlink.discord_id)
        else:
            where = PlayerProfile.user_id == _main_id(db, unlink.user_id.strip())
        removed = db.execute(delete(PlayerProfile).where(where)).rowcount
        db.commit()
    return {"removed": bool(removed)}


@bot_router.post("/lookup")
def bot_lookup(request: Request, unlink: Unlink):
    """Which player a Discord account is linked to (or which account a player is linked to). POST so the secret
    travels in the same way as for the other bot calls."""
    _require_bot(request)
    with request.app.state.sessionmaker() as db:
        if unlink.discord_id:
            profile = db.scalar(select(PlayerProfile).where(PlayerProfile.discord_id == _discord_id(unlink.discord_id)))
        elif unlink.user_id:
            profile = db.get(PlayerProfile, _main_id(db, unlink.user_id.strip()))
        else:
            raise ApiError(400, "missing_id", "Give discord_id or user_id")
        return _link_info(db, profile)
