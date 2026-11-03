"""Achievements (D17): 5-79 from the old ECRanked stat.js comments, thresholds from the rule text; 80+ are new
(user, 2026-10-30), built on data the old site never used: unreleased gear, results, payload push / block, emotes.
Progress = the best value ever reached (old app only ever raised progress): best game, best calendar
day (recorder-local), best rolling 7 days (any 7-day window, Beta 69), or the all-time total. The logic follows the description shown
on the website (user, 2026-10-30): every condition a rule applies is in its text. Computed from stored match
stats on request; nothing is stored. Tiers (user, 2026-10-30): white 25 %, bronze 50 %, silver 75 %, gold 100 %."""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property

WEAPONS = [("assault", "Pulsar", "pulsar"), ("blaster", "Nova", "nova"), ("scout", "Comet", "comet"), ("rocket", "Meteor", "meteor")]
ORDNANCES = [("det", "Detonator", "detonator"), ("stun", "Stun Field", "stun_field"), ("arc", "Arc Mine", "arcmine"), ("burst", "Instant Repair", "instant_repair")]
TACMODS = [("heal", "Repair Matrix", "repair_matrix"), ("sensor", "Threat Scanner", "threat_scanner"), ("shield", "Energy Barrier", "energy_barrier"), ("wraith", "Phase Shift", "phaseshift")]
SLOTS = {"weapon": 0, "tacmod": 1, "ordnance": 2}  # index into the (weapon, tacmod, ordnance) loadout key
# Unreleased gear seen in recent replays. Attack Drone, Umbral Veil and Neutron are left out: each appears in 35
# games or fewer in the 2026 archive and in none of the 30-31 Oct 2026 replays. Overcharge got a low target (112).
MEDAL_LEVELS = (5, 10, 25, 50, 75)  # Medal Collector: gold-or-better medals held; archive: 36 % bronze, 20 % silver, 11 % gold, 5 % diamond, 1 % platinum
MAPS = ("dyson", "combustion", "fission", "surge")
UNRELEASED_WEAPONS = [("rifle", "Starburst"), ("magnum", "Protostar"), ("smg", "Quark"), ("chain", "Blazar")]
# Badge art for the gear released 2026-10-30 (made from the loadout icons in public/icons). Dot Field and Overcharge
# have no art yet: they keep the generic icon (an admin can pick or upload one on the Console page).
GEAR_ICONS = {"rifle": "starburst", "magnum": "protostar", "smg": "quark", "chain": "blazar", "loc": "translocator"}

ONLY_SHARE = 0.95  # "use only X": X is at least 95 % of the game's loadout time
USED_SHARE = 0.05  # old loadoutCutoff: below 5 % of the time does not count as "used"
FULL_GAME_S = 180.0  # per-game rules ignore short appearances (A: avoids 0-death 10-second games)
LOADOUT_USED_S = 180.0  # "use all 64 loadouts": at least 3 min each (old code: 3*60*30 frames)
SEASON_MIN_GAMES = 50  # all-time averages need 50 games (A)
SPEED_MIN_GAMES = 25  # Cyberkinetic Enhancements: 50 left 76 % of the active players out (user, 2026-10-31)
# One ladder per kind of gear challenge, the same for every weapon, ordnance and tac mod, new gear included (user,
# 2026-11-03). Set from the most-used gear (Pulsar, ~110k games in the archive): 500 games was out of reach in the last 500.
GEAR_VETERAN = (5, 15, 50, 150, 350)  # games using it
GEAR_DAY = (3, 6, 10, 15, 20)  # "only X" games in one day
GEAR_WEEK = (5, 10, 15, 30, 50)  # "only X" games in any 7 days
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
    stopped: int = 0  # in-bounds frames standing still
    left_arm: int = 0
    right_arm: int = 0
    capture_s: float = 0.0  # capture point: time the player's team's progress was rising
    contested_s: float = 0.0
    four_v_four: bool = True  # both teams had 4 players for at least half of the match; the one-game challenges need it

    @property
    def won(self) -> bool:
        return self.winner is not None and self.winner == self.team

    @cached_property
    def day(self) -> date:
        return date.fromisoformat(self.started_at[:10])

    @cached_property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.started_at)

    @cached_property
    def week(self) -> date:  # calendar week: only "Different weeks played" uses it
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

    @cached_property
    def _only(self) -> dict[str, frozenset[str]]:
        """slot -> codes that are at least ONLY_SHARE of the game's loadout time ("use only")."""
        return {slot: frozenset(c for c, v in shares.items() if c and v >= ONLY_SHARE) for slot, shares in self._shares.items()}

    def share(self, slot: str, code: str) -> float:
        return self._shares[slot].get(code, 0.0)

    @cached_property
    def _used(self) -> dict[str, frozenset[str]]:
        return {slot: frozenset(c for c, v in shares.items() if c and v >= USED_SHARE) for slot, shares in self._shares.items()}

    def used(self, slot: str) -> frozenset[str]:
        return self._used[slot]

    def loadouts_played(self) -> int:
        """Different loadout combinations that were at least USED_SHARE of the game."""
        total = sum(self.loadouts.values())
        return sum(1 for n in self.loadouts.values() if total and n / total >= USED_SHARE)

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
    # Tiered (progression) rules: all-time count targets for bronze, silver, gold, diamond, platinum (LEVELS).
    # The medal is the highest target reached instead of the percentage tiers; platinum = completed.
    levels: tuple[float, ...] = ()
    count: Callable[[list[Game]], float] | None = None  # per period group; the best group counts
    unit: str = ""  # shown after each target ("%", " m/s", " min")
    meta: bool = False  # Medal Collector: counts the medals of the other rules


