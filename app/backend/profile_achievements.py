"""Challenges about the player's page rather than their games (user, 2026-11-26: "Edit your Bio", a special; removed and
brought back the same day). Like the Combat challenges they are added to a player's answer apart from the replay ones, and
stay out of every total, the ranking and Medal Collector (counted=False): the replay evaluation is cached per set of games,
and a bio changes without any game."""

from sqlalchemy import func, select

from . import discord_links
from .achievements import Rule
from .models import LeagueMember, NakamaAccount, Player, PlayerProfile

GROUP = "Profile"
BIO_RULE = Rule(277, "Edit your Bio", "Write a bio on your player page (log in with Discord, then edit it on your profile)", "game", None,
                lambda games: 0.0, new=True, group=GROUP, counted=False, binary=True)
# Echo Combat George League (user, 2026-11-27: two Specials): from the league's own roster at ecgleague.com (league.py), matched
# by Discord id. Ids 280-281 (272 / 276 / 278 are retired ids, never reused).
LEAGUE_GROUP = "George League"
LEAGUE_RULE = Rule(280, "Join Echo Combat George League", "Sign up as a player of the Echo Combat George League at ecgleague.com",
                   "game", None, lambda games: 0.0, new=True, group=LEAGUE_GROUP, counted=False, binary=True)
LEAGUE_TEAM_RULE = Rule(281, "Join a George League Team", "Be on the roster of an Echo Combat George League team",
                        "game", None, lambda games: 0.0, new=True, group=LEAGUE_GROUP, counted=False, binary=True)
PROFILE_RULES = [BIO_RULE, LEAGUE_RULE, LEAGUE_TEAM_RULE]
NOTES = ["On your player page", "Discord login"]
LEAGUE_NOTES = ["From the league's roster at ecgleague.com, read every hour", "Matched by your Discord account",
                "Stays complete if you leave later"]


def _entry(rule: Rule) -> dict:
    notes = LEAGUE_NOTES if rule.group == LEAGUE_GROUP else NOTES
    return {"id": rule.id, "name": rule.name, "description": rule.description, "rules": notes, "period": rule.period,
            "icon": rule.icon, "estimated": False, "new": rule.new, "group": rule.group, "counted": rule.counted, "binary": rule.binary,
            "levels": None, "unit": ""}


def catalogue(db) -> list[dict]:
    """The rule list with rarity: share of players with a bio, of the players who have a page."""
    players = db.scalar(select(func.count()).select_from(Player)) or 0
    with_bio = sum(1 for bio in db.scalars(select(PlayerProfile.bio)) if bio and bio.strip())
    share = round(with_bio / players, 4) if players else None
    # league shares: members who have a player page here, of all players (as for the bio)
    members = {m.discord_id: m.team_at for m in db.scalars(select(LeagueMember))}
    here = _with_page(db, set(members))
    league_share = round(len(here) / players, 4) if players else None
    team_share = round(sum(1 for d in here if members[d]) / players, 4) if players else None
    return [_entry(BIO_RULE) | {"unlocked_share": share, "completed_share": share},
            _entry(LEAGUE_RULE) | {"unlocked_share": league_share, "completed_share": league_share},
            _entry(LEAGUE_TEAM_RULE) | {"unlocked_share": team_share, "completed_share": team_share}]


def _with_page(db, discord_ids: set[str]) -> set[str]:
    """The Discord ids among these that belong to a player here: a bot / admin link, a player whose id IS the Discord id,
    or an Echo account linked to a player (the routes discord_links uses, in three queries instead of one per id)."""
    if not discord_ids:
        return set()
    ids = list(discord_ids)
    found = set(db.scalars(select(PlayerProfile.discord_id).where(PlayerProfile.discord_id.in_(ids))))
    found |= set(db.scalars(select(Player.user_id).where(Player.user_id.in_(ids))))
    found |= set(db.scalars(select(NakamaAccount.discord_id).where(NakamaAccount.discord_id.in_(ids),
                                                                   NakamaAccount.replay_user_id.is_not(None))))
    return found


def _done(entry: dict, at: str | None) -> dict:
    return entry | {"progress": 1.0 if at else 0.0, "tier": "crown" if at else None, "unlocked_at": at[:10] if at else None}


def player_items(db, user_id: str) -> list[dict]:
    """This player's cards: the bio one is complete once their page has a bio (the date it was last edited); the league ones
    once their Discord account is on the league's roster / a team's roster (the date it was first seen there)."""
    profile = db.get(PlayerProfile, user_id)
    has_bio = bool(profile and profile.bio and profile.bio.strip())
    linked = discord_links.discord_of(db, discord_links.main_id(db, user_id))
    member = db.get(LeagueMember, linked[0]) if linked else None
    return [_done(_entry(BIO_RULE), profile.updated_at if has_bio else None),
            _done(_entry(LEAGUE_RULE), member.joined_at if member else None),
            _done(_entry(LEAGUE_TEAM_RULE), member.team_at if member else None)]
