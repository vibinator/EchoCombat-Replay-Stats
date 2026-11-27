"""Pinned challenges (user, 2026-11-27): a player pins up to MAX_PINS challenges to work on; every visitor of their page
sees them. Only the Discord account that may edit that player's bio may change them (the same three routes as
profiles.edit_profile: bot / admin link, a player id that IS the Discord id, the Echo account seen on the match list).
POST /api/profiles/{user_id}/pins with X-EchoVR: part of the profile write, the fourth exception to D38 (middleware WRITES).
A completed challenge is unpinned by itself (drop_completed, when the player's challenges are worked out)."""

import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import delete, select

from .. import auth, discord_links
from ..errors import ApiError
from ..icons import RULE_IDS
from ..models import ChallengePin
from .achievements import require_launched

router = APIRouter(prefix="/api/profiles", tags=["pins"])
MAX_PINS = 3


def owner_of(db, main: str) -> str | None:
    """The Discord account that may edit this (main) player's page, as profiles.edit_profile decides it."""
    profile = discord_links.profile_of(db, main)
    if profile is not None:
        return profile.discord_id
    if auth.is_discord_id(main) and discord_links.allowed(db, main, main):
        return main
    return discord_links.seen_discord(db, main)


def pinned(db, main: str) -> list[int]:
    return list(db.scalars(select(ChallengePin.achievement_id).where(ChallengePin.user_id == main)
                           .order_by(ChallengePin.pinned_at, ChallengePin.achievement_id)))


def drop_completed(db, user_id: str, items: list[dict]) -> list[int]:
    """Unpins what this player has completed (user, 2026-11-27: "if a pin is completed, it will remove"); returns the pins
    left. Public data: it goes in the shared challenges answer, so anonymous visitors need no per-visitor request."""
    # reads only, unless a pin is complete: a DELETE takes SQLite's write lock even when it removes nothing, and would
    # wait for the worker saving a replay (a page view must never do that)
    main = discord_links.main_id(db, user_id)
    have = pinned(db, main)
    done = [i["id"] for i in items if i["id"] in have and i.get("progress", 0) >= 1]
    if done:
        db.execute(delete(ChallengePin).where(ChallengePin.user_id == main, ChallengePin.achievement_id.in_(done)))
        db.commit()
    return [p for p in have if p not in done]


def _answer(db, main: str, viewer: dict | None) -> dict:
    owner = owner_of(db, main)
    return {"pins": pinned(db, main), "max": MAX_PINS,
            "editable": bool(viewer and owner and hmac.compare_digest(viewer["id"], owner))}


@router.get("/{user_id}/pins")
def get_pins(request: Request, user_id: str):
    require_launched(request)
    viewer = auth.viewer(request)  # per visitor (editable): never kept in a shared cache
    with request.app.state.sessionmaker() as db:
        return _answer(db, discord_links.main_id(db, user_id), viewer)


class PinEdit(BaseModel):
    id: int
    pinned: bool


@router.post("/{user_id}/pins")
def edit_pins(request: Request, user_id: str, edit: PinEdit):
    require_launched(request)
    viewer = auth.viewer(request)
    if not viewer:
        raise ApiError(401, "login_required", "Log in with Discord to pin challenges")
    if edit.id not in RULE_IDS:
        raise ApiError(404, "unknown_challenge", "No such challenge")
    with request.app.state.sessionmaker() as db:
        main = discord_links.main_id(db, user_id)
        owner = owner_of(db, main)
        if not owner or not hmac.compare_digest(viewer["id"], owner):
            raise ApiError(403, "not_your_profile", "Only the Discord account linked to this player can pin its challenges")
        have = pinned(db, main)
        if edit.pinned and edit.id not in have:
            if len(have) >= MAX_PINS:
                raise ApiError(409, "pins_full", f"At most {MAX_PINS} pinned challenges: unpin one first")
            db.add(ChallengePin(user_id=main, achievement_id=edit.id,
                                pinned_at=datetime.now(timezone.utc).isoformat(timespec="seconds")))
        elif not edit.pinned:
            db.execute(delete(ChallengePin).where(ChallengePin.user_id == main, ChallengePin.achievement_id == edit.id))
        db.commit()
        return _answer(db, main, viewer)
