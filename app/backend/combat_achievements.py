"""Combat achievements (user, 2026-11-05): built only from the recorder's match reports (combat_matches, combat_players), kept
completely apart from the replay data and from RULES. They use the same medal engine and show on the same Achievements page, but
they never read a replay table, and the replay-based overall %, totals, rankings and Medal Collector never count them.

What counts is judged from the report itself: 4+ minutes present and 3+ players per team (each there for at least half of the
match), the same limits as the replay rules. The challenge period applies too. Merged accounts (player_aliases) add up.

Targets are PROVISIONAL (user, 2026-11-05: "we will work on this as more data comes in"). One-game and one-day targets come from
about one day of reports (4-5 Nov 2026), near what the top 40 / 20 / 12 / 7.5 / 5 % reached, rounded up as bests rise over time;
all-time targets are estimates from that pace. Assists are always above kills. Left out: eliminations (always kills + assists) and
hill captures (always 0). Heal bubbles and stuns come from complete event logs only, which matches have had since 5 Nov 2026 18:15:
those targets rest on 9 matches. See docs/CombatStats.MD."""

import json
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cached_property
from itertools import groupby

from sqlalchemy import func, select

from .achievements import FULL_GAME_S, Rule, _ladder, _tuned, evaluate, icon_file, in_window, medal_times, rule_notes, unlock_dates, unlock_threshold
from .aliases import alias_map
from .models import CombatFile, CombatMatch, CombatPlayer

GROUP = "Combat"
MIN_PER_TEAM = 3
RARITY_MIN_GAMES = 10
RECENT_DAYS = 30


@dataclass
class CombatGame:
    """One counted match of one player, from the report."""

    started_at: str
    kills: int
    assists: int
    deaths: int
    damage: float
    objective_eliminations: int
    objective_time: float
    top_fragger: bool  # the most kills of anyone in the match (a tie counts for everyone in it)
    objective_damage: float = 0.0
    heal_bubbles: int = 0  # 0 when the match has no complete event log
    stuns_given: int = 0  # same
    awards: tuple[str, ...] = ()  # the end-of-match award cards this player won ("mvp", "guard" ...); () when unknown or none

    @cached_property
    def day(self) -> date:
        return date.fromisoformat(self.started_at[:10])

    @cached_property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.started_at)


def _total(value):
    """Sum of value(game): one game, one day or all time, depending on the rule's period."""
    def total(games):
        return sum(value(g) for g in games)
    total.min_length = total.enough_players = True  # shown as rule notes; load_games only keeps games that meet them
    return total


def _awards(*cards: str):
    """Number of award cards won in a game (any card, or only the named ones)."""
    return lambda g: sum(1 for a in g.awards if not cards or a in cards)


def _rule(id_: int, name: str, what: str, icon: str | None, value, levels: tuple[float, ...], period: str, unit: str = "") -> Rule:
    return _tuned(_ladder(id_, name, what, icon, _total(value), levels, period, unit, new=True, group=GROUP, counted=False), levels)


