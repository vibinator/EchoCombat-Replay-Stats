"""Achievements (D17): 5-79 from the old ECRanked stat.js comments, thresholds from the rule text; 80+ are new
(user, 2026-10-30), built on data the old site never used: unreleased gear, results, payload push / block, emotes.
Progress = the best value ever reached (old app only ever raised progress): best game, best calendar
day / week (recorder-local, weeks start Monday), or the all-time total. The logic follows the description shown
on the website (user, 2026-10-30): every condition a rule applies is in its text. Computed from stored match
stats on request; nothing is stored. Tiers (user, 2026-10-30): white 25 %, bronze 50 %, silver 75 %, gold 100 %."""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cached_property

WEAPONS = [("assault", "Pulsar", "pulsar"), ("blaster", "Nova", "nova"), ("scout", "Comet", "comet"), ("rocket", "Meteor", "meteor")]
ORDNANCES = [("det", "Detonator", "detonator"), ("stun", "Stun Field", "stun_field"), ("arc", "Arc Mine", "arcmine"), ("burst", "Instant Repair", "instant_repair")]
TACMODS = [("heal", "Repair Matrix", "repair_matrix"), ("sensor", "Threat Scanner", "threat_scanner"), ("shield", "Energy Barrier", "energy_barrier"), ("wraith", "Phase Shift", "phaseshift")]
SLOTS = {"weapon": 0, "tacmod": 1, "ordnance": 2}  # index into the (weapon, tacmod, ordnance) loadout key
# Unreleased gear seen in recent replays. Attack Drone, Umbral Veil and Neutron are left out: each appears in 35
# games or fewer in the 2026 archive and in none of the 30-31 Oct 2026 replays. Overcharge got a low target (112).
UNRELEASED_WEAPONS = [("rifle", "Starburst"), ("magnum", "Protostar"), ("smg", "Quark"), ("chain", "Blazar")]

ONLY_SHARE = 0.95  # "use only X": X is at least 95 % of the game's loadout time
USED_SHARE = 0.05  # old loadoutCutoff: below 5 % of the time does not count as "used"
FULL_GAME_S = 180.0  # per-game rules ignore short appearances (A: avoids 0-death 10-second games)
LOADOUT_USED_S = 180.0  # "use all 64 loadouts": at least 3 min each (old code: 3*60*30 frames)
SEASON_MIN_GAMES = 50  # all-time averages ramp up over the first 50 games (A)
TIERS = [(1.0, "gold"), (0.75, "silver"), (0.5, "bronze"), (0.25, "white")]


@dataclass
class Game:
    """One match of one player, as needed by the rules."""

    started_at: str
    map: str
    mode: str
    private: bool
    play_time_s: float
    deaths: int
    in_bounds: int
    near_mate: int
    near_enemy: int
    upside: int
    speed_sum: float
    top_speed: float
    frame_rate: float
    loadouts: dict[tuple[str, str, str], int] = field(default_factory=dict)  # (weapon, tacmod, ordnance) -> frames
    # used by the new challenges (80+)
    team: str = ""
    winner: str | None = None  # None = no result (recording ended early)
    attacking_team: str | None = None  # payload only
    rounds_lost: int = 0  # capture point: rounds won by the other team
    push_s: float = 0.0
    block_s: float = 0.0
    emotes: int = 0

    @property
    def won(self) -> bool:
        return self.winner is not None and self.winner == self.team

    @cached_property
    def day(self) -> date:
        return date.fromisoformat(self.started_at[:10])

    @cached_property
    def week(self) -> date:
        return self.day - timedelta(days=self.day.weekday())

    @cached_property
    def _shares(self) -> dict[str, dict[str, float]]:
        """slot -> code -> share of loadout time (computed once; rules ask hundreds of times)."""
        frames: dict[str, dict[str, int]] = {slot: {} for slot in SLOTS}  # plain dicts: built for every game
        for key, n in self.loadouts.items():
            for slot, i in SLOTS.items():
                counts = frames[slot]
                counts[key[i]] = counts.get(key[i], 0) + n
        total = sum(self.loadouts.values())
        return {slot: {c: n / total for c, n in counts.items()} if total else {} for slot, counts in frames.items()}

    def share(self, slot: str, code: str) -> float:
        return self._shares[slot].get(code, 0.0)

    @cached_property
    def _used(self) -> dict[str, frozenset[str]]:
        return {slot: frozenset(c for c, v in shares.items() if c and v >= USED_SHARE) for slot, shares in self._shares.items()}

    def used(self, slot: str) -> frozenset[str]:
        return self._used[slot]

    def main_loadout(self) -> tuple[str, str, str] | None:
        total = sum(self.loadouts.values())
        if not total:
            return None
        key, n = max(self.loadouts.items(), key=lambda kv: kv[1])
        return key if n / total >= ONLY_SHARE else None


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    description: str
    period: str  # game | day | week | all
    icon: str | None  # base name in app/images; daily / weekly variants added by period
    score: Callable[[list[Game]], float]  # games of one period -> progress (0..1+)
    estimated: bool = False
    new: bool = False  # not on the original ECRanked site
    group: str | None = None  # theme of a new rule (its own section on the website)


def clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _only(slot: str, code: str, need: int):
    return lambda games: sum(1 for g in games if g.share(slot, code) >= ONLY_SHARE) / need


def _count(pred, need: int):
    return lambda games: sum(1 for g in games if pred(g)) / need


class _Average:
    """sum(attr) / in-bounds frames over the games, against `target`. With min_games, progress is also
    scaled by games / min_games (the text says "over N+ games")."""

    def __init__(self, attr: str, target: float, min_games: int = 0):
        self.attr, self.target, self.min_games = attr, target, min_games

    def _value(self, total: float, frames: int, n: int) -> float:
        value = ratio(total, frames) / self.target
        if not self.min_games:
            return value
        return clamp(value) * min(1.0, n / self.min_games)  # 100 % needs the 50 games, however high the average

    def __call__(self, games) -> float:
        return self._value(sum(getattr(g, self.attr) for g in games), sum(g.in_bounds for g in games), len(games))

    def first_reached(self, ordered: list) -> int | None:
        """Index of the game at which the running average first reached the target (it can drop again later,
        so the binary search used for counts does not apply)."""
        total = frames = 0
        for i, g in enumerate(ordered):
            total += getattr(g, self.attr)
            frames += g.in_bounds
            if self._value(total, frames, i + 1) >= 1:
                return i
        return None


def _agg_ratio(attr: str, target: float, min_games: int = 0):
    return _Average(attr, target, min_games)


def _avg_speed(target: float, min_games: int = 0):
    return _Average("speed_sum", target, min_games)


def _full(score):
    """Per-game rules: only games played at least FULL_GAME_S."""
    return lambda games: score(games) if games and games[0].play_time_s >= FULL_GAME_S else 0.0


def _gearhead(games):
    """Longest run of consecutive games on one single loadout, out of 25."""
    best = run = 0
    prev = None
    for g in sorted(games, key=lambda g: g.started_at):
        key = g.main_loadout()
        run = run + 1 if key is not None and key == prev else (1 if key else 0)
        prev = key
        best = max(best, run)
    return best / 25


PEW_PEW_MAX_DEATHS = 5  # was 3 in the original text; raised by the user (2026-10-30)


def _pew_pew_proof(games):
    """Average fewer than PEW_PEW_MAX_DEATHS deaths per game over a week with at least 25 games. Exactly the
    limit is not fewer: partial progress stays below 100 % until the average is under it."""
    if not games:
        return 0.0
    avg = sum(g.deaths for g in games) / len(games)
    limit = PEW_PEW_MAX_DEATHS
    return min(1.0, len(games) / 25) * (1.0 if avg < limit else min(limit / avg, 0.99))


def _all_loadouts(games):
    seconds = Counter()
    for g in games:
        for key, frames in g.loadouts.items():
            seconds[key] += frames / (g.frame_rate or 20)
    released = {w for w, _, _ in WEAPONS}, {t for t, _, _ in TACMODS}, {o for o, _, _ in ORDNANCES}
    used = {k for k, s in seconds.items() if s >= LOADOUT_USED_S and all(k[i] in released[i] for i in range(3))}
    return len(used) / 64


def _equipables_used(games):
    used = set()
    for g in games:
        for slot in SLOTS:
            used |= g.used(slot)
    released = {c for c, _, _ in WEAPONS + ORDNANCES + TACMODS}
    return len(used & released) / 12


def _games_using(slot: str, code: str, need: int):
    return lambda games: sum(1 for g in games if code in g.used(slot)) / need


