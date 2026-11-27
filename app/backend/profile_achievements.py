"""Challenges about the player's page rather than their games (user, 2026-11-26: "Edit your Bio", a special; removed and
brought back the same day). They are added to a player's answer apart from the replay ones; "Edit your Bio" stays out of
every total, the ranking and Medal Collector (counted=False): the replay evaluation is cached per set of games, and a bio
changes without any game. The George League ones count as full challenges (user, 2026-11-27), and so do the Combat ones
(user, 2026-11-27: "Make Combat count"): they are put on top of the cached answers when looked at (counted_answer,
with_league)."""

from sqlalchemy import func, select

from . import aliases, discord_links
from .achievements import RULES, Rule, _levelled, _reached_gold, clamp, level_tier
from .combat_achievements import COMBAT_RULES
from .models import DiscordProfile, LeagueMember, NakamaAccount, Player, PlayerProfile

GROUP = "Profile"
BIO_RULE = Rule(277, "Edit your Bio", "Write a bio on your player page (log in with Discord, then edit it on your profile)", "game", None,
                lambda games: 0.0, new=True, group=GROUP, counted=False, binary=True)
# Echo Combat George League (user, 2026-11-27): Specials from the league's own site, ecgleague.com, Rookie League only
# (Varsity ignored, user), matched by Discord id (league.py). Ids 280-284 (272 / 276 / 278 are retired ids, never reused).
LEAGUE_GROUP = "George League"


def _league(rule_id: int, name: str, description: str) -> Rule:
    # full challenges (user, 2026-11-27: "make it count as a full challenge"): in the bar, the totals, the ranking and
    # Medal Collector. Added to the replay answer on every look (counted_answer, with_league), never cached with it.
    return Rule(rule_id, name, description, "game", None, lambda games: 0.0, new=True, group=LEAGUE_GROUP, counted=True, binary=True)


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


# --- the George League cards as full challenges (user, 2026-11-27) ---------------------------------------------------
# The replay answer and the ranking are cached per set of games; the league is read every hour without any game. So
# the league cards are put on top of them when they are looked at: they add to the total, the completed count and
# the average, and a won card is one more challenge for Medal Collector.

# The Combat challenges count the same way (user, 2026-11-27: "Make Combat count"): from the recorder's reports, cached
# apart from the replay answer and only added to it here, never mixed into the replay evaluation.
EXTRA_RULES = [*LEAGUE_RULES, *COMBAT_RULES]  # put on top of the replay answer, in this order
COUNTED_RULES = [*RULES, *EXTRA_RULES]  # the rules behind a ranking row's progress list (with_league), in this order
_EXTRA_BY_ID = {r.id: r for r in EXTRA_RULES}
_COLLECTOR = next(i for i, r in enumerate(RULES) if r.meta)  # Medal Collector
_COLLECTOR_RULE = RULES[_COLLECTOR]


def _collector(n: float) -> float:
    return round(clamp(_levelled(lambda _: n, _COLLECTOR_RULE.levels)([])), 4)


def _collector_count(progress: float) -> float:
    """Medal Collector's count back from its progress (the ranking keeps progress only): exact for whole counts below
    the crown; at the crown more cannot change anything."""
    levels = _COLLECTOR_RULE.levels
    x = progress * len(levels)
    i = int(x + 1e-6)
    if i >= len(levels):
        return levels[-1]
    prev = levels[i - 1] if i else 0
    return round(prev + max(0.0, x - i) * (levels[i] - prev))


def counted_answer(result: dict, items: list[dict]) -> tuple[dict, list[dict]]:
    """One player's answer with the league cards in its totals and Medal Collector (new dicts: `result` and its items
    are the cached ones)."""
    league = [i for i in items if i["id"] in _EXTRA_BY_ID and i.get("counted")]  # the league and Combat cards
    won = sum(1 for i in league if i["progress"] >= 1)
    collected = sum(1 for i in league if _reached_gold(i, _EXTRA_BY_ID[i["id"]]))  # Medal Collector: a ladder from silver on
    old = new = 0.0
    if collected:
        for k, item in enumerate(items):
            if item["id"] == _COLLECTOR_RULE.id and "count" in item:
                n = item["count"] + collected
                old, new = item["progress"], _collector(n)
                items = items[:k] + [item | {"count": n, "progress": new, "tier": level_tier(n, _COLLECTOR_RULE.levels)}] + items[k + 1:]
                break
    total = result["total"] + len(league)
    summed = result["overall"] * result["total"] - old + new + sum(i["progress"] for i in league)
    return result | {"total": total, "completed": result["completed"] + won + (new >= 1 > old),
                     "overall": round(summed / total, 4) if total else 0.0}, items


