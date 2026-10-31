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
MEDAL_LEVELS = (5, 10, 25, 50, 75)  # Medal Collector: gold-or-better medals held; archive: 36 % bronze, 20 % silver, 11 % gold, 5 % platinum, 1 % diamond
MAPS = ("dyson", "combustion", "fission", "surge")
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
    # Tiered (progression) rules: all-time count targets for bronze, silver, gold, platinum, diamond (LEVELS).
    # The medal is the highest target reached instead of the percentage tiers; diamond = completed.
    levels: tuple[float, ...] = ()
    count: Callable[[list[Game]], float] | None = None  # per period group; the best group counts
    unit: str = ""  # shown after each target ("%", " m/s", " min")
    meta: bool = False  # Medal Collector: counts the medals of the other rules


# Tiered rules (user, 2026-10-31): almost every rule is a ladder. Platinum below diamond, as usual for medal ladders.
LEVELS = ("bronze", "silver", "gold", "platinum", "diamond")


def _levelled(count, levels: tuple[float, ...]):
    """Progress spread evenly over the medals: bronze 20 %, silver 40 %, ... diamond 100 %, partial in between."""
    def score(games):
        n, prev = count(games), 0
        for i, need in enumerate(levels):
            if n < need:
                return (i + (n - prev) / (need - prev)) / len(levels)
            prev = need
        return 1.0
    return score


def level_tier(n: float, levels: tuple[float, ...]) -> str | None:
    reached = sum(n >= need for need in levels)
    return LEVELS[reached - 1] if reached else None


def unlock_threshold(rule: "Rule") -> float:
    """Progress at which a rule counts as unlocked (rarity): the first medal."""
    return 1 / len(rule.levels) if rule.levels else TIERS[-1][0]


def _num(n: float) -> str:
    return f"{n:g}"


def _ladder(id_: int, name: str, what: str, icon: str | None, count, levels: tuple[float, ...], period: str = "all",
            unit: str = "", **kw) -> "Rule":
    """A medal ladder: `count` is evaluated per period group (game / day / week / all time); the best group counts.
    The text lists every target."""
    targets = ", ".join(f"{_num(n)}{unit} {medal}" for n, medal in zip(levels, LEVELS))
    return Rule(id_, name, f"{what} ({targets})", period, icon, _levelled(count, levels), levels=levels, count=count,
                unit=unit, **kw)


def _tiered(id_: int, name: str, what: str, icon: str | None, pred, levels: tuple[float, ...], period: str = "all", **kw) -> "Rule":
    """Ladder over the number of games matching `pred`."""
    return _ladder(id_, name, what, icon, lambda games: sum(1 for g in games if pred(g)), levels, period, **kw)


def clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _only(slot: str, code: str, need: int):
    return lambda games: sum(1 for g in games if g.share(slot, code) >= ONLY_SHARE) / need


def _count(pred, need: int):
    return lambda games: sum(1 for g in games if pred(g)) / need


class _AvgValue:
    """100 x sum(attr) / in-bounds frames over the games (percent), or sum(attr) / frames when scale is 1 (speed).
    0 until min_games games (all-time averages ramp: 50+ games)."""

    def __init__(self, attr: str, scale: float = 100.0, min_games: int = 0):
        self.attr, self.scale, self.min_games = attr, scale, min_games

    def _value(self, total: float, frames: int, n: int) -> float:
        return round(self.scale * ratio(total, frames), 6) if n >= self.min_games else 0.0

    def __call__(self, games) -> float:
        return self._value(sum(getattr(g, self.attr) for g in games), sum(g.in_bounds for g in games), len(games))

    def first_reached(self, ordered: list, need: float) -> int | None:
        """Index of the game at which the running average first reached `need` (it can drop again later, so the
        binary search used for counts does not apply)."""
        total = frames = 0
        for i, g in enumerate(ordered):
            total += getattr(g, self.attr)
            frames += g.in_bounds
            if self._value(total, frames, i + 1) >= need:
                return i
        return None