def _all_used(slot: str, codes: set[str]):
    """Share of `codes` used (5%+ of a game) in these games."""
    return lambda games: len(set().union(*(g.used(slot) for g in games)) & codes) / len(codes)


def _win_streak(need: int):
    """Longest run of wins over games with a result, out of `need` (games without a result are skipped)."""
    def score(games):
        best = run = 0
        for g in sorted(games, key=lambda g: g.started_at):
            if g.winner is None:
                continue
            run = run + 1 if g.won else 0
            best = max(best, run)
        return best / need
    return score


def _capture(g):
    return g.mode == "capture_point"


def _payload(g):
    return g.mode == "payload"


def _pub(g):
    return not g.private


def _build_rules() -> list[Rule]:
    rules: list[Rule] = []
    # Daily (5-29)
    names = {
        "assault": "One with the Pulsar", "blaster": "One with the Nova", "scout": "One with the Comet", "rocket": "One with the Meteor",
        "det": "Yeet and Delete", "stun": "Ride the Lightning", "arc": "Paralyzer", "burst": "RAD_DavidN Heal Us w/5th Map",
        "heal": "Damage Control", "sensor": "Search and Destroy", "shield": "n00b Protector 9000", "wraith": "Wraith",
    }
    i = 5
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(Rule(i, names[code], f"Use only {label} for 15+ games in one day", "day", icon, _only(slot, code, 15)))
            i += 1
    rules += [
        Rule(17, "Versatile Bot", "Use all 12 equipables in one day", "day", None, _equipables_used),
        Rule(18, "My Other Chassis Is a Toaster", "Have 3 or fewer deaths in one game (3+ minutes)", "game", "deaths",
             _full(lambda gs: clamp((8 - gs[0].deaths) / 5)), estimated=True),
        Rule(19, "Point Captured", "Play 8+ Capture Point games in one day", "day", "capture_point", _count(_capture, 8)),
        Rule(20, "Checkpoint Reached", "Play 8+ Payload games in one day", "day", "payload", _count(_payload, 8)),
        Rule(21, "Full Team Salvo", "Be near a teammate 50% or more of one game (3+ minutes)", "game", None, _full(_agg_ratio("near_mate", 0.5))),
        Rule(22, "Can We Talk About This?", "Be near an enemy 2% or more of one game (3+ minutes)", "game", None, _full(_agg_ratio("near_enemy", 0.02))),
        Rule(23, "Super Ultra Hyper Turbo", "Hit a top speed of 35 m/s or more in one game", "game", None, lambda gs: gs[0].top_speed / 35),
        Rule(24, "I’m Bat Bot", "Play inverted for 50% or more of one game (3+ minutes)", "game", None, _full(_agg_ratio("upside", 0.5))),
    ]
    for rid, name, m in ((25, "Constant Contesting", "dyson"), (26, "Blast Furnace", "combustion"),
                         (27, "Techneium-99", "fission"), (28, "Bird of Prey", "surge")):
        rules.append(Rule(rid, name, f"Play 4+ games of {m.title()} in one day", "day", m, _count(lambda g, m=m: g.map == m, 4)))
    rules.append(Rule(29, "Combat on Quest When?", "Play 35+ Combat pubs in one day", "day", None, _count(_pub, 35)))

    # Weekly (30-54)
    names = {
        "assault": "Set Phasers to Kill!", "blaster": "Eat My Nova!", "scout": "Silicon Assassin", "rocket": "I Came to Drop Bombs",
        "det": "Throws Better Than an Arena Disc", "stun": "Don't Taze Me Bro Bot", "arc": "Electroshock Therapy", "burst": "Fully Juiced",
        "heal": "Built to Last", "sensor": "X-Ray Vision Implant Upgrade", "shield": "Check Out My Cool Screensaver", "wraith": "Ghost in the Shell",
    }
    i = 30
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(Rule(i, names[code], f"Use only {label} for 20+ games in one week", "week", icon, _only(slot, code, 20)))
            i += 1
    rules += [
        Rule(42, "Gearhead", "Use only one loadout for 25+ games in a row in one week", "week", None, _gearhead),
        Rule(43, "Pew Pew Proof", "Average fewer than 5 deaths per game over a week (25+ games)", "week", "deaths", _pew_pew_proof, estimated=True),
        Rule(44, "I'd Rather Be on Kronos II", "Play 50+ Capture Point games in one week", "week", "capture_point", _count(_capture, 50)),
        Rule(45, "Sakura's Dancing Flamingo", "Play 50+ Payload games in one week", "week", "payload", _count(_payload, 50)),
        Rule(46, "Tech Support w/RAD_Natalie", "Be near a teammate 22% or more over a week", "week", None, _agg_ratio("near_mate", 0.22)),
        Rule(47, "Hug Your Frenemy", "Be near an enemy 2% or more over a week", "week", None, _agg_ratio("near_enemy", 0.02)),
        Rule(48, "The Wings of RAD_Wyvern", "Average speed of 4.5 m/s or more in one week", "week", None, _avg_speed(4.5)),
        Rule(49, "I’ɯ ꓭɐʇ ꓭoʇ", "Play inverted for 15% or more of a week", "week", None, _agg_ratio("upside", 0.15)),
    ]
    for rid, name, m in ((50, "Frame-Drop Hell", "dyson"), (51, "I've Got a Fever, and the Only Prescription Is Pew Pew Pew!", "combustion"),
                         (52, "Phoeniconaias minor", "fission"), (53, "Phoenicopterus ruber", "surge")):
        rules.append(Rule(rid, name, f"Play 8+ games of {m.title()} in one week", "week", m, _count(lambda g, m=m: g.map == m, 8)))
    rules.append(Rule(54, "Who Do I Have to Pew Pew Pew to Get a Combat Update Around Here?",
                      "Play 100+ Combat pubs in one week", "week", None, _count(_pub, 100)))

    # All time (55-79). 55-66 have no title in the old code (A: names generated).
    i = 55
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(Rule(i, f"{label} Veteran", f"Play 100 games using {label}", "all", icon,
                              lambda gs, s=slot, c=code: sum(1 for g in gs if c in g.used(s)) / 100))
            i += 1
    rules += [
        Rule(67, "5th Loadout when? \"Soon™\"", "Use all 64 loadout combinations (3+ minutes each)", "all", None, _all_loadouts),
        Rule(68, "Pixel Party!", "Die 1000+ times", "all", "deaths", lambda gs: sum(g.deaths for g in gs) / 1000, estimated=True),
        Rule(69, "King of the Hill", "Play 50+ Capture Point games", "all", "capture_point", _count(_capture, 50)),
        Rule(70, "Feed the Flamingo", "Play 50+ Payload games", "all", "payload", _count(_payload, 50)),
        Rule(71, "Robot Wrecking Squad", "Be near a teammate 13% or more (all-time average, 50+ games)", "all", None, _agg_ratio("near_mate", 0.13, SEASON_MIN_GAMES)),
        Rule(72, "Roboticide", "Be near an enemy 2% or more (all-time average, 50+ games)", "all", None, _agg_ratio("near_enemy", 0.02, SEASON_MIN_GAMES)),
        Rule(73, "Cyberkinetic Enhancements", "Average speed of 3.5 m/s or more (all-time average, 50+ games)", "all", None, _avg_speed(3.5, SEASON_MIN_GAMES)),
        Rule(74, "toB taB m'I", "Play inverted for 4% or more (all-time average, 50+ games)", "all", None, _agg_ratio("upside", 0.04, SEASON_MIN_GAMES)),
    ]
    for rid, name, m in ((75, "Brute Force Attack", "dyson"), (76, "Molten Mechanical Mayhem", "combustion"),
                         (77, "George and I Go Way Back", "fission"), (78, "Good ol' George", "surge")):
        rules.append(Rule(rid, name, f"Play 40+ games of {m.title()}", "all", m, _count(lambda g, m=m: g.map == m, 40)))
    rules.append(Rule(79, "King/Queen of Pubs", "Play 550+ Combat pubs", "all", None, _count(_pub, 550)))

    # New (80+): data the old site never used.
    names = {"rifle": ("Starburst Beta Tester", 25), "magnum": ("Protostar Prototype", 25),
             "smg": ("Quantum of Quark", 25), "chain": ("Blazar of Glory", 5)}
    i = 80
    for code, label in UNRELEASED_WEAPONS:
        name, need = names[code]
        rules.append(Rule(i, name, f"Play {need}+ games using {label} (unreleased weapon)", "all", None,
                          _games_using("weapon", code, need), new=True, group="Unreleased gear"))
        i += 1
    rules += [
        Rule(84, "Now You See Me", "Play 25+ games using Translocator (unreleased ordnance)", "all", None,
             _games_using("ordnance", "loc", 25), new=True, group="Unreleased gear"),
        Rule(85, "Connect the Dots", "Play 5+ games using Dot Field (unreleased ordnance)", "all", None,
             _games_using("ordnance", "dot", 5), new=True, group="Unreleased gear"),
        Rule(86, "Forbidden Arsenal", "Use all 4 unreleased weapons: Starburst, Protostar, Quark and Blazar", "all", None,
             _all_used("weapon", {c for c, _ in UNRELEASED_WEAPONS}), new=True, group="Unreleased gear"),
        Rule(87, "Jack of All Trades", "Use Pulsar, Nova, Comet and Meteor in one game", "game", None,
             _all_used("weapon", {c for c, _, _ in WEAPONS}), new=True, group="Gear mastery"),
        Rule(88, "Ordnance Sampler", "Use Detonator, Stun Field, Arc Mine and Instant Repair in one game", "game", None,
             _all_used("ordnance", {c for c, _, _ in ORDNANCES}), new=True, group="Gear mastery"),
        Rule(89, "Tac Mod Tinkerer", "Use Repair Matrix, Threat Scanner, Energy Barrier and Phase Shift in one game", "game",
             None, _all_used("tacmod", {c for c, _, _ in TACMODS}), new=True, group="Gear mastery"),
        Rule(90, "On a Roll", "Win 5 games in a row (games without a result are skipped)", "all", None, _win_streak(5), new=True, group="Wins"),
        Rule(91, "Unstoppable", "Win 10 games in a row (games without a result are skipped)", "all", None, _win_streak(10), new=True, group="Wins"),
        Rule(92, "Centurion", "Win 100 games", "all", None, _count(lambda g: g.won, 100), new=True, group="Wins"),
        Rule(93, "Clean Sweep", "Win a Capture Point game 2-0", "game", "capture_point",
             lambda gs: 1.0 if _capture(gs[0]) and gs[0].won and gs[0].rounds_lost == 0 else 0.0, new=True, group="Wins"),
        Rule(94, "Special Delivery", "Win a Payload game as the attacking team", "game", "payload",
             lambda gs: 1.0 if _payload(gs[0]) and gs[0].won and gs[0].attacking_team == gs[0].team else 0.0, new=True, group="Wins"),
        Rule(95, "Hold the Line", "Win a Payload game as the defending team", "game", "payload",
             lambda gs: 1.0 if _payload(gs[0]) and gs[0].won and gs[0].attacking_team not in (None, gs[0].team) else 0.0,
             new=True, group="Wins"),
        Rule(96, "Pedal to the Metal", "Push the payload for 3+ minutes in one game", "game", "payload",
             lambda gs: gs[0].push_s / 180, estimated=True, new=True, group="Payload"),
        Rule(97, "Immovable Object", "Block the payload for 1+ minute in one game", "game", "payload",
             lambda gs: gs[0].block_s / 60, estimated=True, new=True, group="Payload"),
        Rule(98, "Freight Train", "Push the payload for 5+ hours in total", "all", "payload",
             lambda gs: sum(g.push_s for g in gs) / 18000, estimated=True, new=True, group="Payload"),
        Rule(99, "Showboat", "Emote 10+ times in one game", "game", None, lambda gs: gs[0].emotes / 10, new=True, group="Emotes"),
        Rule(100, "Dance Floor Legend", "Emote 500+ times in total", "all", None, lambda gs: sum(g.emotes for g in gs) / 500,
             new=True, group="Emotes"),
    ]

    # Unreleased gear, now in everyday use (user, 2026-10-31): the replays of 30-31 Oct 2026 show Quark in 75 of 84
    # games and Translocator in 74. Targets checked against them: one day of only Translocator reached 8 games.
    now_public = (("weapon", "rifle", "Starburst", "Starburst Stream"), ("weapon", "magnum", "Protostar", "Protostar Power Trip"),
                  ("weapon", "smg", "Quark", "Quark Storm"), ("ordnance", "loc", "Translocator", "Here, There and Everywhere"))
    for i, (slot, code, label, name) in enumerate(now_public, 101):
        rules.append(Rule(i, name, f"Use only {label} for 10+ games in one day", "day", None, _only(slot, code, 10),
                          new=True, group="Unreleased gear"))
    for i, (slot, code, label, _) in enumerate(now_public, 105):
        rules.append(Rule(i, f"{label} Veteran", f"Play 100 games using {label}", "all", None,
                          _games_using(slot, code, 100), new=True, group="Unreleased gear"))
    rules += [
        Rule(109, "Beam Me Up", "Use Translocator and Dot Field in one game", "game", None,
             _all_used("ordnance", {"loc", "dot"}), new=True, group="Unreleased gear"),
        Rule(110, "Arsenal Overload", "Use 6 different weapons in one game", "game", None,
             lambda gs: len(gs[0].used("weapon")) / 6, new=True, group="Gear mastery"),
        Rule(111, "Ordnance Overload", "Use 5 different ordnances in one game", "game", None,
             lambda gs: len(gs[0].used("ordnance")) / 5, new=True, group="Gear mastery"),
        Rule(112, "Overclocked", "Play 5+ games using Overcharge (unreleased tac mod)", "all", None,
             _games_using("tacmod", "buff", 5), new=True, group="Unreleased gear"),
    ]
    return rules