# Tiered rules (user, 2026-10-31): almost every rule is a ladder. Order (user, 2026-10-31): bronze, silver, gold, diamond, platinum (platinum is the top medal).
LEVELS = ("bronze", "silver", "gold", "diamond", "platinum")


def _levelled(count, levels: tuple[float, ...]):
    """Progress spread evenly over the medals: bronze 20 %, silver 40 %, ... platinum 100 %, partial in between."""
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


HARDER_TOP = 1.3  # diamond and platinum need 30 % more than the targets written below (user, 2026-11-03)


def _harder(levels: tuple[float, ...], unit: str) -> tuple[float, ...]:
    """Diamond and platinum (the last two targets) x HARDER_TOP. A percentage cannot pass 100: it only closes 30 % of
    the way to 100 when that is less. Whole-number targets stay whole and always rise by at least one step."""
    whole = all(float(v).is_integer() for v in levels)
    out = list(levels)
    for i in (3, 4):
        v = levels[i] * HARDER_TOP
        if unit == "%":
            v = min(v, levels[i] + 0.3 * (100 - levels[i]))
        v = float(int(v + 0.5)) if whole else round(v, 1)
        out[i] = max(v, out[i - 1] + (1 if whole else 0.1))
    return tuple(int(v) if whole else v for v in out)