COMBAT_RULES: list[Rule] = [
    _rule(164, "Chassis Crusher (Combat)", "Get kills in one game", "deaths", lambda g: g.kills, (8, 11, 13, 15, 18), "game"),
    _rule(165, "Wingbot", "Get assists in one game", "team_proximity", lambda g: g.assists, (10, 13, 15, 18, 21), "game"),
    _rule(166, "Hull Breach (Combat)", "Deal damage in one game", "enemy_proximity", lambda g: g.damage, (1300, 1750, 2050, 2400, 2800), "game"),
    _rule(167, "Net Positive Bot (Combat)", "Finish one game with more kills than deaths (kills minus deaths)", "deaths", lambda g: max(0, g.kills - g.deaths), (3, 6, 8, 11, 13), "game"),
    _rule(168, "Point Denied (Combat)", "Get objective eliminations in one game", None, lambda g: g.objective_eliminations, (8, 12, 14, 16, 18), "game"),
    _rule(169, "Parked on the Point (Combat)", "Spend time on the objective yourself in one game, in seconds", None, lambda g: g.objective_time, (115, 165, 195, 210, 225), "game", " s"),
    Rule(170, "Flawless Chassis (Combat)", "Get 10 or more kills in one game without dying", "game", "deaths", _total(lambda g: g.kills >= 10 and g.deaths == 0), new=True, group=GROUP, counted=False),
    _rule(171, "Kill Spree Bot (Combat)", "Get kills in one day", "deaths", lambda g: g.kills, (15, 28, 35, 50, 75), "day"),
    _rule(172, "Helping Hands of Kronos II (Combat)", "Get assists in one day", "team_proximity", lambda g: g.assists, (18, 33, 42, 60, 90), "day"),
    _rule(173, "Ring Debris (Combat)", "Total kills", "deaths", lambda g: g.kills, (50, 150, 350, 700, 1200), "all"),
    _rule(174, "The Whole Echo Crew (Combat)", "Total assists", "team_proximity", lambda g: g.assists, (60, 180, 420, 840, 1440), "all"),
    _rule(175, "Kronos II Salvage (Combat)", "Total damage dealt", "enemy_proximity", lambda g: g.damage, (8000, 25000, 60000, 120000, 200000), "all"),
    _rule(176, "Top Bot (Combat)", "Games where you got the most kills in the match (a tie counts)", None, lambda g: g.top_fragger, (3, 12, 30, 60, 100), "all"),
    _rule(177, "Saturn Trifecta (Combat)", "Games with at least 5 kills, 5 assists and 5 objective eliminations", None,
          lambda g: min(g.kills, g.assists, g.objective_eliminations) >= 5, (3, 10, 25, 50, 90), "all"),
    _rule(178, "Service Android (Combat)", "Games with at least 8 assists and at least twice as many assists as kills", "team_proximity",
          lambda g: g.assists >= 8 and g.assists >= 2 * g.kills, (1, 5, 12, 25, 45), "all"),
    _rule(198, "Siege Breaker Bot (Combat)", "Deal objective damage in one game", None, lambda g: g.objective_damage, (500, 900, 1300, 1700, 2000), "game"),
    _rule(199, "Repair Matrix Medic (Combat)", "Use heal bubbles in one game", None, lambda g: g.heal_bubbles, (2, 4, 6, 7, 9), "game"),
    _rule(200, "Stun Field Trooper (Combat)", "Stun enemies in one game", None, lambda g: g.stuns_given, (1, 2, 3, 4, 5), "game"),
    # Second set (user, 2026-11-09: new one game / one day / one month / all-time Combat challenges; "the top should be 10%
    # achievable"). From 435 reports (4-9 Nov 2026), the 42 players with 10+ counted games (the site's rarity group): the crown is
    # what the top 10 % of them reached in one game / one day, and their pace since their first game x30 (any 30 days) or x90
    # (all time, ~3 months, as for gear Veteran). Lower medals keep the ladder's shape. Re-check as players' pace settles.
    # Removed (user, 2026-11-09, too repetitive): 211 (30-day damage), 212 (30-day objective eliminations), 216 (all-time objective
    # eliminations), 218 (all-time objective damage). Over 30+ days these totals move with kills / damage (0.98-0.99), so they
    # added nothing. Their ids stay unused.
    # Names (user, 2026-11-09): from Ready At Dawn, Lone Echo, Echo VR and Echo Combat (Jack, Captain Liv Rhodes, Kronos II, the maps).
    # In one game
    _rule(202, "Jack's Toolkit", "Get kills, assists and objective eliminations in one game (counts the lowest of the three)", None,
          lambda g: min(g.kills, g.assists, g.objective_eliminations), (6, 9, 11, 13, 15), "game"),
    _rule(203, "Ghost of Sparta", "Get kills in one game while dying 3 times or fewer", "deaths",
          lambda g: g.kills if g.deaths <= 3 else 0, (4, 8, 10, 12, 15), "game"),
    # In one day
    _rule(204, "Wrath of Saturn", "Deal damage in one day", "enemy_proximity", lambda g: g.damage, (3000, 5000, 9000, 14000, 20000), "day"),
    _rule(205, "Fission Reaction", "Get objective eliminations in one day", None, lambda g: g.objective_eliminations, (19, 31, 52, 84, 115), "day"),
    _rule(206, "Camping Out on Dyson", "Spend time on the objective yourself in one day, in minutes", None, lambda g: g.objective_time / 60,
          (2, 4, 6, 11, 16), "day", " min"),
    _rule(207, "Keeping Liv Alive", "Use heal bubbles in one day", "repair_matrix", lambda g: g.heal_bubbles, (6, 12, 22, 35, 50), "day"),
    _rule(208, "Spontaneous Combustion", "Games in one day where you got the most kills in the match (a tie counts)", None, lambda g: g.top_fragger,
          (1, 2, 3, 4, 5), "day"),
    # In any 7 days (user, 2026-11-10: the 30-day set became the first Combat 7-day challenges, targets = the old ones x 7/30;
    # the month period stays supported in the code but no challenge uses it, so its page is hidden)
    _rule(209, "Power Surge", "Get kills in any 7 days", "deaths", lambda g: g.kills, (30, 75, 150, 260, 370), "week"),
    _rule(210, "Captain Rhodes' Right Hand", "Get assists in any 7 days", "team_proximity", lambda g: g.assists, (35, 85, 170, 300, 420), "week"),
    _rule(213, "Lobby Billboard", "Games in any 7 days where you got the most kills in the match (a tie counts)", None, lambda g: g.top_fragger,
          (1, 3, 5, 8, 14), "week"),
    _rule(214, "Above the Rings", "Games in any 7 days with more kills than deaths", "deaths", lambda g: g.kills > g.deaths, (2, 5, 10, 19, 30), "week"),
    _rule(215, "Kronos II Medbay", "Use heal bubbles in any 7 days", "repair_matrix", lambda g: g.heal_bubbles, (8, 23, 47, 77, 115), "week"),
    # Award cards (user, 2026-11-10): one set per card of the game's end-of-match cards. A player wins at most one card per game
    # (checked on 154 matches), so there is no "in one game" version. Targets: the top 10 % of the 31 players with 10+ games with
    # cards (4-9 Nov 2026): all time = their pace x 15 (~3 months), any 7 days = their 6 days x 7/6, one day = their best day.
    # A period is only made where that crown is 3 or more: one day only MVP, any 7 days MVP / Guard / Medic. The rare cards
    # (fewer than 10 of the 31 regular players have won one: Tank, Sniper, Cannoneer, Controller, Assassin, Renegade, Defender) are one game only (user, 2026-11-10); so are Super Star, Shock
    # Trooper, Infiltrator and Immovable Object (2-11 winners so far, re-check as more reports come in).
    # Ids 222-232 (an earlier "any card" / collector set, never released) stay unused.
    _rule(233, "Most Valuable Jack (Leaderboard)", "Win the MVP card in one day", None, _awards("mvp"), (1, 2, 3, 4, 5), "day"),
    _rule(234, "Jack of the Week (Leaderboard)", "Win the MVP card in any 7 days", None, _awards("mvp"), (3, 6, 9, 12, 16), "week"),
    _rule(235, "Lone Echo MVP (Leaderboard)", "Total MVP cards won (the highest score in a match)", None, _awards("mvp"), (8, 30, 70, 130, 210), "all"),
    _rule(236, "Guard Duty on Kronos II (Leaderboard)", "Win the Guard card in any 7 days (the most time on the objective in a match)", None, _awards("guard"), (1, 1, 2, 3, 4), "week"),
    _rule(237, "Dyson Sentinel (Leaderboard)", "Total Guard cards won (the most time on the objective in a match)", None, _awards("guard"), (3, 9, 18, 30, 45), "all"),
    _rule(238, "Repair Matrix on Call (Leaderboard)", "Win the Medic card in any 7 days (the most healing in a match)", None, _awards("medic"), (1, 1, 2, 3, 4), "week"),
    _rule(239, "Repair Matrix Veteran (Leaderboard)", "Total Medic cards won (the most healing in a match)", None, _awards("medic"), (3, 9, 18, 30, 45), "all"),
    _rule(240, "Saturn Specialist (Leaderboard)", "Total Specialist cards won (the most assists in a match)", None, _awards("specialist"), (2, 6, 12, 20, 30), "all"),
    _rule(242, "Pulsar Hot Shot (Leaderboard)", "Total Hot Shot cards won (the longest elimination streak in a match)", None, _awards("hot_shot"), (2, 6, 12, 20, 30), "all"),
    # One game: each card can be won once per game, so one medal each (user, 2026-11-10; like Flawless Chassis)
    Rule(249, "MVP of Echo Combat (Leaderboard)", "Win the MVP card in one game (the highest score in the match)", "game", None, _total(lambda g: "mvp" in g.awards), new=True, group=GROUP, counted=False),
    Rule(250, "Standing Guard on Kronos II (Leaderboard)", "Win the Guard card in one game (the most time on the objective)", "game", None, _total(lambda g: "guard" in g.awards), new=True, group=GROUP, counted=False),
    Rule(251, "Echo Combat Specialist (Leaderboard)", "Win the Specialist card in one game (the most assists)", "game", None, _total(lambda g: "specialist" in g.awards), new=True, group=GROUP, counted=False),
    Rule(252, "Repair Matrix Rescue (Leaderboard)", "Win the Medic card in one game (the most healing)", "game", None, _total(lambda g: "medic" in g.awards), new=True, group=GROUP, counted=False),
    Rule(253, "Detonator Strike (Leaderboard)", "Win the Cannoneer card in one game (the most damage dealt)", "game", None, _total(lambda g: "cannoneer" in g.awards), new=True, group=GROUP, counted=False),
    Rule(254, "Saturn Hull Plating (Leaderboard)", "Win the Tank card in one game (the most damage absorbed)", "game", None, _total(lambda g: "tank" in g.awards), new=True, group=GROUP, counted=False),
    Rule(255, "Pulsar Streak (Leaderboard)", "Win the Hot Shot card in one game (the longest elimination streak)", "game", None, _total(lambda g: "hot_shot" in g.awards), new=True, group=GROUP, counted=False),
    Rule(256, "Dyson Defender (Leaderboard)", "Win the Defender card in one game (the most eliminations on the objective)", "game", None, _total(lambda g: "defender" in g.awards), new=True, group=GROUP, counted=False),
    Rule(257, "Nova Strike (Leaderboard)", "Win the Assassin card in one game (the most kills)", "game", None, _total(lambda g: "assassin" in g.awards), new=True, group=GROUP, counted=False),
    Rule(258, "Comet Headhunter (Leaderboard)", "Win the Sniper card in one game (the most headshot kills)", "game", None, _total(lambda g: "sniper" in g.awards), new=True, group=GROUP, counted=False),
    Rule(259, "Lone Wolf of Kronos II (Leaderboard)", "Win the Renegade card in one game (the most solo kills)", "game", None, _total(lambda g: "renegade" in g.awards), new=True, group=GROUP, counted=False),
    Rule(260, "Stun Field Lockdown (Leaderboard)", "Win the Controller card in one game (the most damage to enemies on the objective)", "game", None, _total(lambda g: "controller" in g.awards), new=True, group=GROUP, counted=False),
    Rule(261, "Super Star (Leaderboard)", "Win the Super Star card in one game (the most eliminations, kills and assists together)", "game", None, _total(lambda g: "super_star" in g.awards), new=True, group=GROUP, counted=False),
    Rule(262, "Kronos II Shock Trooper (Leaderboard)", "Win the Shock Trooper card in one game (the most enemies stunned)", "game", None, _total(lambda g: "shock_trooper" in g.awards), new=True, group=GROUP, counted=False),
    Rule(263, "Capture Point Infiltrator (Leaderboard)", "Win the Infiltrator card in one game (the most hill captures, Capture Point maps)", "game", None, _total(lambda g: "infiltrator" in g.awards), new=True, group=GROUP, counted=False),
    Rule(264, "Immovable Object on Dyson (Leaderboard)", "Win the Immovable Object card in one game (the most hill defends, Capture Point maps)", "game", None, _total(lambda g: "immovable_object" in g.awards), new=True, group=GROUP, counted=False),
    # All time
    _rule(217, "The Anomaly Doesn't Move", "Total time on the objective yourself, in minutes", None, lambda g: g.objective_time / 60, (18, 72, 180, 360, 650), "all", " min"),
    _rule(219, "Life Support Systems", "Total heal bubbles used", "repair_matrix", lambda g: g.heal_bubbles, (64, 190, 480, 960, 1600), "all"),
    _rule(220, "Old Arena Habits", "Total enemies stunned", "stun_field", lambda g: g.stuns_given, (7, 22, 56, 110, 200), "all"),
    _rule(221, "Ready At Dawn", "Games with more kills than deaths", "deaths", lambda g: g.kills > g.deaths, (13, 51, 130, 230, 380), "all"),
]


