"""Challenges about the player's page rather than their games (user, 2026-11-26: "Edit your Bio", a special; removed and
brought back the same day). Like the Combat challenges they are added to a player's answer apart from the replay ones, and
stay out of every total, the ranking and Medal Collector (counted=False): the replay evaluation is cached per set of games,
and a bio changes without any game."""

from sqlalchemy import func, select

from . import discord_links
from .achievements import Rule
from .models import DiscordProfile, LeagueMember, NakamaAccount, Player, PlayerProfile

GROUP = "Profile"
BIO_RULE = Rule(277, "Edit your Bio", "Write a bio on your player page (log in with Discord, then edit it on your profile)", "game", None,
                lambda games: 0.0, new=True, group=GROUP, counted=False, binary=True)
# Echo Combat George League (user, 2026-11-27): Specials from the league's own site, ecgleague.com, Rookie League only
# (Varsity ignored, user), matched by Discord id (league.py). Ids 280-284 (272 / 276 / 278 are retired ids, never reused).
LEAGUE_GROUP = "George League"


def _league(rule_id: int, name: str, description: str) -> Rule:
    return Rule(rule_id, name, description, "game", None, lambda games: 0.0, new=True, group=LEAGUE_GROUP, counted=False, binary=True)


LEAGUE_RULE = _league(280, "Join Echo Combat George League", "Join the Rookie League of the Echo Combat George League (ecgleague.com): be on a Rookie team or its leaderboard")
LEAGUE_TEAM_RULE = _league(281, "Join a George League Team", "Be on the roster of a George League Rookie team")
LEAGUE_PLAY_RULE = _league(282, "Play a George League Match", "Play a match in the George League's Rookie League")
LEAGUE_WIN_RULE = _league(283, "Win a George League Match", "Win a match in the George League's Rookie League")
LEAGUE_SUB_RULE = _league(284, "Join as a George League Sub", "Sign up as a League Sub who can play in the George League's Rookie League")
# rule -> the LeagueMember column with the date it was first seen
LEAGUE_RULES = {LEAGUE_RULE: "joined_at", LEAGUE_TEAM_RULE: "team_at", LEAGUE_PLAY_RULE: "played_at",
                LEAGUE_WIN_RULE: "won_at", LEAGUE_SUB_RULE: "sub_at"}
PROFILE_RULES = [BIO_RULE, *LEAGUE_RULES]
NOTES = ["On your player page", "Discord login"]
LEAGUE_NOTES = ["Rookie League only, from ecgleague.com, read every hour", "Matched by your Discord account",
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
    # a bio written on My profile by an account without a bot link is kept by Discord id (DiscordProfile)
    own = {d for d, bio in db.execute(select(DiscordProfile.discord_id, DiscordProfile.bio)) if bio and bio.strip()}
    with_bio += len(_with_page(db, own))
    share = round(with_bio / players, 4) if players else None
    # league shares: members who have a player page here, of all players (as for the bio)
    members = {m.discord_id: m for m in db.scalars(select(LeagueMember))}
    here = _with_page(db, set(members))
    out = [_entry(BIO_RULE) | {"unlocked_share": share, "completed_share": share}]
    for rule, column in LEAGUE_RULES.items():
        s = round(sum(1 for d in here if getattr(members[d], column)) / players, 4) if players else None
        out.append(_entry(rule) | {"unlocked_share": s, "completed_share": s})
    return out


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
    once their Discord account was seen doing it in the Rookie League (the date it was first seen, league.py)."""
    profile = db.get(PlayerProfile, user_id)
    linked = discord_links.discord_of(db, discord_links.main_id(db, user_id))
    if not (profile and profile.bio and profile.bio.strip()) and linked:
        # no bot link: the bio written on My profile is kept by Discord id (2026-11-27: it never counted before)
        profile = db.get(DiscordProfile, linked[0]) or profile
    has_bio = bool(profile and profile.bio and profile.bio.strip())
    member = db.get(LeagueMember, linked[0]) if linked else None
    return [_done(_entry(BIO_RULE), profile.updated_at if has_bio else None)] + [
        _done(_entry(rule), getattr(member, column) if member else None) for rule, column in LEAGUE_RULES.items()]