RULES = _build_rules()


def icon_file(rule: Rule) -> str | None:
    """Old badge art: ids 5-29 were the daily set, 30-54 weekly, 55-79 all-time."""
    if rule.icon is None:
        return None
    suffix = "_daily" if rule.id < 30 else "_weekly" if rule.id < 55 else ""
    return f"{rule.icon}{suffix}.png"


def tier(progress: float) -> str | None:
    return next((name for level, name in TIERS if progress >= level), None)


def _groups(games: list[Game], period: str) -> list[list[Game]]:
    if period == "all":
        return [games]
    if period == "game":
        return [[g] for g in games]
    key = (lambda g: g.day) if period == "day" else (lambda g: g.week)
    groups = defaultdict(list)
    for g in games:
        groups[key(g)].append(g)
    return list(groups.values())


def evaluate(games: list[Game]) -> list[dict]:
    """Progress per rule: best period, capped at 1."""
    groups = {p: _groups(games, p) for p in ("game", "day", "week", "all")}
    out = []
    for rule in RULES:
        best = max((rule.score(g) for g in groups[rule.period] if g), default=0.0)
        progress = round(clamp(best), 4)
        out.append({
            "id": rule.id, "name": rule.name, "description": rule.description, "period": rule.period,
            "icon": icon_file(rule), "estimated": rule.estimated, "new": rule.new, "group": rule.group, "progress": progress, "tier": tier(progress),
        })
    return out