def _card_list(raw) -> list[str]:
    """The award symbols of a player row (JSON list; NULL = unknown counts as none)."""
    try:
        cards = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [c for c in cards if isinstance(c, str)]


def load_games(db, aliases: dict[str, str]) -> tuple[dict[str, list[CombatGame]], dict[str, str]]:
    """(main user id -> counted games, oldest first; main user id -> latest name). Reads the combat tables only."""
    rows = db.execute(
        select(CombatMatch.id, CombatMatch.started_at, CombatMatch.duration_s, CombatMatch.has_events, CombatMatch.events_complete,
               CombatPlayer.user_id, CombatPlayer.name, CombatPlayer.team,
               CombatPlayer.present_s, CombatPlayer.kills, CombatPlayer.assists, CombatPlayer.deaths, CombatPlayer.damage,
               CombatPlayer.objective_eliminations, CombatPlayer.objective_time, CombatPlayer.objective_damage,
               CombatPlayer.heal_bubbles, CombatPlayer.stuns_given, CombatPlayer.awards)
        .join(CombatMatch, CombatMatch.id == CombatPlayer.match_id)
        .order_by(CombatMatch.started_at, CombatMatch.id))
    games: dict[str, list[CombatGame]] = defaultdict(list)
    names: dict[str, str] = {}
    for _, match in groupby(rows, key=lambda r: r[0]):
        # main id -> [team, present, kills, assists, deaths, damage, objective eliminations, objective time, objective damage, heal bubbles, stuns]
        merged: dict[str, list] = {}
        won: dict[str, list[str]] = {}
        for _, started, duration, has_events, complete, user_id, name, team, present, *numbers, heals, stuns, awards in match:
            logged = has_events and complete is True  # an incomplete log counts too little: left out, as FORMATS.md advises
            numbers = [*numbers, (heals or 0) if logged else 0, (stuns or 0) if logged else 0]
            main = aliases.get(user_id, user_id)
            names[main] = name
            won.setdefault(main, []).extend(_card_list(awards))
            have = merged.get(main)
            merged[main] = [team, present, *numbers] if have is None else [have[0], max(have[1], present), *(a + b for a, b in zip(have[2:], numbers))]
        teams = Counter(m[0] for m in merged.values() if m[1] >= 0.5 * duration)
        if teams["blue"] < MIN_PER_TEAM or teams["orange"] < MIN_PER_TEAM:
            continue
        most = max(m[2] for m in merged.values())
        for main, m in merged.items():
            if m[1] >= FULL_GAME_S:
                games[main].append(CombatGame(started, *m[2:8], top_fragger=m[2] > 0 and m[2] == most,
                                              objective_damage=m[8], heal_bubbles=m[9], stuns_given=m[10], awards=tuple(won[main])))
    return games, names