def _full(value):
    """Per-game rules: only games played at least FULL_GAME_S."""
    return lambda games: value(games) if games and games[0].play_time_s >= FULL_GAME_S else 0.0


def _gearhead_run(games):
    """Longest run of consecutive games on one single loadout."""
    best = run = 0
    prev = None
    for g in sorted(games, key=lambda g: g.started_at):
        key = g.main_loadout()
        run = run + 1 if key is not None and key == prev else (1 if key else 0)
        prev = key
        best = max(best, run)
    return best


PEW_PEW_MAX_DEATHS = 5  # was 3 in the original text; raised by the user (2026-10-30)


def _pew_pew_proof(games):
    """Average fewer than PEW_PEW_MAX_DEATHS deaths per game over a week with at least 25 games. Exactly the
    limit is not fewer: partial progress stays below 100 % until the average is under it."""
    if not games:
        return 0.0
    avg = sum(g.deaths for g in games) / len(games)
    limit = PEW_PEW_MAX_DEATHS
    return min(1.0, len(games) / 25) * (1.0 if avg < limit else min(limit / avg, 0.99))


def _loadouts_used(games):
    """Different released loadouts (of 64) played at least 3 minutes in total."""
    seconds = Counter()
    for g in games:
        for key, frames in g.loadouts.items():
            seconds[key] += frames / (g.frame_rate or 20)
    released = {w for w, _, _ in WEAPONS}, {t for t, _, _ in TACMODS}, {o for o, _, _ in ORDNANCES}
    return len({k for k, s in seconds.items() if s >= LOADOUT_USED_S and all(k[i] in released[i] for i in range(3))})


RELEASED = {c for c, _, _ in WEAPONS + ORDNANCES + TACMODS}


def _equipables_used(games):
    used = set()
    for g in games:
        for slot in SLOTS:
            used |= g.used(slot)
    return len(used & RELEASED)


def _days_all_equipables(games):
    """Days (recorder-local calendar days) on which all 12 released equipables were used."""
    return sum(1 for day in _groups(games, "day") if _equipables_used(day) == 12)


def _games_using(slot: str, code: str):
    return lambda games: sum(1 for g in games if code in g.used(slot))


def _only_games(slot: str, code: str):
    return lambda games: sum(1 for g in games if g.share(slot, code) >= ONLY_SHARE)


def _all_used(slot: str, codes: set[str]):
    """Share of `codes` used (5%+ of a game) in these games."""
    return lambda games: len(set().union(*(g.used(slot) for g in games)) & codes) / len(codes)


def _win_streak(games):
    """Longest run of wins over games with a result (games without a result are skipped)."""
    best = run = 0
    for g in sorted(games, key=lambda g: g.started_at):
        if g.winner is None:
            continue
        run = run + 1 if g.won else 0
        best = max(best, run)
    return best


def _day_streak(games):
    """Longest run of consecutive calendar days with at least one game."""
    best = run = 0
    prev = None
    for day in sorted({g.day for g in games}):
        run = run + 1 if prev is not None and (day - prev).days == 1 else 1
        best, prev = max(best, run), day
    return best


def _fewest_wins(games):
    """Wins on the map where the player has the fewest (all four maps count)."""
    return min(sum(1 for g in games if g.map == m and g.won) for m in MAPS)


def _least_used(slot: str, items):
    return lambda games: min(sum(1 for g in games if code in g.used(slot)) for code, _, _ in items)


def _least_used_equipable(games):
    return min(_least_used(slot, items)(games) for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)))


def _capture(g):
    return g.mode == "capture_point"


def _payload(g):
    return g.mode == "payload"


def _pub(g):
    return not g.private


def _pct(attr: str) -> "_AvgValue":
    return _AvgValue(attr)