def _ladder(id_: int, name: str, what: str, icon: str | None, count, levels: tuple[float, ...], period: str = "all",
            unit: str = "", **kw) -> "Rule":
    """A medal ladder: `count` is evaluated per period group (game / day / week / all time); the best group counts.
    The text lists every target. Diamond and platinum are made harder by _harder."""
    levels = _harder(levels, unit)
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
    """Average fewer than PEW_PEW_MAX_DEATHS deaths per game over any 7 days with at least 25 games. Exactly the
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
    return lambda games: sum(1 for g in games if code in g._used[slot])


def _only_games(slot: str, code: str):
    return lambda games: sum(1 for g in games if code in g._only[slot])


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


def _v4(count):
    """One-game challenges (139+) only count 4v4 games (user, 2026-11-03)."""
    def only_4v4(games):
        games = [g for g in games if g.four_v_four]
        return count(games) if games else 0.0
    return only_4v4


def _away_from_mates(games):
    """% of the in-bounds time not near a teammate (3+ minute games only, see _full)."""
    return 100.0 - _pct("near_mate")(games) if games[0].in_bounds else 0.0


def _both_arms(games):
    g = games[0]
    return 1.0 if g.in_bounds and min(g.left_arm, g.right_arm) / g.in_bounds >= 0.4 else 0.0


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
                                 _only_games(slot, code), GEAR_DAY, "day"))
            i += 1
    rules += [
        _ladder(17, "Versatile Bot", "Days on which you used all 12 equipables", None, _days_all_equipables, (1, 2, 4, 8, 15)),
        _tiered(18, "My Other Chassis Is a Toaster", "Games with 3 or fewer deaths (3+ minutes)", "deaths",
                lambda g: g.play_time_s >= FULL_GAME_S and g.deaths <= 3, (1, 5, 15, 50, 150), estimated=True),
        _tiered(19, "Point Captured", "Play Capture Point games in one day: the most in a single day counts", "capture_point", _capture, (4, 6, 8, 12, 20), "day"),
        _tiered(20, "Checkpoint Reached", "Play Payload games in one day: the most in a single day counts", "payload", _payload, (4, 6, 8, 12, 20), "day"),
        _ladder(21, "Full Team Salvo", "Time near a teammate in one game of 3+ minutes: your best game counts", "team_proximity",
                _full(_pct("near_mate")), (45, 55, 65, 80, 92), "game", "%"),
        _ladder(22, "Can We Talk About This?", "Time near an enemy in one game of 3+ minutes: your best game counts", "enemy_proximity",
                _full(_pct("near_enemy")), (10, 25, 40, 55, 75), "game", "%"),
        _ladder(23, "Super Ultra Hyper Turbo", "Top speed reached in one game: your best game counts", "speed",
                lambda gs: gs[0].top_speed, (14, 18, 22, 27, 32), "game", " m/s"),
        _ladder(24, "I’m Bat Bot", "Time spent inverted in one game of 3+ minutes: your best game counts", "inverted",
                _full(_pct("upside")), (15, 30, 55, 80, 92), "game", "%"),
    ]
    for rid, name, m in ((25, "Constant Contesting", "dyson"), (26, "Blast Furnace", "combustion"),
                         (27, "Techneium-99", "fission"), (28, "Bird of Prey", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()} in one day: the most in a single day counts", m,
                             lambda g, m=m: g.map == m, (3, 5, 7, 10, 14), "day"))
    rules.append(_tiered(29, "Combat on Quest When?", "Play Combat pubs in one day: the most in a single day counts", "pubs", _pub, (8, 12, 16, 24, 32), "day"))  # 20 % lower (user, 2026-11-03)

    # Weekly (30-54): the most in one calendar week (Monday start)
    names = {
        "assault": "Set Phasers to Kill!", "blaster": "Eat My Nova!", "scout": "Silicon Assassin", "rocket": "I Came to Drop Bombs",
        "det": "Throws Better Than an Arena Disc", "stun": "Don't Taze Me Bro Bot", "arc": "Electroshock Therapy", "burst": "Fully Juiced",
        "heal": "Built to Last", "sensor": "X-Ray Vision Implant Upgrade", "shield": "Check Out My Cool Screensaver", "wraith": "Ghost in the Shell",
    }
    i = 30
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, names[code], f"Play games using only {label} in any 7 days: the most in any 7 days counts", icon,
                                 _only_games(slot, code), GEAR_WEEK, "week"))
            i += 1
    rules += [
        _ladder(42, "Gearhead", "Games in a row using only one loadout in any 7 days: your best 7 days count", "loadout", _gearhead_run, (4, 8, 15, 30, 50), "week"),
        Rule(43, "Pew Pew Proof", "Average fewer than 5 deaths per game over any 7 days (25+ games)", "week", "deaths", _pew_pew_proof, estimated=True),
        _tiered(44, "I'd Rather Be on Kronos II", "Play Capture Point games in any 7 days: the most in any 7 days counts", "capture_point", _capture, (10, 18, 25, 40, 50), "week"),
        _tiered(45, "Sakura's Dancing Flamingo", "Play Payload games in any 7 days: the most in any 7 days counts", "payload", _payload, (10, 18, 25, 40, 50), "week"),
        _ladder(46, "Tech Support w/RAD_Natalie", "Time near a teammate over any 7 days: your best 7 days count", "team_proximity", _pct("near_mate"), (22, 27, 32, 40, 55), "week", "%"),
        _ladder(47, "Hug Your Frenemy", "Time near an enemy over any 7 days: your best 7 days count", "enemy_proximity", _pct("near_enemy"), (15, 20, 25, 35, 50), "week", "%"),
        _ladder(48, "The Wings of RAD_Wyvern", "Average speed over any 7 days: your best 7 days count", "speed", _AvgValue("speed_sum", 1.0), (3.5, 4, 4.5, 5, 6), "week", " m/s"),
        _ladder(49, "I’ɯ ꓭɐʇ ꓭoʇ", "Time spent inverted over any 7 days: your best 7 days count", "inverted", _pct("upside"), (5, 10, 15, 30, 50), "week", "%"),
    ]
    for rid, name, m in ((50, "Frame-Drop Hell", "dyson"), (51, "I've Got a Fever, and the Only Prescription Is Pew Pew Pew!", "combustion"),
                         (52, "Phoeniconaias minor", "fission"), (53, "Phoenicopterus ruber", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()} in any 7 days: the most in any 7 days counts", m,
                             lambda g, m=m: g.map == m, (4, 6, 8, 16, 30), "week"))
    rules.append(_tiered(54, "Who Do I Have to Pew Pew Pew to Get a Combat Update Around Here?",
                         "Play Combat pubs in any 7 days: the most in any 7 days counts", "pubs", _pub, (15, 30, 60, 100, 150), "week"))

    # All time (55-79). 55-66 have no title in the old code (A: names generated).
    i = 55
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", icon, _games_using(slot, code), GEAR_VETERAN))
            i += 1
    rules += [
        _ladder(67, "5th Loadout when? \"Soon™\"", "Different loadout combinations used, 3+ minutes each (of 64)", "loadout", _loadouts_used, (6, 12, 24, 40, 56)),
        _ladder(68, "Pixel Party!", "Total deaths across all your games", "deaths", lambda gs: sum(g.deaths for g in gs), (100, 300, 750, 2000, 4000), estimated=True),
        _tiered(69, "King of the Hill", "Play Capture Point games", "capture_point", _capture, (10, 25, 50, 100, 250)),
        _tiered(70, "Feed the Flamingo", "Play Payload games", "payload", _payload, (10, 25, 50, 100, 250)),
        _ladder(71, "Robot Wrecking Squad", "Time near a teammate, all-time average (50+ games)", "team_proximity",
                _AvgValue("near_mate", 100.0, SEASON_MIN_GAMES), (14, 15.5, 17, 19.5, 22.5), "all", "%"),
        _ladder(72, "Roboticide", "Time near an enemy, all-time average (50+ games)", "enemy_proximity",
                _AvgValue("near_enemy", 100.0, SEASON_MIN_GAMES), (6, 8, 10, 12.5, 15), "all", "%"),
        _ladder(73, "Cyberkinetic Enhancements", "Average speed, all-time average (25+ games)", "speed",
                _AvgValue("speed_sum", 1.0, SPEED_MIN_GAMES), (2.6, 2.8, 3.0, 3.2, 3.5), "all", " m/s"),
        _ladder(74, "toB taB m'I", "Time spent inverted, all-time average (50+ games)", "inverted",
                _AvgValue("upside", 100.0, SEASON_MIN_GAMES), (2, 4, 8, 20, 40), "all", "%"),
    ]
    for rid, name, m in ((75, "Brute Force Attack", "dyson"), (76, "Molten Mechanical Mayhem", "combustion"),
                         (77, "George and I Go Way Back", "fission"), (78, "Good ol' George", "surge")):
        rules.append(_tiered(rid, name, f"Play games of {m.title()}", m, lambda g, m=m: g.map == m, (5, 10, 25, 75, 150)))
    rules.append(_tiered(79, "King/Queen of Pubs", "Play Combat pubs", "pubs", _pub, (25, 75, 150, 250, 400)))

    # New (80+): data the old site never used.
    starts = {"rifle": ("Starburst Beta Tester", (1, 5, 25, 50, 100)), "magnum": ("Protostar Prototype", (1, 5, 25, 50, 100)),
              "smg": ("Quantum of Quark", (1, 5, 25, 50, 100)), "chain": ("Blazar of Glory", (1, 5, 25, 50, 100))}
    i = 80
    for code, label in UNRELEASED_WEAPONS:
        name, levels = starts[code]
        rules.append(_ladder(i, name, f"Play games using {label} (experimental weapon)", GEAR_ICONS[code], _games_using("weapon", code), levels,
                             new=True, group="Experimental gear"))
        i += 1
    rules += [
        _ladder(84, "Now You See Me", "Play games using Translocator (experimental ordnance)", "translocator", _games_using("ordnance", "loc"), (1, 5, 25, 50, 100),
                new=True, group="Experimental gear"),
        _ladder(85, "Connect the Dots", "Play games using Dot Field (experimental ordnance)", None, _games_using("ordnance", "dot"), (1, 5, 25, 50, 100),
                new=True, group="Experimental gear"),
        Rule(86, "Forbidden Arsenal", "Use all 4 experimental weapons: Starburst, Protostar, Quark and Blazar", "all", "loadout",
             _all_used("weapon", {c for c, _ in UNRELEASED_WEAPONS}), new=True, group="Experimental gear"),
        Rule(87, "Jack of All Trades", "Use Pulsar, Nova, Comet and Meteor in one game", "game", "loadout",
             _all_used("weapon", {c for c, _, _ in WEAPONS}), new=True, group="Gear mastery"),
        Rule(88, "Ordnance Sampler", "Use Detonator, Stun Field, Arc Mine and Instant Repair in one game", "game", "loadout",
             _all_used("ordnance", {c for c, _, _ in ORDNANCES}), new=True, group="Gear mastery"),
        Rule(89, "Tac Mod Tinkerer", "Use Repair Matrix, Threat Scanner, Energy Barrier and Phase Shift in one game", "game",
             "loadout", _all_used("tacmod", {c for c, _, _ in TACMODS}), new=True, group="Gear mastery"),
        _ladder(90, "On a Roll", "Win games in a row (games without a result are skipped)", None, _win_streak, (2, 3, 5, 8, 12), new=True, group="Wins"),
        _ladder(91, "Unstoppable", "Win games in a row (games without a result are skipped)", None, _win_streak, (4, 6, 8, 10, 12), new=True, group="Wins"),
        _tiered(92, "Centurion", "Win games", None, lambda g: g.won, (5, 10, 30, 100, 250), new=True, group="Wins"),
        # the attacking team wins exactly when the payload reaches the end (stats/payload.py)
        _tiered(93, "Clean Sweep", "Win Capture Point games 2-0", "capture_point",
                lambda g: _capture(g) and g.won and g.rounds_lost == 0, (1, 5, 10, 25, 100), new=True, group="Capture Point"),
        _tiered(94, "Special Delivery", "Deliver the payload to the end: win Payload games as the attacking team", "payload",
                lambda g: _payload(g) and g.won and g.attacking_team == g.team, (1, 5, 10, 25, 60), new=True, group="Payload"),
        _tiered(95, "Hold the Line", "Win Payload games as the defending team", "payload",
                lambda g: _payload(g) and g.won and g.attacking_team not in (None, g.team), (1, 5, 10, 25, 60), new=True, group="Payload"),
        _ladder(96, "Pedal to the Metal", "Time pushing the payload in one game: your best game counts", "payload",
                lambda gs: gs[0].push_s / 60, (1, 2, 3, 4, 6), "game", " min", estimated=True, new=True, group="Payload"),
        _ladder(97, "Immovable Object", "Time blocking the payload in one game: your best game counts", "payload",
                lambda gs: gs[0].block_s / 60, (0.5, 1, 1.5, 2, 3), "game", " min", estimated=True, new=True, group="Payload"),
        _ladder(98, "Freight Train", "Time pushing the payload in total", "payload",
                lambda gs: sum(g.push_s for g in gs) / 60, (10, 30, 60, 150, 300), "all", " min", estimated=True, new=True, group="Payload"),
        _ladder(99, "Showboat", "Emotes in one game: your best game counts", None, lambda gs: gs[0].emotes, (12, 24, 40, 60, 100), "game",  # emotes are easy: x4 (user, 2026-11-03)
                new=True, group="Emotes"),
        _ladder(100, "Dance Floor Legend", "Emotes in total", None, lambda gs: sum(g.emotes for g in gs), (40, 200, 800, 2000, 8000),  # x4 (user, 2026-11-03)
                new=True, group="Emotes"),
    ]

    # Unreleased gear, now in everyday use (user, 2026-10-31): the replays of 30-31 Oct 2026 show Quark in 75 of 84
    # games and Translocator in 74.
    now_public = (("weapon", "rifle", "Starburst", "Starburst Stream"), ("weapon", "magnum", "Protostar", "Protostar Power Trip"),
                  ("weapon", "smg", "Quark", "Quark Storm"), ("ordnance", "loc", "Translocator", "Here, There and Everywhere"))
    for i, (slot, code, label, name) in enumerate(now_public, 101):
        rules.append(_ladder(i, name, f"Play games using only {label} in one day: the most in a single day counts", GEAR_ICONS[code],
                             _only_games(slot, code), GEAR_DAY, "day", new=True, group="Experimental gear"))
    for i, (slot, code, label, _) in enumerate(now_public, 105):
        rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", GEAR_ICONS[code], _games_using(slot, code),
                             GEAR_VETERAN,  # released 2026-10-30: the same ladder as the older gear (user, 2026-10-31)
                             new=True, group="Experimental gear"))
    rules += [
        Rule(109, "Beam Me Up", "Use Translocator and Dot Field in one game", "game", "translocator",
             _all_used("ordnance", {"loc", "dot"}), new=True, group="Experimental gear"),
        Rule(110, "Arsenal Overload", "Use 5 different weapons in one game", "game", None,
             lambda gs: len(gs[0].used("weapon")) / 5, new=True, group="Gear mastery"),
        Rule(111, "Ordnance Overload", "Use 5 different ordnances in one game", "game", None,
             lambda gs: len(gs[0].used("ordnance")) / 5, new=True, group="Gear mastery"),
        _ladder(112, "Overclocked", "Play games using Overcharge (experimental tac mod)", None, _games_using("tacmod", "buff"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
    ]

    # New challenges from the 2026-10-31 review (113+). Targets chosen from the archive (docs/Achievement-Tiers-Proposal.MD).
    rules += [
        _ladder(113, "Frequent Flyer", "Games played", None, len, (10, 50, 150, 300, 500), new=True, group="Activity"),
        _ladder(114, "Regular", "Different days played", None, lambda gs: len({g.day for g in gs}), (5, 15, 30, 60, 100), new=True, group="Activity"),
        _ladder(115, "Loyal Bot", "Different weeks played", None, lambda gs: len({g.week for g in gs}), (3, 6, 9, 12, 15), new=True, group="Activity"),
        _ladder(116, "Daily Grind", "Days in a row with at least one game played", None, _day_streak, (3, 5, 7, 14, 30), new=True, group="Activity"),
        _ladder(117, "Time Well Wasted", "Hours played", None, lambda gs: sum(g.play_time_s for g in gs) / 3600, (1, 5, 20, 50, 80), "all", " h",
                new=True, group="Activity"),
        _tiered(118, "Overtime", "Games of 10 minutes or longer", None, lambda g: g.play_time_s >= 600, (5, 20, 50, 100, 250), new=True, group="Activity"),
        _tiered(119, "Hot Day", "Win games in one day: the most in a single day counts", None, lambda g: g.won, (3, 5, 8, 12, 16), "day", new=True, group="Wins"),
        _tiered(120, "Point Taker", "Win Capture Point games", "capture_point", lambda g: _capture(g) and g.won, (5, 10, 30, 80, 150), new=True, group="Capture Point"),
        _tiered(121, "Cargo Hauler", "Win Payload games", "payload", lambda g: _payload(g) and g.won, (5, 10, 30, 80, 150), new=True, group="Payload"),
        _ladder(122, "Grand Tour", "Wins on each of the 4 maps (the map with the fewest wins counts)", None, _fewest_wins, (1, 3, 8, 25, 75),
                new=True, group="Wins"),
        _ladder(123, "Weapons Master", "Games with your least-used weapon of Pulsar, Nova, Comet and Meteor", "loadout", _least_used("weapon", WEAPONS),
                (1, 5, 15, 50, 100), new=True, group="Gear mastery"),
        _ladder(124, "Loadout Scholar", "Games with your least-used equipable of all 12 weapons, ordnances and tac mods", None, _least_used_equipable,
                (1, 5, 15, 50, 100), new=True, group="Gear mastery"),
        _ladder(125, "Wall of Steel", "Time blocking the payload in total", "payload", lambda gs: sum(g.block_s for g in gs) / 60, (2, 10, 30, 60, 120),
                "all", " min", estimated=True, new=True, group="Payload"),
        # Medal Collector counts the other rules' medals; filled in by evaluate() (meta)
        _ladder(126, "Medal Collector", "Gold medals or better held across the other challenges", None, lambda gs: 0.0, MEDAL_LEVELS,
                new=True, group="Activity", meta=True),
    ]
    # Gear released on 2026-10-30 gets what the older gear has: "only X" in a week (127-130) and Overcharge in a day / week
    # (131-132), on the same ladders (user, 2026-10-31: estimated, the archive holds little of it yet).
    weekly = (("weapon", "rifle", "Starburst", "Star Power"), ("weapon", "magnum", "Protostar", "Protostar Powerhouse"),
              ("weapon", "smg", "Quark", "Quark Quake"), ("ordnance", "loc", "Translocator", "Blink and You'll Miss It"))
    for i, (slot, code, label, name) in enumerate(weekly, 127):
        rules.append(_ladder(i, name, f"Play games using only {label} in any 7 days: the most in any 7 days counts", GEAR_ICONS[code],
                             _only_games(slot, code), GEAR_WEEK, "week", new=True, group="Experimental gear"))
    rules += [
        _ladder(131, "Full Charge", "Play games using only Overcharge in one day: the most in a single day counts", None,
                _only_games("tacmod", "buff"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(132, "Charged Up", "Play games using only Overcharge in any 7 days: the most in any 7 days counts", None,
                _only_games("tacmod", "buff"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
        # Blazar and Dot Field were released too (user, 2026-10-31): the same set as the other new gear
        _ladder(133, "Blazar Veteran", "Play games using Blazar", "blazar", _games_using("weapon", "chain"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
        _ladder(134, "Dot Field Veteran", "Play games using Dot Field", None, _games_using("ordnance", "dot"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
        _ladder(135, "Blazing Trail", "Play games using only Blazar in one day: the most in a single day counts", "blazar",
                _only_games("weapon", "chain"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(136, "Dot to Dot", "Play games using only Dot Field in one day: the most in a single day counts", None,
                _only_games("ordnance", "dot"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(137, "Blazar Barrage", "Play games using only Blazar in any 7 days: the most in any 7 days counts", "blazar",
                _only_games("weapon", "chain"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
        _ladder(138, "Dot Matrix", "Play games using only Dot Field in any 7 days: the most in any 7 days counts", None,
                _only_games("ordnance", "dot"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
    ]

    # In one game (user, 2026-11-03); 4v4 games only. Targets from the archive's per-game distributions (3+ minute games):
    # standing still median 34 % / p99 70 %, average speed p50 2.8 / p99 4.6 m/s, length p50 8.5 / p99 17 min,
    # own capture time p90 3.2 / p99 4.1 min, up to 8 loadouts. Left / right arm is a handedness flag (0 or 100 % in
    # nearly every game), so there is no arm ladder, only "both arms". Glass Cannon (most deaths) was dropped by the user.
    rules += [
        _tiered(139, "Untouchable", "Win a 4v4 game of 3+ minutes without dying once. Counts every such win", "deaths",
                lambda g: g.four_v_four and g.won and g.play_time_s >= FULL_GAME_S and g.deaths == 0, (1, 2, 3, 5, 8), estimated=True, new=True, group="Survival"),
        _ladder(140, "Marathon Bot", "Play one long 4v4 game: the length of your longest game counts", None, _v4(lambda gs: gs[0].play_time_s / 60),
                (12, 15, 18, 21, 26), "game", " min", new=True, group="Activity"),
        _tiered(141, "Comeback Kid", "Win a 4v4 Capture Point game after losing the first round (a 2-1 win). Counts every such win", "capture_point",
                lambda g: g.four_v_four and _capture(g) and g.won and g.rounds_lost == 1, (1, 5, 15, 40, 100), new=True, group="Capture Point"),
        _ladder(142, "Statue", "Stand still (under 1 m/s) for a share of one 4v4 game of 3+ minutes: your best game counts", None,
                _v4(_full(_pct("stopped"))), (50, 60, 70, 80, 90), "game", "%", new=True, group="Movement"),
        _ladder(143, "Lone Wolf", "Stay away from your teammates (more than 2.6 m) for a share of one 4v4 game of 3+ minutes: your best game counts",
                "team_proximity", _v4(_full(_away_from_mates)), (92, 95, 97, 98.5, 99.5), "game", "%", new=True, group="Movement"),
        Rule(144, "Ambidextrous", "Play one 4v4 game of 3+ minutes holding the disc-arm on each side for at least 40 % of the time", "game", None,
             _v4(_full(_both_arms)), new=True, group="Movement"),
        _ladder(145, "Speed Demon", "Keep a high average speed through one whole 4v4 game of 3+ minutes: your best game counts", "speed",
                _v4(_full(_AvgValue("speed_sum", 1.0))), (3.5, 4, 4.5, 5.5, 7), "game", " m/s", new=True, group="Movement"),
        _ladder(146, "Point Guard", "Your team's capture progress is rising for part of one 4v4 Capture Point game: your best game counts",
                "capture_point", _v4(lambda gs: gs[0].capture_s / 60 if _capture(gs[0]) else 0.0), (2, 3, 3.5, 4.2, 5), "game", " min",
                new=True, group="Capture Point"),
        _ladder(147, "Contested Ground", "The point is contested (both teams on it) for part of one 4v4 Capture Point game: your best game counts",
                "capture_point", _v4(lambda gs: gs[0].contested_s / 60 if _capture(gs[0]) else 0.0), (2, 3.5, 5, 6.5, 8), "game", " min",
                new=True, group="Capture Point"),
        _tiered(148, "One-Trick Pony", "Win a 4v4 game while using one single loadout (weapon, tac mod and ordnance) for at least 95 % of it. Counts every such win",
                "loadout", lambda g: g.four_v_four and g.won and g.main_loadout() is not None, (1, 10, 30, 80, 200), new=True, group="Gear mastery"),
        _ladder(149, "Loadout Roulette", "Switch between loadouts in one 4v4 game: each loadout used for at least 5 % of the game counts, your best game wins",
                "loadout", _v4(lambda gs: gs[0].loadouts_played()), (4, 5, 6, 7, 8), "game", new=True, group="Gear mastery"),
        _ladder(150, "Mime Troupe", "Emote as much as you can in one 4v4 game of 3+ minutes without dying: your best game counts", None,
                _v4(lambda gs: gs[0].emotes if gs[0].play_time_s >= FULL_GAME_S and gs[0].deaths == 0 else 0), (4, 8, 12, 16, 20), "game",  # x4 (user, 2026-11-03)
                estimated=True, new=True, group="Emotes"),
        _ladder(151, "Victory Lap", "Emote as much as you can in one 4v4 game that your team wins: your best game counts", None,
                _v4(lambda gs: gs[0].emotes if gs[0].won else 0), (12, 24, 40, 60, 100), "game", new=True, group="Emotes"),
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


WEEK = timedelta(days=7)


def _rolling_weeks(games: list[Game], maximal: bool) -> list[list[Game]]:
    """Every 7-day window that starts at one of the player's games (any 7 days can be slid to start at its first game).
    `maximal`: skip windows that are a part of the one before (same last game), for rules where more games can
    never lower the value (counts); averages and ratios need every window."""
    ordered = sorted(games, key=lambda g: g.start_dt)
    out: list[list[Game]] = []
    end = prev_end = 0
    for i, g in enumerate(ordered):
        limit = g.start_dt + WEEK
        end = max(end, i + 1)
        while end < len(ordered) and ordered[end].start_dt < limit:
            end += 1
        if maximal and i and end == prev_end:
            continue
        out.append(ordered[i:end])
        prev_end = end
    return out


def _monotone(rule: "Rule") -> bool:
    """True when adding games to a group can never lower the rule's value (so only maximal windows need checking)."""
    return bool(rule.levels) and not isinstance(rule.count, _AvgValue)