def _player(games: list[CombatGame]) -> dict:
    results = evaluate(games, COMBAT_RULES)
    unlocked = unlock_dates(games, COMBAT_RULES)
    for r in results:
        r["unlocked_at"] = unlocked.get(r["id"])
    return {"games": games, "results": results, "medals": medal_times(games, COMBAT_RULES)}


_lock = threading.Lock()
_cache: dict[int, tuple[tuple, dict]] = {}  # id(sessions) -> (key, data)
_EMPTY = _player([])


def _everyone(sessions, window: tuple) -> dict:
    """Everyone's results, rebuilt when a report is read, a merge changes or the challenge period changes. A player whose counted
    games did not change keeps their results, so a new report only evaluates the players in it."""
    with sessions() as db:
        aliases = alias_map(db)
        read = tuple(db.execute(select(func.count(), func.max(CombatFile.processed_at)).where(CombatFile.status == "done")).one())
        key = (read, window, frozenset(aliases.items()))
        with _lock:
            cached = _cache.get(id(sessions))
            if cached and cached[0] == key:
                return cached[1]
            previous = cached[1]["players"] if cached else {}
            games, names = load_games(db, aliases)
            players = {}
            for user_id, all_games in games.items():
                counted = in_window(all_games, *window)
                if counted:
                    old = previous.get(user_id)
                    players[user_id] = old if old and old["games"] == counted else _player(counted)
            data = {"players": players, "names": names, "aliases": aliases}
            _cache[id(sessions)] = (key, data)
            return data


