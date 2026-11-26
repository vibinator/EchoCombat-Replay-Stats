"""Challenges about the player's page rather than their games (user, 2026-11-26: "Edit your Bio", a special; removed and
brought back the same day). Like the Combat challenges they are added to a player's answer apart from the replay ones, and
stay out of every total, the ranking and Medal Collector (counted=False): the replay evaluation is cached per set of games,
and a bio changes without any game."""

from sqlalchemy import func, select

from .achievements import Rule
from .models import Player, PlayerProfile

GROUP = "Profile"
BIO_RULE = Rule(277, "Edit your Bio", "Write a bio on your player page (log in with Discord, then edit it on your profile)", "game", None,
                lambda games: 0.0, new=True, group=GROUP, counted=False, binary=True)
PROFILE_RULES = [BIO_RULE]
NOTES = ["On your player page", "Discord login"]


def _entry(rule: Rule) -> dict:
    return {"id": rule.id, "name": rule.name, "description": rule.description, "rules": NOTES, "period": rule.period,
            "icon": rule.icon, "estimated": False, "new": rule.new, "group": rule.group, "counted": rule.counted, "binary": rule.binary,
            "levels": None, "unit": ""}


def catalogue(db) -> list[dict]:
    """The rule list with rarity: share of players with a bio, of the players who have a page."""
    players = db.scalar(select(func.count()).select_from(Player)) or 0
    with_bio = sum(1 for bio in db.scalars(select(PlayerProfile.bio)) if bio and bio.strip())
    share = round(with_bio / players, 4) if players else None
    return [_entry(BIO_RULE) | {"unlocked_share": share, "completed_share": share}]


def player_items(db, user_id: str) -> list[dict]:
    """This player's cards: the bio one is complete once their page has a bio (the date it was last edited)."""
    profile = db.get(PlayerProfile, user_id)
    has_bio = bool(profile and profile.bio and profile.bio.strip())
    return [_entry(BIO_RULE) | {"progress": 1.0 if has_bio else 0.0, "tier": "crown" if has_bio else None,
                                "unlocked_at": profile.updated_at[:10] if has_bio else None}]