def _week_key(rule: "Rule") -> str:
    if rule.period != "week":
        return rule.period
    return "week" if _monotone(rule) else "week_all"


def _groups(games: list[Game], period: str) -> list[list[Game]]:
    if period == "all":
        return [games]
    if period == "game":
        return [[g] for g in games]
    if period in ("week", "week_all"):
        return _rolling_weeks(games, maximal=period == "week")
    key = lambda g: g.day
    groups = defaultdict(list)
    for g in games:
        groups[key(g)].append(g)
    return list(groups.values())


def _reached_gold(entry: dict, rule: Rule) -> bool:
    """Medal Collector: a ladder counts from gold (third medal) on, a single-step rule when completed."""
    return entry["count"] >= rule.levels[2] if rule.levels else entry["progress"] >= 1


def evaluate(games: list[Game]) -> list[dict]:
    """Progress per rule: best period, capped at 1. Ladders also report the best count per period group."""
    groups = {p: _groups(games, p) for p in ("game", "day", "week", "week_all", "all")}
    entries: dict[int, dict] = {}
    for rule in RULES:
        if rule.meta:
            continue
        n = None
        if rule.levels:  # ladder: the best count over the period groups (once: progress follows from it)
            n = max((rule.count(g) for g in groups[_week_key(rule)] if g), default=0)
            best = _levelled(lambda _, n=n: n, rule.levels)([])
        else:
            best = max((rule.score(g) for g in groups[_week_key(rule)] if g), default=0.0)
        progress = round(clamp(best), 4)
        entry = {
            "id": rule.id, "name": rule.name, "description": rule.description, "period": rule.period,
            "icon": icon_file(rule), "estimated": rule.estimated, "new": rule.new, "group": rule.group, "progress": progress, "tier": tier(progress),
        }
        if n is not None:  # the website shows "12 / 25 for diamond"
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
    groups = {p: _groups(ordered, p) for p in ("game", "day", "week", "week_all")}
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
            # a rolling week is complete at its last game, a day / game at its first (as before)
            pick = max if rule.period == "week" else min
            done = [pick(g.started_at for g in group) for group in groups[_week_key(rule)] if group and rule.score(group) >= 1]
            if done:
                out[rule.id] = min(done)[:10]
    return out