def player_items(sessions, window: tuple, user_id: str) -> list[dict]:
    """The Combat cards of one player's page, in the same form as the replay ones."""
    data = _everyone(sessions, window)
    return data["players"].get(data["aliases"].get(user_id, user_id), _EMPTY)["results"]


def player_name(sessions, window: tuple, user_id: str) -> str | None:
    """The name in the reports: a player can be in them without having a replay. None = not in any report."""
    data = _everyone(sessions, window)
    return data["names"].get(data["aliases"].get(user_id, user_id))


def catalogue(sessions, window: tuple) -> list[dict]:
    """The rule list with rarity: share of players with RARITY_MIN_GAMES+ counted games who unlocked / completed each."""
    eligible = [p["results"] for p in _everyone(sessions, window)["players"].values() if len(p["games"]) >= RARITY_MIN_GAMES]
    out = []
    for i, r in enumerate(COMBAT_RULES):
        values = [results[i]["progress"] for results in eligible]
        out.append({"id": r.id, "name": r.name, "description": r.description, "rules": rule_notes(r), "period": r.period,
                    "icon": icon_file(r), "estimated": r.estimated, "new": r.new, "group": r.group, "counted": r.counted,
                    "levels": list(r.levels) or None, "unit": r.unit,
                    "unlocked_share": round(sum(v >= unlock_threshold(r) for v in values) / len(values), 4) if values else None,
                    "completed_share": round(sum(v >= 1 for v in values) / len(values), 4) if values else None})
    return out


def recent(sessions, window: tuple) -> list[dict]:
    """Every Combat medal earned in the last RECENT_DAYS of the reports, newest first, in the form of the replay medal feed."""
    data = _everyone(sessions, window)
    latest = max((p["games"][-1].started_at for p in data["players"].values()), default=None)
    if latest is None:
        return []
    cutoff = (date.fromisoformat(latest[:10]) - timedelta(days=RECENT_DAYS)).isoformat()
    rules = {r.id: r for r in COMBAT_RULES}
    events = []
    for user_id, p in data["players"].items():
        for rule_id, medals in p["medals"].items():
            for medal, at in medals.items():
                if at[:10] >= cutoff:
                    rule = rules[rule_id]
                    events.append({"date": at[:10], "at": at, "user_id": user_id, "name": data["names"].get(user_id, "Unknown"), "id": rule_id, "medal": medal,
                                   "achievement": rule.name, "description": rule.description, "icon": icon_file(rule)})
    events.sort(key=lambda e: e["at"], reverse=True)
    return events