def league_progress(db) -> dict[int, list[float]]:
    """player row id -> progress of each league card (LEAGUE_RULES order), for the members who have a player page here:
    the same Discord account their page shows (player_items). Merged ids all get it (the ranking is per row)."""
    out: dict[int, list[float]] = {}
    for member in db.scalars(select(LeagueMember)):
        values = [1.0 if getattr(member, column) else 0.0 for column in LEAGUE_RULES.values()]
        if not any(values):
            continue
        main = discord_links.player_of(db, member.discord_id)
        if main is None:
            continue
        linked = discord_links.discord_of(db, main)
        if not linked or linked[0] != member.discord_id:
            continue
        for pid in db.scalars(select(Player.id).where(Player.user_id.in_(aliases.ids_of(db, main)))):
            out[pid] = values
    return out


def combat_progress(db, combat: dict) -> dict[int, tuple[list[float], int, int, bool]]:
    """player row id -> (progress of each Combat card in COMBAT_RULES order, how many count for Medal Collector, counted
    Combat games, whether the row is the main one of a merged player), from combat_achievements.everyone(). Every row of
    a merged player gets the cards (the replay ranking is per row, like the league cards)."""
    players, merged = combat["players"], combat["aliases"]
    out: dict[int, tuple[list[float], int, int, bool]] = {}
    for pid, user_id in db.execute(select(Player.id, Player.user_id)):
        main = merged.get(user_id, user_id)
        p = players.get(main)
        if p is not None:
            results = p["results"]
            out[pid] = ([r["progress"] for r in results],
                        sum(1 for r, rule in zip(results, COMBAT_RULES) if _reached_gold(r, rule)), len(p["games"]),
                        main == user_id)
    return out


def with_league(data: dict, extra: dict[int, list[float]], combat: dict[int, tuple[list[float], int, int, bool]] | None = None) -> dict:
    """The ranking ({"rows": [(player row id, games, overall)], "progress": {id: [per RULES]}, ...}) with the league and
    Combat cards appended to every progress list (COUNTED_RULES order) and in every average and Medal Collector. A player
    with Combat reports but no replay game in the period joins it, with their Combat games as `games`."""
    combat = combat or {}
    none = [0.0] * len(LEAGUE_RULES)
    no_combat = ([0.0] * len(COMBAT_RULES), 0, 0, True)
    total = len(RULES)
    progress, rows = {}, []
    listed = data["rows"]
    have = {pid for pid, _, _ in listed}
    joining = [pid for pid, c in combat.items() if pid not in have and c[2] and c[3]]  # the main row only: listed once
    if joining:
        blank = [0.0] * len(RULES)
        # no replay game: the replay cards at 0 (Medal Collector too, before the Combat ones), ranked by the Combat games
        listed = [*listed, *((pid, combat[pid][2], 0.0) for pid in joining)]
        data = data | {"progress": {**data["progress"], **{pid: blank for pid in joining}}}
    for pid, games, overall in listed:
        values = data["progress"][pid]
        cards, collected, _, _ = combat.get(pid, no_combat)
        league = [*extra.get(pid, none), *cards]
        won = sum(1 for v in extra.get(pid, none) if v >= 1) + collected  # Medal Collector: league won, Combat from silver on
        if won:
            values = list(values)
            old = values[_COLLECTOR]
            values[_COLLECTOR] = _collector(_collector_count(old) + won)
            overall = overall * total - old + values[_COLLECTOR]
        else:
            overall = overall * total
        progress[pid] = [*values, *league]
        rows.append((pid, games, round((overall + sum(league)) / (total + len(league)), 4)))
    return data | {"rows": rows, "progress": progress}