def overall(results: list[dict]) -> float:
    return round(sum(r["progress"] for r in results) / len(results), 4) if results else 0.0


def in_window(games: list[Game], start: str | None, end: str | None) -> list[Game]:
    """Challenge period (admin-set, D33): only games started on/after `start` and on/before `end` (dates)."""
    return [g for g in games
            if (not start or g.started_at[:10] >= start) and (not end or g.started_at[:10] <= end)]


def unlock_dates(games: list[Game]) -> dict[int, str]:
    """Date each rule first reached 100 % (ISO date). Game / day / week rules: the earliest group that
    reached it; all-time rules: the first game at which the running total reached it (averages: scanned in
    order, they can go down again; counts only grow, so a binary search finds it)."""
    ordered = sorted(games, key=lambda g: g.started_at)
    groups = {p: _groups(ordered, p) for p in ("game", "day", "week")}
    out: dict[int, str] = {}
    for rule in RULES:
        if rule.period == "all":
            if not ordered or rule.score(ordered) < 1:
                continue
            if isinstance(rule.score, _Average):
                out[rule.id] = ordered[rule.score.first_reached(ordered)].started_at[:10]
                continue
            lo, hi = 1, len(ordered)
            while lo < hi:
                mid = (lo + hi) // 2
                if rule.score(ordered[:mid]) >= 1:
                    hi = mid
                else:
                    lo = mid + 1
            out[rule.id] = ordered[lo - 1].started_at[:10]
        else:
            done = [min(g.started_at for g in group) for group in groups[rule.period] if group and rule.score(group) >= 1]
            if done:
                out[rule.id] = min(done)[:10]
    return out