def _build_rules() -> list[Rule]:
    rules: list[Rule] = []
    # Daily (5-29): the most games in one calendar day
    names = {
        "assault": "One with the Pulsar", "blaster": "One with the Nova", "scout": "One with the Comet", "rocket": "One with the Meteor",
        "det": "Yeet and Delete", "stun": "Ride the Lightning", "arc": "Paralyzer", "burst": "RAD_DavidN Heal Us w/5th Map",
        "heal": "Damage Control", "sensor": "Search and Destroy", "shield": "n00b Protector 9000", "wraith": "Wraith",
    }
    i = 5
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, names[code], f"Play games using only {label} in one day: the most in a single day counts", icon,
                                 _only_games(slot, code), (3, 6, 10, 15, 20), "day"))
            i += 1
    rules += [
        _ladder(17, "Versatile Bot", "Days on which you used all 12 equipables", None, _days_all_equipables, (1, 3, 10, 25, 50)),
        _tiered(18, "My Other Chassis Is a Toaster", "Games with 3 or fewer deaths (3+ minutes)", "deaths",
                lambda g: g.play_time_s >= FULL_GAME_S and g.deaths <= 3, (1, 5, 15, 50, 250), estimated=True),
        _tiered(19, "Point Captured", "Play Capture Point games in one day: the most in a single day counts", "capture_point", _capture, (4, 6, 8, 12, 20), "day"),
        _tiered(20, "Checkpoint Reached", "Play Payload games in one day: the most in a single day counts", "payload", _payload, (4, 6, 8, 12, 20), "day"),
        _ladder(21, "Full Team Salvo", "Time near a teammate in one game of 3+ minutes: your best game counts", None,
                _full(_pct("near_mate")), (40, 50, 60, 75, 90), "game", "%"),
        _ladder(22, "Can We Talk About This?", "Time near an enemy in one game of 3+ minutes: your best game counts", None,
                _full(_pct("near_enemy")), (2, 15, 30, 50, 75), "game", "%"),
        _ladder(23, "Super Ultra Hyper Turbo", "Top speed reached in one game: your best game counts", None,
                lambda gs: gs[0].top_speed, (13, 17, 21, 25, 30), "game", " m/s"),
        _ladder(24, "I’m Bat Bot", "Time spent inverted in one game of 3+ minutes: your best game counts", None,
                _full(_pct("upside")), (10, 25, 50, 75, 90), "game", "%"),
    ]
    for rid, name, m in ((25, "Constant Contesting", "dyson"), (26, "Blast Furnace", "combustion"),
                         (27, "Techneium-99", "fission"), (28, "Bird of Prey", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()} in one day: the most in a single day counts", m,
                             lambda g, m=m: g.map == m, (2, 3, 4, 6, 10), "day"))
    rules.append(_tiered(29, "Combat on Quest When?", "Play Combat pubs in one day: the most in a single day counts", None, _pub, (10, 15, 20, 30, 40), "day"))

    # Weekly (30-54): the most in one calendar week (Monday start)
    names = {
        "assault": "Set Phasers to Kill!", "blaster": "Eat My Nova!", "scout": "Silicon Assassin", "rocket": "I Came to Drop Bombs",
        "det": "Throws Better Than an Arena Disc", "stun": "Don't Taze Me Bro Bot", "arc": "Electroshock Therapy", "burst": "Fully Juiced",
        "heal": "Built to Last", "sensor": "X-Ray Vision Implant Upgrade", "shield": "Check Out My Cool Screensaver", "wraith": "Ghost in the Shell",
    }
    i = 30
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, names[code], f"Play games using only {label} in one week: the most in a single week counts", icon,
                                 _only_games(slot, code), (5, 10, 15, 30, 50), "week"))
            i += 1
    rules += [
        _ladder(42, "Gearhead", "Games in a row using only one loadout in one week: your best week counts", None, _gearhead_run, (5, 10, 25, 50, 100), "week"),
        Rule(43, "Pew Pew Proof", "Average fewer than 5 deaths per game over a week (25+ games)", "week", "deaths", _pew_pew_proof, estimated=True),
        _tiered(44, "I'd Rather Be on Kronos II", "Play Capture Point games in one week: the most in a single week counts", "capture_point", _capture, (10, 18, 25, 40, 50), "week"),
        _tiered(45, "Sakura's Dancing Flamingo", "Play Payload games in one week: the most in a single week counts", "payload", _payload, (10, 18, 25, 40, 50), "week"),
        _ladder(46, "Tech Support w/RAD_Natalie", "Time near a teammate over one week: your best week counts", None, _pct("near_mate"), (22, 27, 32, 40, 55), "week", "%"),
        _ladder(47, "Hug Your Frenemy", "Time near an enemy over one week: your best week counts", None, _pct("near_enemy"), (10, 15, 20, 30, 50), "week", "%"),
        _ladder(48, "The Wings of RAD_Wyvern", "Average speed over one week: your best week counts", None, _AvgValue("speed_sum", 1.0), (3.5, 4, 4.5, 5, 6), "week", " m/s"),
        _ladder(49, "I’ɯ ꓭɐʇ ꓭoʇ", "Time spent inverted over one week: your best week counts", None, _pct("upside"), (5, 10, 15, 30, 50), "week", "%"),
    ]
    for rid, name, m in ((50, "Frame-Drop Hell", "dyson"), (51, "I've Got a Fever, and the Only Prescription Is Pew Pew Pew!", "combustion"),
                         (52, "Phoeniconaias minor", "fission"), (53, "Phoenicopterus ruber", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()} in one week: the most in a single week counts", m,
                             lambda g, m=m: g.map == m, (4, 6, 8, 16, 30), "week"))
    rules.append(_tiered(54, "Who Do I Have to Pew Pew Pew to Get a Combat Update Around Here?",
                         "Play Combat pubs in one week: the most in a single week counts", None, _pub, (15, 30, 60, 100, 150), "week"))

    # All time (55-79). 55-66 have no title in the old code (A: names generated).
    i = 55
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", icon, _games_using(slot, code), (10, 30, 100, 300, 1000)))
            i += 1
    rules += [
        _ladder(67, "5th Loadout when? \"Soon™\"", "Different loadout combinations used, 3+ minutes each (of 64)", None, _loadouts_used, (8, 16, 32, 48, 64)),
        _ladder(68, "Pixel Party!", "Die in total", "deaths", lambda gs: sum(g.deaths for g in gs), (100, 500, 1000, 5000, 20000), estimated=True),
        _tiered(69, "King of the Hill", "Play Capture Point games", "capture_point", _capture, (10, 25, 50, 250, 1000)),
        _tiered(70, "Feed the Flamingo", "Play Payload games", "payload", _payload, (10, 25, 50, 250, 1000)),
        _ladder(71, "Robot Wrecking Squad", "Time near a teammate, all-time average (50+ games)", None,
                _AvgValue("near_mate", 100.0, SEASON_MIN_GAMES), (14, 16, 19, 22, 25), "all", "%"),
        _ladder(72, "Roboticide", "Time near an enemy, all-time average (50+ games)", None,
                _AvgValue("near_enemy", 100.0, SEASON_MIN_GAMES), (6, 9, 12, 14, 15.5), "all", "%"),
        _ladder(73, "Cyberkinetic Enhancements", "Average speed, all-time average (50+ games)", None,
                _AvgValue("speed_sum", 1.0, SEASON_MIN_GAMES), (2.9, 3.1, 3.3, 3.5, 3.7), "all", " m/s"),
        _ladder(74, "toB taB m'I", "Time spent inverted, all-time average (50+ games)", None,
                _AvgValue("upside", 100.0, SEASON_MIN_GAMES), (2, 4, 8, 30, 60), "all", "%"),
    ]
    for rid, name, m in ((75, "Brute Force Attack", "dyson"), (76, "Molten Mechanical Mayhem", "combustion"),
                         (77, "George and I Go Way Back", "fission"), (78, "Good ol' George", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()}", m, lambda g, m=m: g.map == m, (5, 15, 40, 150, 500)))
    rules.append(_tiered(79, "King/Queen of Pubs", "Play Combat pubs", None, _pub, (25, 100, 250, 550, 2000)))

    # New (80+): data the old site never used.
    starts = {"rifle": ("Starburst Beta Tester", (1, 5, 25, 100, 300)), "magnum": ("Protostar Prototype", (1, 5, 25, 100, 250)),
              "smg": ("Quantum of Quark", (1, 5, 25, 50, 100)), "chain": ("Blazar of Glory", (1, 2, 5, 10, 15))}
    i = 80
    for code, label in UNRELEASED_WEAPONS:
        name, levels = starts[code]
        rules.append(_ladder(i, name, f"Play games using {label} (unreleased weapon)", None, _games_using("weapon", code), levels,
                             new=True, group="Experimental gear"))
        i += 1
    rules += [
        _ladder(84, "Now You See Me", "Play games using Translocator (unreleased ordnance)", None, _games_using("ordnance", "loc"), (1, 5, 25, 50, 100),
                new=True, group="Experimental gear"),
        _ladder(85, "Connect the Dots", "Play games using Dot Field (unreleased ordnance)", None, _games_using("ordnance", "dot"), (1, 2, 5, 10, 20),
                new=True, group="Experimental gear"),
        Rule(86, "Forbidden Arsenal", "Use all 4 unreleased weapons: Starburst, Protostar, Quark and Blazar", "all", None,
             _all_used("weapon", {c for c, _ in UNRELEASED_WEAPONS}), new=True, group="Experimental gear"),
        Rule(87, "Jack of All Trades", "Use Pulsar, Nova, Comet and Meteor in one game", "game", None,
             _all_used("weapon", {c for c, _, _ in WEAPONS}), new=True, group="Gear mastery"),
        Rule(88, "Ordnance Sampler", "Use Detonator, Stun Field, Arc Mine and Instant Repair in one game", "game", None,
             _all_used("ordnance", {c for c, _, _ in ORDNANCES}), new=True, group="Gear mastery"),
        Rule(89, "Tac Mod Tinkerer", "Use Repair Matrix, Threat Scanner, Energy Barrier and Phase Shift in one game", "game",
             None, _all_used("tacmod", {c for c, _, _ in TACMODS}), new=True, group="Gear mastery"),
        _ladder(90, "On a Roll", "Wins in a row (games without a result are skipped)", None, _win_streak, (2, 3, 5, 8, 12), new=True, group="Wins"),
        _ladder(91, "Unstoppable", "Wins in a row (games without a result are skipped)", None, _win_streak, (4, 6, 10, 14, 18), new=True, group="Wins"),
        _tiered(92, "Centurion", "Win games", None, lambda g: g.won, (10, 25, 100, 500, 2000), new=True, group="Wins"),
        # the attacking team wins exactly when the payload reaches the end (stats/payload.py)
        _tiered(93, "Clean Sweep", "Win Capture Point games 2-0", "capture_point",
                lambda g: _capture(g) and g.won and g.rounds_lost == 0, (1, 5, 10, 25, 100), new=True, group="Capture Point"),
        _tiered(94, "Special Delivery", "Deliver the payload to the end: win Payload games as the attacking team", "payload",
                lambda g: _payload(g) and g.won and g.attacking_team == g.team, (1, 5, 10, 25, 100), new=True, group="Payload"),
        _tiered(95, "Hold the Line", "Win Payload games as the defending team", "payload",
                lambda g: _payload(g) and g.won and g.attacking_team not in (None, g.team), (1, 5, 15, 50, 200), new=True, group="Payload"),
        _ladder(96, "Pedal to the Metal", "Time pushing the payload in one game: your best game counts", "payload",
                lambda gs: gs[0].push_s / 60, (1, 2, 3, 4, 6), "game", " min", estimated=True, new=True, group="Payload"),
        _ladder(97, "Immovable Object", "Time blocking the payload in one game: your best game counts", "payload",
                lambda gs: gs[0].block_s / 60, (0.5, 1, 1.5, 2, 3), "game", " min", estimated=True, new=True, group="Payload"),
        _ladder(98, "Freight Train", "Time pushing the payload in total", "payload",
                lambda gs: sum(g.push_s for g in gs) / 60, (10, 30, 60, 300, 900), "all", " min", estimated=True, new=True, group="Payload"),
        _ladder(99, "Showboat", "Emotes in one game: your best game counts", None, lambda gs: gs[0].emotes, (3, 6, 10, 15, 25), "game",
                new=True, group="Emotes"),
        _ladder(100, "Dance Floor Legend", "Emotes in total", None, lambda gs: sum(g.emotes for g in gs), (10, 50, 200, 500, 2000),
                new=True, group="Emotes"),
    ]

    # Unreleased gear, now in everyday use (user, 2026-10-31): the replays of 30-31 Oct 2026 show Quark in 75 of 84
    # games and Translocator in 74.
    now_public = (("weapon", "rifle", "Starburst", "Starburst Stream"), ("weapon", "magnum", "Protostar", "Protostar Power Trip"),
                  ("weapon", "smg", "Quark", "Quark Storm"), ("ordnance", "loc", "Translocator", "Here, There and Everywhere"))
    for i, (slot, code, label, name) in enumerate(now_public, 101):
        rules.append(_ladder(i, name, f"Play games using only {label} in one day: the most in a single day counts", None,
                             _only_games(slot, code), (2, 5, 10, 15, 20), "day", new=True, group="Experimental gear"))
    for i, (slot, code, label, _) in enumerate(now_public, 105):
        rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", None, _games_using(slot, code), (10, 30, 100, 300, 1000),
                             new=True, group="Experimental gear"))
    rules += [
        Rule(109, "Beam Me Up", "Use Translocator and Dot Field in one game", "game", None,
             _all_used("ordnance", {"loc", "dot"}), new=True, group="Experimental gear"),
        Rule(110, "Arsenal Overload", "Use 6 different weapons in one game", "game", None,
             lambda gs: len(gs[0].used("weapon")) / 6, new=True, group="Gear mastery"),
        Rule(111, "Ordnance Overload", "Use 5 different ordnances in one game", "game", None,
             lambda gs: len(gs[0].used("ordnance")) / 5, new=True, group="Gear mastery"),
        _ladder(112, "Overclocked", "Play games using Overcharge (unreleased tac mod)", None, _games_using("tacmod", "buff"), (1, 3, 5, 10, 25),
                new=True, group="Experimental gear"),
    ]

    # New challenges from the 2026-10-31 review (113+). Targets chosen from the archive (docs/Achievement-Tiers-Proposal.MD).
    rules += [
        _ladder(113, "Frequent Flyer", "Games played", None, len, (10, 50, 200, 1000, 5000), new=True, group="Activity"),
        _ladder(114, "Regular", "Different days played", None, lambda gs: len({g.day for g in gs}), (5, 15, 40, 100, 300), new=True, group="Activity"),
        _ladder(115, "Loyal Bot", "Different weeks played", None, lambda gs: len({g.week for g in gs}), (3, 8, 20, 50, 100), new=True, group="Activity"),
        _ladder(116, "Daily Grind", "Days in a row with at least one game played", None, _day_streak, (3, 5, 7, 14, 30), new=True, group="Activity"),
        _ladder(117, "Time Well Wasted", "Hours played", None, lambda gs: sum(g.play_time_s for g in gs) / 3600, (1, 5, 20, 100, 500), "all", " h",
                new=True, group="Activity"),
        _tiered(118, "Overtime", "Games of 10 minutes or longer", None, lambda g: g.play_time_s >= 600, (5, 20, 50, 250, 1000), new=True, group="Activity"),
        _tiered(119, "Hot Day", "Win games in one day: the most in a single day counts", None, lambda g: g.won, (3, 5, 8, 12, 20), "day", new=True, group="Wins"),
        _tiered(120, "Point Taker", "Win Capture Point games", "capture_point", lambda g: _capture(g) and g.won, (3, 10, 30, 100, 400), new=True, group="Capture Point"),
        _tiered(121, "Cargo Hauler", "Win Payload games", "payload", lambda g: _payload(g) and g.won, (3, 10, 30, 100, 400), new=True, group="Payload"),
        _ladder(122, "Grand Tour", "Wins on each of the 4 maps (the map with the fewest wins counts)", None, _fewest_wins, (1, 5, 15, 50, 150),
                new=True, group="Wins"),
        _ladder(123, "Weapons Master", "Games with your least-used weapon of Pulsar, Nova, Comet and Meteor", None, _least_used("weapon", WEAPONS),
                (1, 5, 15, 50, 150), new=True, group="Gear mastery"),
        _ladder(124, "Loadout Scholar", "Games with your least-used equipable of all 12 weapons, ordnances and tac mods", None, _least_used_equipable,
                (1, 5, 15, 50, 100), new=True, group="Gear mastery"),
        _ladder(125, "Wall of Steel", "Time blocking the payload in total", "payload", lambda gs: sum(g.block_s for g in gs) / 60, (2, 10, 30, 60, 120),
                "all", " min", estimated=True, new=True, group="Payload"),
        # Medal Collector counts the other rules' medals; filled in by evaluate() (meta)
        _ladder(126, "Medal Collector", "Gold medals or better held across the other challenges", None, lambda gs: 0.0, MEDAL_LEVELS,
                new=True, group="Activity", meta=True),
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


def _reached_gold(entry: dict, rule: Rule) -> bool:
    """Medal Collector: a ladder counts from gold (third medal) on, a single-step rule when completed."""
    return entry["count"] >= rule.levels[2] if rule.levels else entry["progress"] >= 1


def evaluate(games: list[Game]) -> list[dict]:
    """Progress per rule: best period, capped at 1. Ladders also report the best count per period group."""
    groups = {p: _groups(games, p) for p in ("game", "day", "week", "all")}
    entries: dict[int, dict] = {}
    for rule in RULES:
        if rule.meta:
            continue
        n = None
        if rule.levels:  # ladder: the best count over the period groups (once: progress follows from it)
            n = max((rule.count(g) for g in groups[rule.period] if g), default=0)
            best = _levelled(lambda _, n=n: n, rule.levels)([])
        else:
            best = max((rule.score(g) for g in groups[rule.period] if g), default=0.0)
        progress = round(clamp(best), 4)
        entry = {
            "id": rule.id, "name": rule.name, "description": rule.description, "period": rule.period,
            "icon": icon_file(rule), "estimated": rule.estimated, "new": rule.new, "group": rule.group, "progress": progress, "tier": tier(progress),
        }
        if n is not None:  # the website shows "12 / 25 for platinum"
            entry |= {"tier": level_tier(n, rule.levels), "count": round(n, 2), "levels": list(rule.levels), "unit": rule.unit}
        entries[rule.id] = entry
    for rule in RULES:
        if rule.meta:
            n = sum(1 for r in RULES if not r.meta and _reached_gold(entries[r.id], r))
            progress = round(clamp(_levelled(lambda _: n, rule.levels)([])), 4)
            entries[rule.id] = {
                "id": rule.id, "name": rule.name, "description": rule.description, "period": rule.period, "icon": icon_file(rule),
                "estimated": False, "new": rule.new, "group": rule.group, "progress": progress, "tier": level_tier(n, rule.levels),
                "count": n, "levels": list(rule.levels), "unit": rule.unit,
            }
    return [entries[rule.id] for rule in RULES]


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
        if rule.meta:
            continue
        if rule.period == "all":
            if not ordered or rule.score(ordered) < 1:
                continue
            if isinstance(rule.count, _AvgValue):
                out[rule.id] = ordered[rule.count.first_reached(ordered, rule.levels[-1])].started_at[:10]
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
